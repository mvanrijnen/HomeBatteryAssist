"""Tests for setting up and unloading HomeBatteryAssist."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist.const import (
    CONF_MAX_CURRENT,
    CONF_PHASES,
    DOMAIN,
)


async def test_setup_and_unload(hass: HomeAssistant) -> None:
    """The config entry loads and unloads cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_PHASES: 3,
            CONF_MAX_CURRENT: 25,
            "sensor_l1": "sensor.power_l1",
            "sensor_l2": "sensor.power_l2",
            "sensor_l3": "sensor.power_l3",
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
