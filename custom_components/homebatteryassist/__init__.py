"""The HomeBatteryAssist integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .consumption import HouseConsumption
from .forecast import ForecastCoordinator
from .models import HomeBatteryAssistConfigEntry, HomeBatteryAssistData

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: HomeBatteryAssistConfigEntry
) -> bool:
    """Set up HomeBatteryAssist from a config entry."""
    forecast = ForecastCoordinator(hass, entry)
    await forecast.async_config_entry_first_refresh()
    if forecast.price_entity:
        # New day-ahead prices arrive as a state/attribute update of the sensor.
        @callback
        def _price_updated(event: Event[EventStateChangedData]) -> None:
            hass.async_create_task(forecast.async_request_refresh())

        entry.async_on_unload(
            async_track_state_change_event(hass, forecast.price_entity, _price_updated)
        )

    consumption = HouseConsumption(hass, entry)
    await consumption.async_start()

    entry.runtime_data = HomeBatteryAssistData(consumption, forecast)
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
        # Persist the consumption history before a reload reads it again.
        await entry.runtime_data.consumption.async_stop()
    return unloaded
