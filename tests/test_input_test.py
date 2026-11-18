"""Tests for the grid connection device and its *Test inputs* button."""

from datetime import timedelta
from unittest.mock import patch

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.homebatteryassist.const import (
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_PHASES,
    DOMAIN,
)


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    hass.states.async_set("sensor.l1", "500", {"unit_of_measurement": "W"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.l1"},
        options={CONF_HISTORY_INTERVAL: 15},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_grid_sensors_on_their_own_device(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    registry = er.async_get(hass)
    by_id = {
        identifier: device
        for device in dr.async_entries_for_config_entry(
            dr.async_get(hass), entry.entry_id
        )
        for _, identifier in device.identifiers
    }
    grid = by_id.get(f"{entry.entry_id}_grid")
    main = by_id.get(entry.entry_id)
    assert grid is not None and main is not None
    for key, device in (
        ("grid_power", grid),
        ("phase_l1_load", grid),
        ("input_test", grid),
        ("house_consumption", main),
        ("pv_power", main),
    ):
        domain = "button" if key == "input_test" else "sensor"
        entity_id = registry.async_get_entity_id(
            domain, DOMAIN, f"{entry.entry_id}_{key}"
        )
        assert registry.async_get(entity_id).device_id == device.id, key


async def test_input_test_shows_the_inputs(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    button = er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, f"{entry.entry_id}_input_test"
    )
    with patch("custom_components.homebatteryassist.output.buttons.TEST_SECONDS", 0):
        await hass.services.async_call(
            "button", "press", {"entity_id": button}, blocking=True
        )
        hass.states.async_set("sensor.l1", "800", {"unit_of_measurement": "W"})
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
        await hass.async_block_till_done()
    notes = persistent_notification._async_get_or_create_notifications(hass)
    note = notes[f"{DOMAIN}_input_test"]
    assert "Grid connection" in note["message"]
    assert "sensor.l1" in note["message"]
    assert "| L1 |" in note["message"]
