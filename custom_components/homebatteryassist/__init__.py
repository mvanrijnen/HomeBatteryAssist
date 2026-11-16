"""The HomeBatteryAssist integration.

Modules and data flow (see the package docstrings):

    inputs  ->  history  ->  forecasts  ->  (planning)  ->  output
    explain (decision log, "why") and Python logging are used by all modules.

This file only wires the modules of a config entry together.
"""

from __future__ import annotations

from datetime import datetime

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
    CONF_HISTORY_INTERVAL,
    CONF_NOTIFY_KINDS,
    CONF_NOTIFY_TARGETS,
    CONF_VACATION,
    DEFAULT_HISTORY_INTERVAL,
    DOMAIN,
)
from .engine.batteries.monitor import ACTIVITY_THRESHOLD_W, BatteryInput, activity_of
from .engine.batteries.virtual import VirtualBatterySimulator
from .engine.explain import DecisionLog
from .engine.explain.notify import Notifier
from .engine.forecasts.accuracy import ForecastAccuracy
from .engine.forecasts.adjustments import AdjustmentStore
from .engine.forecasts.coordinator import ForecastCoordinator
from .engine.history import ConsumptionHistory
from .engine.inputs.measurements import MeasurementInput
from .engine.modules.forecasters import async_load_user_forecasters
from .engine.modules.planners import async_load_user_planners
from .engine.modules.pv_forecasts import async_load_user_pv_sources
from .engine.modules.tariffs import async_load_user_tariffs
from .engine.planning.battery_plan import MODE_NOM
from .engine.planning.verification import PlanVerification
from .models import HomeBatteryAssistConfigEntry, HomeBatteryAssistData
from .output.panel import async_setup_panel
from .services import async_setup_services

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


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
        lambda: batteries.states.values(),
        await async_load_user_planners(hass),
        await async_load_user_forecasters(hass),
        await async_load_user_tariffs(hass),
        await async_load_user_pv_sources(hass),
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
    await forecast.async_config_entry_first_refresh()
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

    measurements = MeasurementInput(hass, entry, decisions)

    @callback
    def _record(when: datetime, power: float | None) -> None:
        flow = measurements.flow
        history.add_sample(
            when,
            power,
            flow.excluded_w if flow else None,
            flow.pv_w if flow and measurements.pv_sensors else None,
            flow.battery_w if flow and measurements.batteries else None,
            (flow.phase_house_w, flow.phase_pv_w) if flow else None,
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
        stats = batteries.stats.values()
        return {
            "charged_kwh": sum(s.get("charged_kwh", 0.0) for s in stats),
            "discharged_kwh": sum(s.get("discharged_kwh", 0.0) for s in stats),
            "value": sum(s.get("value", 0.0) for s in stats),
        }

    @callback
    def _check_plan(now: datetime) -> None:
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

    simulator = VirtualBatterySimulator(
        hass, batteries, measurements, forecast, decisions
    )
    simulator.async_start()
    entry.async_on_unload(simulator.async_stop)

    entry.runtime_data = HomeBatteryAssistData(
        decisions=decisions,
        measurements=measurements,
        batteries=batteries,
        history=history,
        forecast=forecast,
        plan_check=plan_check,
        simulator=simulator,
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
