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
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import CONF_HISTORY_INTERVAL, DEFAULT_HISTORY_INTERVAL, DOMAIN
from .explain import DecisionLog
from .forecasts.accuracy import ForecastAccuracy
from .forecasts.adjustments import AdjustmentStore
from .forecasts.coordinator import ForecastCoordinator
from .history import ConsumptionHistory
from .inputs.batteries import BatteryInput
from .inputs.measurements import MeasurementInput
from .models import HomeBatteryAssistConfigEntry, HomeBatteryAssistData
from .output.panel import async_setup_panel
from .services import async_setup_services
from .simulation.virtual_battery import VirtualBatterySimulator

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
    )
    forecast.last_full = lambda battery_id: batteries.stats.get(battery_id, {}).get(
        "last_full_charge"
    )

    def _price_now() -> float | None:
        data, now = forecast.data, dt_util.utcnow()
        if data is None:
            return None
        return next((p.price for p in data.prices if p.start <= now < p.end), None)

    batteries.price_now = _price_now
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
    if forecast.price_entity:
        # New day-ahead prices arrive as a state/attribute update of the sensor.
        @callback
        def _price_updated(event: Event[EventStateChangedData]) -> None:
            hass.async_create_task(forecast.async_request_refresh())

        entry.async_on_unload(
            async_track_state_change_event(hass, forecast.price_entity, _price_updated)
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
    measurements.async_start()
    await measurements.async_start_meter()

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
    return unloaded


async def _async_version(hass: HomeAssistant) -> str:
    """Integration version, used to bust the browser cache of the panel."""
    from homeassistant.loader import async_get_integration

    integration = await async_get_integration(hass, DOMAIN)
    return str(integration.version)
