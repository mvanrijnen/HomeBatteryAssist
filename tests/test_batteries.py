"""Tests for linking, reading and monitoring home batteries."""

from datetime import datetime, timedelta
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    ConfigSubentryData,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist.const import (
    CONF_CAPACITY,
    CONF_CHARGE_ENTITY,
    CONF_CONTROL_TYPE,
    CONF_DISCHARGE_ENTITY,
    CONF_EFFICIENCY,
    CONF_FULL_CHARGE_INTERVAL,
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_CURRENT,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_MODE_CHARGE,
    CONF_MODE_DISCHARGE,
    CONF_MODE_ENTITY,
    CONF_MODE_IDLE,
    CONF_PHASE,
    CONF_PHASES,
    CONF_POWER_SENSOR,
    CONF_POWER_SIGN,
    CONF_SETPOINT_ENTITY,
    CONF_SETPOINT_SIGN,
    CONF_SOC_SENSOR,
    DOMAIN,
    SUBENTRY_BATTERY,
)

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=dt_util.UTC)
GRID = {CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.grid"}
BATTERY_INPUT = {
    CONF_NAME: "Venus",
    CONF_SOC_SENSOR: "sensor.marstek_soc",
    CONF_POWER_SENSOR: "sensor.marstek_power",
    CONF_POWER_SIGN: "discharging_positive",
    CONF_CAPACITY: 5.12,
    CONF_MAX_CHARGE_POWER: 2500,
    CONF_MAX_DISCHARGE_POWER: 800,
    CONF_MIN_SOC: 10,
    CONF_MAX_SOC: 90,
    CONF_EFFICIENCY: 88,
    CONF_FULL_CHARGE_INTERVAL: 14,
}


async def _entry(
    hass: HomeAssistant, data: dict[str, Any] | None = None, battery: bool = True
) -> MockConfigEntry:
    subentries = []
    if battery:
        subentries.append(
            ConfigSubentryData(
                data={**BATTERY_INPUT, CONF_PHASE: "none", CONF_CONTROL_TYPE: "none"},
                subentry_type=SUBENTRY_BATTERY,
                title="Venus",
                unique_id="sensor.marstek_power",
            )
        )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data or GRID,
        options={CONF_HISTORY_INTERVAL: 15},
        subentries_data=subentries,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    (battery_id,) = entry.subentries
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{battery_id}_{key}"
    )
    assert entity_id is not None, key
    return entity_id


def _value(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    return hass.states.get(_entity(hass, entry, key)).state


def _set(hass: HomeAssistant, entity_id: str, value: str, unit: str) -> None:
    hass.states.async_set(entity_id, value, {"unit_of_measurement": unit})


# ---------------------------------------------------------------------------
# Linking (subentry flow)


async def test_add_battery_with_setpoint_and_modes(hass: HomeAssistant) -> None:
    """Battery -> control -> modes; mode options come from the select entity."""
    entry = await _entry(hass, battery=False)
    hass.states.async_set(
        "select.venus_mode",
        "auto",
        {"options": ["auto", "manual_charge", "manual_discharge", "stop"]},
    )

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_BATTERY), context={"source": SOURCE_USER}
    )
    assert result["step_id"] == "user"
    assert CONF_PHASE not in result["data_schema"].schema  # 1-phase connection

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], BATTERY_INPUT
    )
    assert result["step_id"] == "control"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_CONTROL_TYPE: "setpoint",
            CONF_SETPOINT_ENTITY: "number.venus_power",
            CONF_SETPOINT_SIGN: "charging_positive",
            CONF_CHARGE_ENTITY: "number.ignored",  # not for this control type
            CONF_MODE_ENTITY: "select.venus_mode",
        },
    )
    assert result["step_id"] == "modes"
    assert result["data_schema"].schema[CONF_MODE_CHARGE].config["options"] == [
        "auto",
        "manual_charge",
        "manual_discharge",
        "stop",
    ]

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_MODE_CHARGE: "manual_charge",
            CONF_MODE_DISCHARGE: "manual_discharge",
            CONF_MODE_IDLE: "stop",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    (subentry,) = entry.subentries.values()
    assert subentry.title == "Venus"
    assert subentry.data[CONF_CAPACITY] == 5.12
    assert subentry.data[CONF_MAX_CHARGE_POWER] == 2500
    assert subentry.data[CONF_SETPOINT_ENTITY] == "number.venus_power"
    assert CONF_CHARGE_ENTITY not in subentry.data
    assert subentry.data[CONF_MODE_IDLE] == "stop"


@pytest.mark.parametrize(
    ("changes", "errors"),
    [
        ({CONF_SOC_SENSOR: "sensor.grid"}, {CONF_SOC_SENSOR: "sensor_is_phase_sensor"}),
        ({CONF_MIN_SOC: 90, CONF_MAX_SOC: 80}, {CONF_MAX_SOC: "soc_range"}),
        (
            {CONF_POWER_SENSOR: "sensor.marstek_soc"},
            {CONF_POWER_SENSOR: "sensor_in_use"},
        ),
    ],
)
async def test_battery_validation(
    hass: HomeAssistant, changes: dict[str, Any], errors: dict[str, str]
) -> None:
    """Sensors cannot be reused and the SoC range must be valid."""
    entry = await _entry(hass, battery=False)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_BATTERY), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**BATTERY_INPUT, **changes}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors


async def test_separate_control_requires_both_entities(hass: HomeAssistant) -> None:
    """Separate charge/discharge control needs both number entities."""
    entry = await _entry(hass, battery=False)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_BATTERY), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], BATTERY_INPUT
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {CONF_CONTROL_TYPE: "separate", CONF_CHARGE_ENTITY: "number.charge"},
    )
    assert result["errors"] == {CONF_DISCHARGE_ENTITY: "control_entity_required"}

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_CONTROL_TYPE: "separate",
            CONF_CHARGE_ENTITY: "number.charge",
            CONF_DISCHARGE_ENTITY: "number.discharge",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_reconfigure_battery(hass: HomeAssistant) -> None:
    """A battery can be changed; its own sensors may be kept."""
    entry = await _entry(hass)
    (battery_id,) = entry.subentries
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_BATTERY),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": battery_id},
    )
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**BATTERY_INPUT, CONF_CAPACITY: 10.24}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_CONTROL_TYPE: "none"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries[battery_id].data[CONF_CAPACITY] == 10.24


# ---------------------------------------------------------------------------
# Reading and monitoring


async def test_battery_values(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """SoC, normalised power, status and derived energies."""
    freezer.move_to(NOW)
    entry = await _entry(hass)
    assert _value(hass, entry, "battery_soc") == "unavailable"
    assert _value(hass, entry, "battery_capacity") == "5.12"

    # This battery reports discharging as positive: -1000 W means charging.
    _set(hass, "sensor.marstek_soc", "50", "%")
    _set(hass, "sensor.marstek_power", "-1000", "W")
    await hass.async_block_till_done()

    assert float(_value(hass, entry, "battery_power")) == 1000.0
    assert _value(hass, entry, "battery_status") == "charging"
    assert float(_value(hass, entry, "battery_stored_energy")) == 2.56
    assert float(_value(hass, entry, "battery_usable_energy")) == 2.048  # above 10%
    assert float(_value(hass, entry, "battery_room")) == 2.048  # up to 90%
    # 2.048 kWh at 1 kW
    full_at = dt_util.parse_datetime(_value(hass, entry, "battery_time_to_target"))
    expected = NOW + timedelta(hours=2.048)  # 2.048 kWh at 1 kW
    assert abs((full_at - expected).total_seconds()) < 1  # stored in whole seconds

    _set(hass, "sensor.marstek_power", "10", "W")
    await hass.async_block_till_done()
    assert _value(hass, entry, "battery_status") == "idle"

    attrs = hass.states.get(_entity(hass, entry, "battery_status")).attributes
    assert attrs["max_discharge_power"] == 800
    assert attrs["round_trip_efficiency"] == 88

    # The battery is its own device, next to the HomeBatteryAssist device.
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert sorted(d.name for d in devices) == ["HomeBatteryAssist", "Venus"]


async def test_battery_kept_out_of_house_consumption(hass: HomeAssistant) -> None:
    """Charging from the grid is not house consumption; discharging adds to it."""
    entry = await _entry(hass)
    house = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_house_consumption"
    )
    _set(hass, "sensor.grid", "1500", "W")
    _set(hass, "sensor.marstek_soc", "50", "%")
    _set(hass, "sensor.marstek_power", "-1000", "W")  # charging 1000 W
    await hass.async_block_till_done()
    assert float(hass.states.get(house).state) == 500.0

    _set(hass, "sensor.grid", "-200", "W")  # exporting while battery discharges
    _set(hass, "sensor.marstek_power", "800", "W")  # discharging 800 W
    await hass.async_block_till_done()
    assert float(hass.states.get(house).state) == 600.0


async def test_energy_counters_and_full_charge(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Charged/discharged kWh are integrated; a full charge is registered."""
    freezer.move_to(NOW)
    entry = await _entry(hass)
    _set(hass, "sensor.marstek_soc", "95", "%")
    _set(hass, "sensor.marstek_power", "-2000", "W")  # charging
    await hass.async_block_till_done()

    freezer.tick(timedelta(minutes=30))
    _set(hass, "sensor.marstek_soc", "100", "%")
    _set(hass, "sensor.marstek_power", "500", "W")  # discharging
    await hass.async_block_till_done()
    assert float(_value(hass, entry, "battery_charged_energy")) == 1.0

    freezer.tick(timedelta(hours=1))
    _set(hass, "sensor.marstek_power", "0", "W")
    await hass.async_block_till_done()
    assert float(_value(hass, entry, "battery_discharged_energy")) == 0.5

    last_full = hass.states.get(_entity(hass, entry, "battery_last_full_charge"))
    assert dt_util.parse_datetime(last_full.state) == NOW + timedelta(minutes=30)
    assert last_full.attributes["interval_days"] == 14
    assert last_full.attributes["due"] is False
    decisions = entry.runtime_data.decisions
    assert decisions.latest["key"] == "battery_full_charge"

    # Counters survive a reload.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert float(_value(hass, entry, "battery_charged_energy")) == 1.0


async def test_totals(hass: HomeAssistant) -> None:
    """Totals over all batteries on the main device."""
    entry = await _entry(hass)
    _set(hass, "sensor.marstek_soc", "40", "%")
    _set(hass, "sensor.marstek_power", "0", "W")
    await hass.async_block_till_done()
    registry = er.async_get(hass)

    def total(key: str) -> str:
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_{key}"
        )
        return hass.states.get(entity_id).state

    assert float(total("batteries_soc")) == 40.0
    assert float(total("batteries_stored_energy")) == 2.048
    assert float(total("batteries_capacity")) == 5.12


async def test_no_battery_no_totals(hass: HomeAssistant) -> None:
    """Without batteries there are no battery totals."""
    entry = await _entry(hass, battery=False)
    assert (
        er.async_get(hass).async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_batteries_soc"
        )
        is None
    )
