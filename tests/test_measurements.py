"""Tests for the measurement inputs, house consumption and its sensor."""

from typing import Any

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, State
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist.const import (
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_PHASE,
    CONF_PHASES,
    CONF_SENSOR,
    DOMAIN,
    SUBENTRY_EXCLUDED_LOAD,
    SUBENTRY_PV_SOURCE,
)
from custom_components.homebatteryassist.inputs.units import state_to_watts

SENSOR = "sensor.homebatteryassist_house_consumption"


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        ("1500", "W", 1500.0),
        ("1.5", "kW", 1500.0),
        ("-200", "W", -200.0),
        ("10", "A", 2300.0),
        ("500", "mA", 115.0),
        ("unavailable", "W", None),
        ("abc", "W", None),
        ("5", "kWh", None),
        ("5", None, None),
    ],
)
def test_state_to_watts(value: str, unit: str | None, expected: float | None) -> None:
    """Power and current states are converted to W."""
    attributes = {"unit_of_measurement": unit} if unit else {}
    assert state_to_watts(State("sensor.x", value, attributes)) == expected


def _subentry(kind: str, name: str, sensor: str) -> ConfigSubentryData:
    return ConfigSubentryData(
        data={CONF_NAME: name, CONF_SENSOR: sensor, CONF_PHASE: "none"},
        subentry_type=kind,
        title=name,
        unique_id=sensor,
    )


async def _setup(
    hass: HomeAssistant, data: dict[str, Any], subentries: list | None = None
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MAX_CURRENT: 25, **data},
        options={CONF_HISTORY_INTERVAL: 15},
        subentries_data=subentries or [],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _set(hass: HomeAssistant, entity_id: str, value: str, unit: str = "W") -> None:
    hass.states.async_set(entity_id, value, {"unit_of_measurement": unit})


async def test_signed_grid_with_pv_and_excluded_load(hass: HomeAssistant) -> None:
    """House = grid (signed) + PV - excluded load."""
    await _setup(
        hass,
        {
            CONF_PHASES: 3,
            "sensor_l1": "sensor.l1",
            "sensor_l2": "sensor.l2",
            "sensor_l3": "sensor.l3",
        },
        [
            _subentry(SUBENTRY_PV_SOURCE, "Roof", "sensor.pv"),
            _subentry(SUBENTRY_EXCLUDED_LOAD, "EV charger", "sensor.ev"),
        ],
    )
    assert hass.states.get(SENSOR).state == "unavailable"

    _set(hass, "sensor.l1", "1000")
    _set(hass, "sensor.l2", "-500")
    _set(hass, "sensor.l3", "200")
    await hass.async_block_till_done()
    assert float(hass.states.get(SENSOR).state) == 700.0

    _set(hass, "sensor.pv", "2", "kW")
    _set(hass, "sensor.ev", "1500")
    await hass.async_block_till_done()
    # 700 + 2000 - 1500
    assert float(hass.states.get(SENSOR).state) == 1200.0

    # Grid phase unknown -> consumption unknown
    _set(hass, "sensor.l2", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state == "unavailable"


async def test_separate_return_sensor_and_floor(hass: HomeAssistant) -> None:
    """Import minus separate return sensor; result never below 0 W."""
    await _setup(
        hass,
        {CONF_PHASES: 1, "sensor_l1": "sensor.import", "return_l1": "sensor.export"},
        [_subentry(SUBENTRY_EXCLUDED_LOAD, "EV charger", "sensor.ev")],
    )
    _set(hass, "sensor.import", "800")
    _set(hass, "sensor.export", "300")
    await hass.async_block_till_done()
    assert float(hass.states.get(SENSOR).state) == 500.0

    _set(hass, "sensor.ev", "900")
    await hass.async_block_till_done()
    assert float(hass.states.get(SENSOR).state) == 0.0
