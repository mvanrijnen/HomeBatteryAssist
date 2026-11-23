"""The HomeBatteryAssist integration.

Modules and data flow (see the package docstrings):

    inputs  ->  history  ->  forecasts  ->  (planning)  ->  output
    explain (decision log, "why") and Python logging are used by all modules.

This file only wires the modules of a config entry together.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.const import (
    CONF_NAME,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_utc_time_change,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COMMAND_CHECK_MINUTES,
    CONF_COMMAND_CHECK_W,
    CONF_CONTROL_ENABLED,
    CONF_CONTROL_MODE,
    CONF_CONTROL_TEST,
    CONF_EXPORT_LIMIT,
    CONF_EXPORT_LIMIT_COST,
    CONF_EXPORT_LIMIT_MAX_W,
    CONF_EXPORT_LIMIT_PRICE,
    CONF_EXPORT_NEVER,
    CONF_HISTORY_INTERVAL,
    CONF_INTERCEPTOR,
    CONF_INVERTER_ADDRESS,
    CONF_INVERTER_DRIVER,
    CONF_INVERTER_MAX_CURRENT,
    CONF_MAX_CHARGE_PRICE,
    CONF_MIN_DISCHARGE_PRICE,
    CONF_NOTIFY_KINDS,
    CONF_NOTIFY_TARGETS,
    CONF_PHASE,
    CONF_PV_DEVIATION_MINUTES,
    CONF_SPIKE_DURATION,
    CONF_SPIKE_FILTER,
    CONF_SPIKE_THRESHOLD,
    CONF_STORAGE_BACKEND,
    CONF_STORAGE_URL,
    CONF_VACATION,
    DEFAULT_COMMAND_CHECK_MINUTES,
    DEFAULT_COMMAND_CHECK_W,
    DEFAULT_EXPORT_LIMIT,
    DEFAULT_EXPORT_LIMIT_COST,
    DEFAULT_EXPORT_LIMIT_MAX_W,
    DEFAULT_EXPORT_LIMIT_PRICE,
    DEFAULT_EXPORT_NEVER,
    DEFAULT_HISTORY_INTERVAL,
    DEFAULT_PV_DEVIATION_MINUTES,
    DEFAULT_SPIKE_DURATION,
    DEFAULT_SPIKE_THRESHOLD,
    DOMAIN,
    PHASE_NONE,
    PRICES_CHECKED,
    SUBENTRY_PV_SOURCE,
)
from .engine.control.control_loop import CONTROL_MODE_NOM, ControlLoop
from .engine.control.control_test import CONTROL_TEST_ALLOWED, ControlTest
from .engine.control.export_limiter import ExportLimiter
from .engine.control.interceptors import (
    async_load_user_interceptors,
    create_interceptor,
)
from .engine.coordinator import ForecastCoordinator
from .engine.db_store import async_close_databases, database_url
from .engine.devices.batteries.virtual import VirtualBatterySimulator
from .engine.devices.inverters import get_driver as get_inverter_driver
from .engine.evaluation.battery_temperature import TemperatureLearning
from .engine.evaluation.command_check import CommandMonitor
from .engine.evaluation.forecast_accuracy import ForecastAccuracy
from .engine.evaluation.plan_check import PlanVerification
from .engine.evaluation.pv_corrections import async_load_user_pv_correctors
from .engine.evaluation.unexpected_surplus import UnexpectedSurplus
from .engine.explain import DecisionLog
from .engine.explain.activity_log import IDLE_W as ACTIVITY_IDLE_W
from .engine.explain.activity_log import ActivityLog
from .engine.explain.notifications import Notifier
from .engine.explain.plan_phases import reason_now
from .engine.forecast.forecasters import async_load_user_forecasters
from .engine.forecast.user_adjustments import AdjustmentStore
from .engine.history import ConsumptionHistory
from .engine.history.temperature_import import (
    async_import_temperatures,
    async_import_zones,
)
from .engine.measure.battery_monitor import (
    ACTIVITY_THRESHOLD_W,
    BatteryInput,
    activity_of,
    direct_link,
)
from .engine.measure.house_measurement import MeasurementInput, solar_surplus_w
from .engine.measure.recorder_check import check_recorder
from .engine.measure.spike_filters import (
    DEFAULT_SPIKE_FILTER,
    async_load_user_spike_filters,
    create_spike_filter,
)
from .engine.planning.battery_plan import MODE_NOM
from .engine.planning.export_limit import (
    connection_w,
    export_capacity_w,
    inverter_max_w,
)
from .engine.planning.planners import async_load_user_planners
from .engine.sources.pv_forecasts import async_load_user_pv_sources
from .engine.sources.tariffs import async_load_user_tariffs
from .engine.sources.weather import async_load_user_weather_sources
from .models import HomeBatteryAssistConfigEntry, HomeBatteryAssistData
from .output.panel import async_setup_panel
from .output.registry_cleanup import remove_stale
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions and the status panel (independent of config entries).

    Home Assistant calls this once a config entry exists. If that entry is not
    loaded, the panel explains how to set it up.
    """
    async_setup_services(hass)
    await async_setup_panel(hass, await _async_version(hass))
    return True


# A price threshold above this per kWh was entered in ct (prices are per kWh
# in the main currency since 0.92).
CENT_THRESHOLD = 3.0


def _convert_cent_thresholds(
    hass: HomeAssistant, entry: HomeBatteryAssistConfigEntry, decisions: DecisionLog
) -> None:
    """Price thresholds that were clearly entered in ct (above
    ``CENT_THRESHOLD`` per kWh) are converted to euro. Only for the euro: in
    other currencies (CZK, SEK, JPY, ...) such a price is normal. Once
    converted a value is below the threshold, so it is not converted again.
    Done once per entry (``PRICES_CHECKED`` in its data): a price above the
    threshold set later is meant as it is."""
    if entry.data.get(PRICES_CHECKED):
        return
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, PRICES_CHECKED: True}
    )
    if (hass.config.currency or "EUR").upper() != "EUR":
        return
    options = dict(entry.options)
    changed = []
    for key in (CONF_MIN_DISCHARGE_PRICE, CONF_MAX_CHARGE_PRICE):
        value = options.get(key)
        if isinstance(value, (int, float)) and abs(value) > CENT_THRESHOLD:
            options[key] = round(value / 100, 5)
            changed.append((key, value, options[key]))
    if not changed:
        return
    hass.config_entries.async_update_entry(entry, options=options)
    for key, old, new in changed:
        decisions.async_log(
            "planning", "price_setting_converted", setting=key, old=old, new=new
        )


async def async_setup_entry(
    hass: HomeAssistant, entry: HomeBatteryAssistConfigEntry
) -> bool:
    """Set up HomeBatteryAssist from a config entry."""
    decisions = DecisionLog(hass, entry.entry_id)
    await decisions.async_load()
    _convert_cent_thresholds(hass, entry, decisions)
    decisions.notifier = Notifier(
        hass,
        list(entry.options.get(CONF_NOTIFY_TARGETS) or []),
        list(entry.options.get(CONF_NOTIFY_KINDS) or []),
    )
    adjustments = AdjustmentStore(hass, entry.entry_id)
    await adjustments.async_load()
    database = database_url(
        hass,
        entry.options.get(CONF_STORAGE_BACKEND),
        entry.options.get(CONF_STORAGE_URL),
    )
    accuracy = ForecastAccuracy(hass, entry.entry_id, database)
    await accuracy.async_load()

    history = ConsumptionHistory(
        hass,
        entry.entry_id,
        entry.options.get(CONF_HISTORY_INTERVAL, DEFAULT_HISTORY_INTERVAL),
        database,
    )
    # Before loading: an interval that ended while Home Assistant was down is
    # finished at load, as vacation when vacation mode is on.
    history.vacation = bool(entry.options.get(CONF_VACATION, False))
    await history.async_load()

    batteries = BatteryInput(hass, entry, decisions)
    await batteries.async_start()
    # Setup fails (and is retried): stop what already runs, so a retry does
    # not leave a second battery monitor, history or listeners writing the
    # same stores (HA does not call async_unload_entry for a failed setup).
    history_started = False
    measurements = None
    try:
        forecast = ForecastCoordinator(
            hass,
            entry,
            decisions,
            history,
            adjustments,
            accuracy,
            batteries.plan_states,
            await async_load_user_planners(hass),
            await async_load_user_forecasters(hass),
            await async_load_user_tariffs(hass),
            await async_load_user_pv_sources(hass),
            await async_load_user_pv_correctors(hass),
            await async_load_user_weather_sources(hass),
        )
        forecast.last_full = lambda battery_id: batteries.stats.get(battery_id, {}).get(
            "last_full_charge"
        )
        forecast.full_charge_since = batteries.full_charge_since
        forecast.last_full_charge = lambda battery_id: batteries.stats.get(
            battery_id, {}
        ).get("last_full_charge")

        def _price_now(when: datetime | None = None) -> float | None:
            data, now = forecast.data, when or dt_util.utcnow()
            if data is None:
                return None
            return next((p.price for p in data.prices if p.start <= now < p.end), None)

        def _export_price_now(when: datetime | None = None) -> float | None:
            data, now = forecast.data, when or dt_util.utcnow()
            if data is None:
                return None
            # The export price point covering now (a slot may average several).
            point = next(
                (p.price for p in data.export_prices if p.start <= now < p.end), None
            )
            if point is not None:
                return point
            slot = next((s for s in data.battery if s.start <= now < s.end), None)
            if slot is not None and slot.export_price is not None:
                return slot.export_price
            price = _price_now(now)
            return None if price is None else price * forecast.export_factor

        batteries.price_now = _price_now
        batteries.export_price_now = _export_price_now

        def _planned_now() -> float | None:
            data, now = forecast.data, dt_util.utcnow()
            if data is None or len(batteries.plan_states()) != 1:
                # Several batteries: the plan pools them (which one takes it
                # depends on the charge order), so no per-battery comparison.
                return None
            return next(
                (s.power_w for s in data.battery if s.start <= now < s.end), None
            )

        batteries.planned_now = _planned_now

        def _plan_reason():
            """The phase the selected plan is in now, with its reason."""
            data, now = forecast.data, dt_util.utcnow()
            if data is None or not data.battery:
                return None
            configs = [s.config for s in batteries.plan_states() if s.soc is not None]
            return reason_now(
                data.battery,
                now,
                data.selected_plan.strategy if data.selected_plan else data.plan_mode,
                forecast.plan_floor(configs, now),
                hass.config.language,
                hass.config.currency,
            )

        batteries.plan_reason = _plan_reason

        def _expected_until(battery_id: str, activity: str):
            """When a real battery's activity is expected to end if it follows the
            forecast at zero on the meter (its usual own control), and why. Only
            with a single battery: the plan pools all batteries."""
            data, now = forecast.data, dt_util.utcnow()
            live = [s for s in batteries.states.values() if s.available]
            plan = data.plans.get(MODE_NOM) if data else None
            if plan is None or len(live) != 1 or live[0].config.id != battery_id:
                return None
            grid = batteries.grid_now()
            if (
                activity == "charging"
                and grid is not None
                and grid > ACTIVITY_THRESHOLD_W
            ):
                return None  # charging from the grid: not zero on the meter
            config = live[0].config
            rules = forecast.rules
            for slot in plan.slots:
                if slot.end <= now:
                    continue
                if activity_of(slot.power_w) == activity:
                    continue
                if slot.start <= now:
                    # The forecast does not match what the battery does now.
                    return None
                if activity == "idle":
                    why = (
                        "resume_charging"
                        if activity_of(slot.power_w) == "charging"
                        else "resume_supplying"
                    )
                elif activity == "discharging":
                    # Empty: at its minimum or at the reserve the plan holds.
                    floor = max(
                        config.min_soc,
                        rules.reserve_soc,
                        rules.night_reserve_soc if slot.start in data.night else 0.0,
                        rules.peak_reserve_soc if forecast.peak_w > 0 else 0.0,
                    )
                    why = "empty" if slot.soc <= floor + 1 else "pv_covers"
                else:
                    why = "full" if slot.soc >= config.max_soc - 1 else "pv_end"
                return max(slot.start, now), why
            return None

        batteries.expected_until = _expected_until
        try:
            await forecast.async_config_entry_first_refresh()
        except Exception:
            await forecast.async_shutdown()
            raise
        if not hass.is_running:
            # Other integrations (price and PV forecasts) may still be starting:
            # recalculate once Home Assistant has fully started.
            @callback
            def _started(_hass: HomeAssistant) -> None:
                hass.async_create_task(forecast.async_request_refresh())

            entry.async_on_unload(async_at_started(hass, _started))
        if price_entities := forecast.price_watch:
            # New day-ahead prices arrive as a state/attribute update of the sensor.
            @callback
            def _price_updated(event: Event[EventStateChangedData]) -> None:
                hass.async_create_task(forecast.async_request_refresh())

            entry.async_on_unload(
                async_track_state_change_event(hass, price_entities, _price_updated)
            )

        await history.async_start()

        async def _async_save_on_stop(_event: Event) -> None:
            # Home Assistant does not unload config entries when it stops:
            # keep the running history interval and the battery counters.
            await history.async_save_running()
            await batteries.async_save_now()
            await forecast.accuracy.async_save()  # written hourly otherwise

        entry.async_on_unload(
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_save_on_stop)
        )
        history_started = True
        if forecast.outdoor_sensor or forecast.zones:
            # Past records get their outdoor temperature and the heating/cooling
            # zones from the statistics, so the temperature effect is learned at
            # once; then the forecast is made again with it.
            async def _fill_temperatures() -> None:
                filled = 0
                try:
                    if forecast.outdoor_sensor:
                        filled += await async_import_temperatures(
                            hass, history, forecast.outdoor_sensor
                        )
                    if forecast.zones:
                        filled += await async_import_zones(
                            hass, history, forecast.zones
                        )
                except Exception:  # the recorder may be unavailable
                    _LOGGER.exception("Filling in past temperatures failed")
                if filled:
                    forecast.history_changed()  # fit the temperature effect anew
                    await forecast.async_request_refresh()

            entry.async_create_background_task(
                hass, _fill_temperatures(), f"{DOMAIN} outdoor temperatures"
            )

        measurements = MeasurementInput(hass, entry, decisions)
        if forecast.spike_history or forecast.spike_battery:
            measurements.spike_filter = create_spike_filter(
                entry.options.get(CONF_SPIKE_FILTER, DEFAULT_SPIKE_FILTER),
                await async_load_user_spike_filters(hass),
                entry.options.get(CONF_SPIKE_THRESHOLD, DEFAULT_SPIKE_THRESHOLD),
                entry.options.get(CONF_SPIKE_DURATION, DEFAULT_SPIKE_DURATION) * 60,
            )

        @callback
        def _record(when: datetime, power: float | None) -> None:
            flow = measurements.flow
            history.add_sample(
                when,
                power,
                flow.excluded_w if flow else None,
                # What the sun gave (also when an inverter held PV back), so
                # the PV correction and accuracy learn from it.
                flow.pv_potential_w
                if flow and measurements.has_pv and measurements.pv_known
                else None,
                flow.battery_w if flow and measurements.batteries else None,
                (flow.phase_house_w, flow.phase_pv_w) if flow else None,
                flow.heating_w if flow and measurements.heating_sensors else None,
                forecast.outdoor_temperature(),
                {zone.zone_id: zone.read(hass) for zone in forecast.zones} or None,
                measurements.take_spike_wh(),
                (flow.phase_w, flow.phase_a, flow.phase_v)
                if flow and flow.phase_a
                else None,
                flow.pv_w
                if flow and measurements.has_pv and measurements.pv_known
                else None,
            )

        measurements.async_add_listener(_record)
        batteries.grid_now = lambda: (
            measurements.flow.grid_w if measurements.flow is not None else None
        )

        @callback
        def _note_grid(when: datetime, _power: float | None) -> None:
            flow = measurements.flow
            batteries.note_grid(when, flow.grid_w if flow is not None else None)

        entry.async_on_unload(measurements.async_add_listener(_note_grid))
        measurements.async_start()
        await measurements.async_start_meter()

        # The plan afterwards: per history interval, planned vs what happened.
        plan_check = PlanVerification(hass, entry.entry_id)
        await plan_check.async_load()

        def _battery_totals() -> dict[str, float]:
            # A real battery with a twin is not planned: left out.
            planned = [s.config for s in batteries.plan_states()]
            stats = [batteries.stats[c.id] for c in planned if c.id in batteries.stats]
            totals = {
                "charged_kwh": sum(s.get("charged_kwh", 0.0) for s in stats),
                "discharged_kwh": sum(s.get("discharged_kwh", 0.0) for s in stats),
                "value": sum(s.get("value", 0.0) for s in stats),
            }
            # Per group (real / virtual), for how well each follows the plan.
            capacity = sum(c.capacity_kwh for c in planned)
            if capacity > 0:
                real = [c for c in planned if not c.virtual]
                totals["real_share"] = sum(c.capacity_kwh for c in real) / capacity
                for group, virtual in (("real", False), ("virtual", True)):
                    ids = [c.id for c in planned if c.virtual is virtual]
                    for key in ("charged_kwh", "discharged_kwh"):
                        totals[f"{group}_{key}"] = sum(
                            batteries.stats[i].get(key, 0.0) for i in ids
                        )
            return totals

        @callback
        def _check_plan(now: datetime) -> None:
            # A new slot: entities showing "the slot now" move on with it.
            if forecast.data is not None:
                forecast.async_update_listeners()
            batteries.count_up_to(now)  # counters up to the slot boundary
            plan_check.settle(now, _battery_totals, forecast.cycle_cost)
            if forecast.data is not None:
                plan_check.record_plan(
                    forecast.data.battery,
                    forecast.data.plan_mode,
                    now,
                    forecast.export_factor,
                    forecast.cycle_cost,
                )

        minutes = history.minutes
        entry.async_on_unload(
            async_track_utc_time_change(
                hass,
                _check_plan,
                minute=f"/{minutes}" if minutes < 60 else 0,
                second=1,
            )
        )
        _check_plan(dt_util.utcnow())

        # The user's last say per battery (interceptor module), before
        # HomeBatteryAssist's own final check.
        forecast.interceptor = create_interceptor(
            entry.options.get(CONF_INTERCEPTOR),
            await async_load_user_interceptors(hass),
        )
        simulator = VirtualBatterySimulator(
            hass, batteries, measurements, forecast, decisions
        )
        simulator.async_start()
        entry.async_on_unload(simulator.async_stop)
        # The plans start from the charge hysteresis as the batteries have it:
        # the virtual ones from the simulator, the real ones from their log.
        forecast.held_batteries = lambda: (
            simulator.held | batteries.hysteresis_held(forecast.rules.charge_hysteresis)
        )

        # Why: an unexpected solar surplus or shortage, measured against the
        # forecast now.
        comma = (hass.config.language or "").startswith("nl")
        deviation_after = timedelta(
            minutes=entry.options.get(
                CONF_PV_DEVIATION_MINUTES, DEFAULT_PV_DEVIATION_MINUTES
            )
        )
        solar_checks = [
            UnexpectedSurplus(
                decimal_comma=comma,
                shortage=shortage,
                threshold_w=forecast.pv_deviation_w,
                start_after=deviation_after,
            )
            for shortage in (False, True)
        ]

        @callback
        def _check_surplus(when: datetime, _power: float | None) -> None:
            flow = measurements.flow
            data = forecast.data
            slot = data.consumption_at(when) if data is not None else None
            # The forecast of the hour of this moment (not of the hour in which
            # the last cycle ran).
            pv_expected = data.pv_at(when) if data is not None else None
            known = (
                flow is not None
                and measurements.has_pv
                and measurements.pv_known
                and data is not None
                and pv_expected is not None
                and slot is not None
            )
            for check in solar_checks:
                result = check.update(
                    when,
                    # Like with like: the forecast is the house without the
                    # excluded devices, so an EV charging on the sun is no
                    # "less sun than expected".
                    flow.pv_w - flow.house_w if known else None,
                    pv_expected - slot.power_w if known else None,
                    nom=data is None
                    or (
                        data.selected_plan.strategy
                        if data.selected_plan
                        else data.plan_mode
                    )
                    == MODE_NOM,
                )
                if result is not None:
                    key, params = result
                    decisions.async_log("forecast", key, **params)

        entry.async_on_unload(measurements.async_add_listener(_check_surplus))

        # Does each real battery follow the command it has (in this phase from
        # its own integration; later also HomeBatteryAssist's own commands)?
        # What each real battery can do at its temperature (to learn from).
        temperatures = TemperatureLearning(
            hass, entry.entry_id, forecast.outdoor_temperature
        )
        await temperatures.async_load()
        commands = CommandMonitor(
            hass,
            batteries,
            decisions,
            threshold_w=entry.options.get(
                CONF_COMMAND_CHECK_W, DEFAULT_COMMAND_CHECK_W
            ),
            start_after=timedelta(
                minutes=entry.options.get(
                    CONF_COMMAND_CHECK_MINUTES, DEFAULT_COMMAND_CHECK_MINUTES
                )
            ),
            observer=temperatures,
        )
        commands.async_start()
        entry.async_on_unload(commands.async_stop)

        # Test control per real battery: built, off unless the setting *Test
        # control* is on; a test always ends with the battery back on its own
        # control, also on unload.
        control_test = ControlTest(
            hass,
            batteries,
            decisions,
            reserve_soc=lambda: forecast.rules.reserve_soc,
            commands=commands,
            allowed=bool(entry.options.get(CONF_CONTROL_TEST, CONTROL_TEST_ALLOWED)),
        )
        entry.async_on_unload(control_test.async_stop_all)
        # Home Assistant stopping does not unload the entry: a running test
        # is stopped (and the battery released) then too.
        entry.async_on_unload(
            hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, control_test.async_stop_all
            )
        )

        # Battery control (engine/control/control_loop.py): only with the
        # setting Control on, and only the batteries marked in their form.
        # Runs next to the simulator on the same targets; releases every
        # battery on unload and when Home Assistant stops.
        control = None
        if entry.options.get(CONF_CONTROL_ENABLED, False):
            control = ControlLoop(
                hass,
                batteries,
                measurements,
                forecast,
                decisions,
                mode=entry.options.get(CONF_CONTROL_MODE, CONTROL_MODE_NOM),
                monitor=commands,  # releases a battery that does not follow
                tests=control_test,
            )
            control.async_start()
            entry.async_on_unload(control.async_stop_all)
            entry.async_on_unload(
                hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STOP, control.async_stop_all
                )
            )

        # The activity log (dashboard tab Log): what each real battery did,
        # who decided it and whether that was the plan.
        def _activity_look(
            control=control, control_test=control_test
        ) -> list[dict[str, Any]]:
            flow = measurements.flow
            surplus = solar_surplus_w(flow) if flow is not None else None
            data = forecast.data
            plan = data.selected_plan if data is not None else None
            now = dt_util.utcnow()
            slot = (
                next((s for s in plan.slots if s.start <= now < s.end), None)
                if plan is not None
                else None
            )
            planned = (
                None
                if slot is None
                else "charge"
                if slot.power_w > ACTIVITY_IDLE_W
                else "discharge"
                if slot.power_w < -ACTIVITY_IDLE_W
                else "idle"
            )
            price = batteries.price_now()
            looks = []
            for config in batteries.configs:
                if config.virtual:
                    continue
                state = batteries.states.get(config.id)
                check = commands.checks.get(config.id)
                link = direct_link(hass, config)
                held = control.holding.get(config.id) if control else None
                if config.id in control_test.runs:
                    source = "test"
                elif (
                    (check is not None and check.problem)
                    or held in ("not_following", "meter", "unknown")
                    or (link is not None and not link.available)
                ):
                    source = "incident"
                elif control is not None and config.id in control.controllers:
                    source = f"hba_{control.mode}"
                else:
                    source = "own"
                looks.append(
                    {
                        "id": config.id,
                        "name": config.name,
                        "power_w": state.power_w if state else None,
                        "pv_surplus_w": surplus,
                        "source": source,
                        "plan": planned,
                        "price": price,
                    }
                )
            return looks

        activity = ActivityLog(hass, entry.entry_id, _activity_look)
        await activity.async_start()
        entry.async_on_unload(activity.async_stop)

        # The export limit (PV inverters): shown and explained; nothing is sent.
        options = entry.options
        pv_subs = [
            sub
            for sub in entry.subentries.values()
            if sub.subentry_type == SUBENTRY_PV_SOURCE
        ]
        grid_w = connection_w(measurements.phases, measurements.max_current)
        pv_max = [
            inverter_max_w(
                sub.data.get(CONF_INVERTER_MAX_CURRENT),
                measurements.phases
                if sub.data.get(CONF_PHASE, PHASE_NONE) == PHASE_NONE
                else 1,
            )
            for sub in pv_subs
        ]
        export_limiter = ExportLimiter(
            decisions,
            enabled=bool(options.get(CONF_EXPORT_LIMIT, DEFAULT_EXPORT_LIMIT)),
            threshold=float(
                options.get(CONF_EXPORT_LIMIT_PRICE, DEFAULT_EXPORT_LIMIT_PRICE)
            ),
            fixed_w=float(
                options.get(CONF_EXPORT_LIMIT_MAX_W, DEFAULT_EXPORT_LIMIT_MAX_W)
            ),
            cost=float(options.get(CONF_EXPORT_LIMIT_COST, DEFAULT_EXPORT_LIMIT_COST)),
            never=bool(options.get(CONF_EXPORT_NEVER, DEFAULT_EXPORT_NEVER)),
            connection=export_capacity_w(grid_w, pv_max),
            capacity={
                "connection_w": round(grid_w),
                "inverters_w": [None if w is None else round(w) for w in pv_max],
            },
            inverters=[
                (
                    sub.data[CONF_NAME],
                    get_inverter_driver(sub.data.get(CONF_INVERTER_DRIVER)),
                    sub.data.get(CONF_INVERTER_ADDRESS, ""),
                )
                for sub in pv_subs
            ],
            inverter_max=pv_max,
            decimal_comma=comma,
        )

        @callback
        def _check_export(when: datetime, _power: float | None) -> None:
            export_limiter.update(
                when,
                batteries.grid_planned_w(),
                batteries.export_price_now(),
                measured_grid_w=batteries.grid_now(),
                pv_sources=measurements.pv_per_source(),
                headroom_w=batteries.charge_headroom_w(),
            )

        entry.async_on_unload(measurements.async_add_listener(_check_export))

        @callback
        def _expect_export_limit() -> None:
            if forecast.data is not None:
                export_limiter.plan_updated(
                    forecast.data.battery, dt_util.utcnow(), forecast.export_factor
                )

        entry.async_on_unload(forecast.async_add_listener(_expect_export_limit))

        entry.runtime_data = HomeBatteryAssistData(
            decisions=decisions,
            measurements=measurements,
            batteries=batteries,
            history=history,
            forecast=forecast,
            plan_check=plan_check,
            simulator=simulator,
            commands=commands,
            temperatures=temperatures,
            control_test=control_test,
            control=control,
            activity=activity,
            export_limit=export_limiter,
        )
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        remove_stale(hass, entry)
    except Exception:
        if measurements is not None:
            measurements.async_stop()
            await measurements.async_stop_meter()
        await batteries.async_stop()
        if history_started:
            await history.async_stop()
        # A failed setup is not unloaded: close the databases here too, so a
        # delayed write of this instance cannot change rows the retry loaded.
        await async_close_databases(hass)
        raise

    # Sensors the recorder leaves out cannot be filled in from its history:
    # a repair issue names them (checked once Home Assistant has started).
    @callback
    def _check_recorder(_hass: HomeAssistant) -> None:
        try:
            check_recorder(
                hass,
                entry.entry_id,
                [
                    *measurements.source_entity_ids,
                    *(
                        c.soc_sensor
                        for c in batteries.configs
                        if not c.virtual and c.soc_sensor
                    ),
                    *([forecast.outdoor_sensor] if forecast.outdoor_sensor else []),
                    *(s for zone in forecast.zones for s in zone.temperature_sensors),
                ],
            )
        except Exception:  # only a hint: never in the way of the rest
            _LOGGER.exception("Checking the recorder's sensors failed")

    entry.async_on_unload(async_at_started(hass, _check_recorder))
    # Options and subentry changes (PV sources, excluded loads) require a reload.
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    return True


async def _async_entry_updated(
    hass: HomeAssistant, entry: HomeBatteryAssistConfigEntry
) -> None:
    """Reload the entry so changed settings take effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: HomeBatteryAssistConfigEntry
) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = entry.runtime_data
        data.measurements.async_stop()
        await data.measurements.async_stop_meter()
        await data.batteries.async_stop()
        # Persist before a reload reads the stores again.
        await data.history.async_stop()
        await data.decisions.async_save()
        await data.forecast.accuracy.async_save()
        await data.forecast.async_save_price_log()
        await data.plan_check.async_save()
        if data.temperatures is not None:
            await data.temperatures.async_save()
        await async_close_databases(hass)  # a changed URL opens anew
    return unloaded


async def _async_version(hass: HomeAssistant) -> str:
    """Integration version, used to bust the browser cache of the panel."""
    from homeassistant.loader import async_get_integration

    integration = await async_get_integration(hass, DOMAIN)
    return str(integration.version)
