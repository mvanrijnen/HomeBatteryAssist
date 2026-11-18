"""The HomeBatteryAssist integration.

Modules and data flow (see the package docstrings):

    inputs  ->  history  ->  forecasts  ->  (planning)  ->  output
    explain (decision log, "why") and Python logging are used by all modules.

This file only wires the modules of a config entry together.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_utc_time_change,
)
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COMMAND_CHECK_MINUTES,
    CONF_COMMAND_CHECK_W,
    CONF_HISTORY_INTERVAL,
    CONF_INTERCEPTOR,
    CONF_NOTIFY_KINDS,
    CONF_NOTIFY_TARGETS,
    CONF_PV_DEVIATION_MINUTES,
    CONF_SPIKE_DURATION,
    CONF_SPIKE_FILTER,
    CONF_SPIKE_THRESHOLD,
    CONF_VACATION,
    DEFAULT_COMMAND_CHECK_MINUTES,
    DEFAULT_COMMAND_CHECK_W,
    DEFAULT_HISTORY_INTERVAL,
    DEFAULT_PV_DEVIATION_MINUTES,
    DEFAULT_SPIKE_DURATION,
    DEFAULT_SPIKE_THRESHOLD,
    DOMAIN,
)
from .engine.control.control_test import ControlTest
from .engine.control.interceptors import (
    async_load_user_interceptors,
    create_interceptor,
)
from .engine.coordinator import ForecastCoordinator
from .engine.devices.batteries.virtual import VirtualBatterySimulator
from .engine.evaluation.command_check import CommandMonitor
from .engine.evaluation.forecast_accuracy import ForecastAccuracy
from .engine.evaluation.plan_check import PlanVerification
from .engine.evaluation.pv_corrections import async_load_user_pv_correctors
from .engine.evaluation.unexpected_surplus import UnexpectedSurplus
from .engine.explain import DecisionLog
from .engine.explain.notifications import Notifier
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
)
from .engine.measure.house_measurement import MeasurementInput, solar_surplus_w
from .engine.measure.spike_filters import (
    DEFAULT_SPIKE_FILTER,
    async_load_user_spike_filters,
    create_spike_filter,
)
from .engine.planning.battery_plan import MODE_NOM
from .engine.planning.planners import async_load_user_planners
from .engine.sources.pv_forecasts import async_load_user_pv_sources
from .engine.sources.tariffs import async_load_user_tariffs
from .engine.sources.weather import async_load_user_weather_sources
from .models import HomeBatteryAssistConfigEntry, HomeBatteryAssistData
from .output.panel import async_setup_panel
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


async def async_setup_entry(
    hass: HomeAssistant, entry: HomeBatteryAssistConfigEntry
) -> bool:
    """Set up HomeBatteryAssist from a config entry."""
    decisions = DecisionLog(hass, entry.entry_id)
    await decisions.async_load()
    decisions.notifier = Notifier(
        hass,
        list(entry.options.get(CONF_NOTIFY_TARGETS) or []),
        list(entry.options.get(CONF_NOTIFY_KINDS) or []),
    )
    adjustments = AdjustmentStore(hass, entry.entry_id)
    await adjustments.async_load()
    accuracy = ForecastAccuracy(hass, entry.entry_id)
    await accuracy.async_load()

    history = ConsumptionHistory(
        hass,
        entry.entry_id,
        entry.options.get(CONF_HISTORY_INTERVAL, DEFAULT_HISTORY_INTERVAL),
    )
    await history.async_load()
    history.vacation = bool(entry.options.get(CONF_VACATION, False))

    batteries = BatteryInput(hass, entry, decisions)
    await batteries.async_start()

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

    def _price_now() -> float | None:
        data, now = forecast.data, dt_util.utcnow()
        if data is None:
            return None
        return next((p.price for p in data.prices if p.start <= now < p.end), None)

    def _export_price_now() -> float | None:
        data, now = forecast.data, dt_util.utcnow()
        if data is None:
            return None
        slot = next((s for s in data.battery if s.start <= now < s.end), None)
        if slot is not None and slot.export_price is not None:
            return slot.export_price
        price = _price_now()
        return None if price is None else price * forecast.export_factor

    batteries.price_now = _price_now
    batteries.export_price_now = _export_price_now

    def _planned_now() -> float | None:
        data, now = forecast.data, dt_util.utcnow()
        if data is None:
            return None
        return next((s.power_w for s in data.battery if s.start <= now < s.end), None)

    batteries.planned_now = _planned_now

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
        if activity == "charging" and grid is not None and grid > ACTIVITY_THRESHOLD_W:
            return None  # charging from the grid: not zero on the meter
        config = live[0].config
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
                why = "empty" if slot.soc <= config.min_soc + 1 else "pv_covers"
            else:
                why = "full" if slot.soc >= config.max_soc - 1 else "pv_end"
            return max(slot.start, now), why
        return None

    batteries.expected_until = _expected_until
    try:
        await forecast.async_config_entry_first_refresh()
    except Exception:
        # Setup fails (and is retried): stop what already runs, so a retry
        # does not leave a second battery monitor writing the same stores.
        await batteries.async_stop()
        await forecast.async_shutdown()
        raise
    if not hass.is_running:
        # Other integrations (price and PV forecasts) may still be starting:
        # recalculate once Home Assistant has fully started.
        @callback
        def _started(event: Event) -> None:
            hass.async_create_task(forecast.async_request_refresh())

        entry.async_on_unload(
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _started)
        )
    if price_entities := forecast.price_watch:
        # New day-ahead prices arrive as a state/attribute update of the sensor.
        @callback
        def _price_updated(event: Event[EventStateChangedData]) -> None:
            hass.async_create_task(forecast.async_request_refresh())

        entry.async_on_unload(
            async_track_state_change_event(hass, price_entities, _price_updated)
        )

    await history.async_start()
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
                    filled += await async_import_zones(hass, history, forecast.zones)
            except Exception:  # the recorder may be unavailable
                _LOGGER.exception("Filling in past temperatures failed")
            if filled:
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
            flow.pv_w
            if flow and measurements.has_pv and measurements.pv_known
            else None,
            flow.battery_w if flow and measurements.batteries else None,
            (flow.phase_house_w, flow.phase_pv_w) if flow else None,
            flow.heating_w if flow and measurements.heating_sensors else None,
            forecast.outdoor_temperature(),
            {zone.zone_id: zone.read(hass) for zone in forecast.zones} or None,
            measurements.take_spike_wh(),
            (flow.phase_w, flow.phase_a) if flow and flow.phase_a else None,
        )

    measurements.async_add_listener(_record)
    batteries.grid_now = lambda: (
        measurements.flow.grid_w if measurements.flow is not None else None
    )
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
        entry.options.get(CONF_INTERCEPTOR), await async_load_user_interceptors(hass)
    )
    simulator = VirtualBatterySimulator(
        hass, batteries, measurements, forecast, decisions
    )
    simulator.async_start()
    entry.async_on_unload(simulator.async_stop)

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
        known = (
            flow is not None
            and measurements.has_pv
            and measurements.pv_known
            and data is not None
            and data.pv_now_w is not None
            and slot is not None
        )
        for check in solar_checks:
            result = check.update(
                when,
                solar_surplus_w(flow) if known else None,
                data.pv_now_w - slot.power_w if known else None,
                nom=data is None or data.plan_mode == MODE_NOM,
            )
            if result is not None:
                key, params = result
                decisions.async_log("forecast", key, **params)

    entry.async_on_unload(measurements.async_add_listener(_check_surplus))

    # Does each real battery follow the command it has (in this phase from
    # its own integration; later also HomeBatteryAssist's own commands)?
    commands = CommandMonitor(
        hass,
        batteries,
        decisions,
        threshold_w=entry.options.get(CONF_COMMAND_CHECK_W, DEFAULT_COMMAND_CHECK_W),
        start_after=timedelta(
            minutes=entry.options.get(
                CONF_COMMAND_CHECK_MINUTES, DEFAULT_COMMAND_CHECK_MINUTES
            )
        ),
    )
    commands.async_start()
    entry.async_on_unload(commands.async_stop)

    # Test control per real battery: built, switched off in this phase
    # (CONTROL_TEST_ALLOWED); a test always ends with the battery back on its
    # own control, also on unload.
    control_test = ControlTest(
        hass,
        batteries,
        decisions,
        reserve_soc=lambda: forecast.rules.reserve_soc,
        commands=commands,
    )
    entry.async_on_unload(control_test.async_stop_all)

    # Battery control — WRITTEN OUT, NOT ACTIVE (engine/control/control_loop.py;
    # see "Activating" there). Once active it runs next to the simulator, on
    # the same targets, and releases every battery on unload:
    #
    # from .engine.control.control_loop import ControlLoop
    # control = ControlLoop(
    #     hass,
    #     entry,
    #     decisions,
    #     batteries,
    #     measurements,
    #     forecast,
    #     enabled=entry.options.get(CONF_CONTROL_ENABLED, False),
    #     commands=commands,  # releases a battery that does not follow
    # )
    # control.async_start()
    # entry.async_on_unload(control.async_stop)

    entry.runtime_data = HomeBatteryAssistData(
        decisions=decisions,
        measurements=measurements,
        batteries=batteries,
        history=history,
        forecast=forecast,
        plan_check=plan_check,
        simulator=simulator,
        commands=commands,
        control_test=control_test,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
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
    return unloaded


async def _async_version(hass: HomeAssistant) -> str:
    """Integration version, used to bust the browser cache of the panel."""
    from homeassistant.loader import async_get_integration

    integration = await async_get_integration(hass, DOMAIN)
    return str(integration.version)
