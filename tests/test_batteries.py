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
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.homebatteryassist.const import (
    CONF_CAPACITY,
    CONF_EFFICIENCY,
    CONF_FULL_CHARGE_INTERVAL,
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_CURRENT,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_PHASE,
    CONF_PHASES,
    CONF_POWER_SENSOR,
    CONF_POWER_SIGN,
    CONF_SOC_SENSOR,
    CONF_SOURCE,
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
                data={**BATTERY_INPUT, CONF_PHASE: "none"},
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


@pytest.mark.frozen_grid
async def test_frozen_battery_power_counts_as_unknown(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A battery power sensor frozen at a real power makes the house
    consumption unknown; frozen near 0 W (idle) it is left alone."""
    house = "sensor.homebatteryassist_house_consumption"
    entry = await _entry(hass)
    measurements = entry.runtime_data.measurements

    def report(battery: str | None) -> None:
        hass.states.async_set("sensor.grid", "500", {"unit_of_measurement": "W"})
        if battery is not None:
            hass.states.async_set(
                "sensor.marstek_power", battery, {"unit_of_measurement": "W"}
            )

    report("800")  # discharging
    hass.states.async_set("sensor.marstek_soc", "50", {"unit_of_measurement": "%"})
    freezer.tick(timedelta(minutes=3))  # past the start-up quiet time
    report("800")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert float(hass.states.get(house).state) == 1300.0
    freezer.tick(timedelta(seconds=100))
    report(None)  # the grid keeps reporting, the battery does not
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(house).state == "unavailable"
    assert measurements.stale == ["sensor.marstek_power"]
    report("0")  # idle now
    freezer.tick(timedelta(seconds=100))
    report(None)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert measurements.stale == []
    assert float(hass.states.get(house).state) == 500.0


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


async def test_add_battery_manually(hass: HomeAssistant) -> None:
    """Without detected batteries the flow goes straight to the battery form."""
    entry = await _entry(hass, battery=False)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_BATTERY), context={"source": SOURCE_USER}
    )
    assert result["step_id"] == "battery"
    assert CONF_PHASE not in result["data_schema"].schema  # 1-phase connection

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], BATTERY_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()  # the entry reloads with the battery
    (subentry,) = entry.subentries.values()
    assert subentry.title == "Venus"
    assert subentry.data[CONF_CAPACITY] == 5.12
    assert subentry.data[CONF_MAX_CHARGE_POWER] == 2500
    assert not any("control" in key or "entity" in key for key in subentry.data)


def _omnibattery_device(hass: HomeAssistant, phases: int = 3) -> None:
    """Entities as the Omnibattery integration creates them for a Venus E v3."""
    owner = MockConfigEntry(domain="omnibattery")
    owner.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=owner.entry_id,
        identifiers={("omnibattery", "venus1")},
        name="Marstek Venus 1",
        manufacturer="Marstek",
        model="Venus E v3",
    )
    registry = er.async_get(hass)
    for domain, key, state, unit in (
        ("sensor", "battery_soc", "12", "%"),
        ("sensor", "ac_power", "0", "W"),
        ("sensor", "battery_total_energy", "5.12", "kWh"),
        ("sensor", "round_trip_efficiency_total", "84.72", "%"),
        ("number", "max_charge_power", "2500.0", "W"),
        ("number", "max_discharge_power", "2500.0", "W"),
        ("number", "charging_cutoff_capacity", "100.0", "%"),
        ("number", "discharging_cutoff_capacity", "12.0", "%"),
        ("select", "battery_phase", "l3", None),
    ):
        entity = registry.async_get_or_create(
            domain,
            "omnibattery",
            f"venus1_{key}",
            config_entry=owner,
            device_id=device.id,
            translation_key=key,
            suggested_object_id=f"marstek_venus_1_{key}",
        )
        hass.states.async_set(
            entity.entity_id, state, {"unit_of_measurement": unit} if unit else {}
        )


async def test_add_detected_omnibattery(hass: HomeAssistant) -> None:
    """A battery of Omnibattery is offered with all values prefilled."""
    _omnibattery_device(hass)
    entry = await _entry(
        hass,
        {
            CONF_PHASES: 3,
            CONF_MAX_CURRENT: 25,
            "sensor_l1": "sensor.l1",
            "sensor_l2": "sensor.l2",
            "sensor_l3": "sensor.l3",
        },
        battery=False,
    )
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_BATTERY), context={"source": SOURCE_USER}
    )
    assert result["step_id"] == "user"
    options = result["data_schema"].schema[CONF_SOURCE].config["options"]
    assert options[0]["label"] == "Marstek Venus 1 - Venus E v3 (Omnibattery)"
    assert options[-1]["value"] == "manual"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_SOURCE: options[0]["value"]}
    )
    assert result["step_id"] == "battery"
    suggested = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }
    assert suggested == {
        CONF_NAME: "Marstek Venus 1",
        CONF_SOC_SENSOR: "sensor.marstek_venus_1_battery_soc",
        CONF_POWER_SENSOR: "sensor.marstek_venus_1_ac_power",
        CONF_POWER_SIGN: "discharging_positive",
        CONF_CAPACITY: 5.12,
        CONF_MAX_CHARGE_POWER: 2500,
        CONF_MAX_DISCHARGE_POWER: 2500,
        CONF_MIN_SOC: 12,
        CONF_MAX_SOC: 100,
        CONF_EFFICIENCY: 85,
        CONF_PHASE: "l3",
    }

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**suggested, CONF_FULL_CHARGE_INTERVAL: 7}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    # Our battery device shows the real battery's make and model.
    (battery_id,) = entry.subentries
    device = next(
        d
        for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
        if (DOMAIN, battery_id) in d.identifiers
    )
    assert (device.manufacturer, device.model) == ("Marstek", "Venus E v3 (read-only)")

    # Once linked, the battery is no longer offered.
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_BATTERY), context={"source": SOURCE_USER}
    )
    assert result["step_id"] == "battery"


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
    assert result["step_id"] == "battery"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**BATTERY_INPUT, **changes}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors


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
    assert (
        float(_value(hass, entry, "battery_usable_energy")) == 2.05
    )  # above 10% (to 10 Wh)
    assert float(_value(hass, entry, "battery_room")) == 2.05  # up to 90%
    # 2.048 kWh at 1 kW
    full_at = dt_util.parse_datetime(_value(hass, entry, "battery_time_to_target"))
    expected = NOW + timedelta(hours=2.048)  # 2.048 kWh at 1 kW
    assert abs((full_at - expected).total_seconds()) < 60  # to the minute

    _set(hass, "sensor.marstek_power", "10", "W")
    await hass.async_block_till_done()
    assert _value(hass, entry, "battery_status") == "idle"

    attrs = hass.states.get(_entity(hass, entry, "battery_status")).attributes
    assert attrs["max_discharge_power"] == 800
    assert attrs["round_trip_efficiency"] == 88

    # The battery is its own device, next to the HomeBatteryAssist device.
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert sorted(d.name for d in devices) == [
        "Grid connection",
        "HomeBatteryAssist",
        "Venus",
    ]

    # Its problem sensor (does not follow its command), on the same device.
    (battery_id,) = entry.subentries
    problem = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{battery_id}_battery_not_following"
    )
    assert problem is not None
    assert hass.states.get(problem).state == "off"

    # The test control: on the battery's device, switched off in this phase.
    registry = er.async_get(hass)
    for domain, key in (
        ("button", "control_test_charge"),
        ("button", "control_test_discharge"),
        ("button", "control_test_stop"),
        ("number", "control_test_power"),
        ("number", "control_test_minutes"),
        ("sensor", "control_test_status"),
    ):
        assert registry.async_get_entity_id(domain, DOMAIN, f"{battery_id}_{key}"), key
    status = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{battery_id}_control_test_status"
    )
    assert hass.states.get(status).state == "read_only"


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


async def test_activity_explained(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """What a real battery does by itself is explained as periods: since when,
    with what and until when, next to the plan; when it stops, the period it
    ran. Short swings are not explained."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    freezer.move_to(NOW)  # 13:00 local
    entry = await _entry(hass)
    batteries = entry.runtime_data.batteries
    batteries.planned_now = lambda: 0.0
    batteries.expected_until = lambda battery_id, activity: {
        "discharging": (NOW + timedelta(hours=3), "empty"),
        "idle": (NOW + timedelta(hours=20), "resume_charging"),
    }.get(activity)
    log = entry.runtime_data.decisions

    class _Latest:
        """The latest battery decision (forecast cycles may log in between)."""

        @property
        def latest(self) -> dict:
            return next(
                (d for d in reversed(log.entries) if d["category"] == "battery"),
                {},
            )

    decisions = _Latest()

    async def later(minutes: int) -> None:
        freezer.tick(timedelta(minutes=minutes))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    _set(hass, "sensor.grid", "0", "W")
    _set(hass, "sensor.marstek_soc", "50", "%")
    _set(hass, "sensor.marstek_power", "0", "W")  # first state
    await hass.async_block_till_done()
    # After start-up, what the battery does is told once, a minute later.
    await later(1)
    assert decisions.latest["key"] == "battery_now_idle"
    assert decisions.latest["message"] == (
        "Venus is idle now; solar power covers the house, expected until about "
        "17-11 09:00, when it charges again. That matches the plan."
    )
    before = decisions.latest

    # A short swing (2 minutes) is not explained.
    _set(hass, "sensor.marstek_power", "800", "W")  # discharging
    await hass.async_block_till_done()
    await later(2)
    _set(hass, "sensor.marstek_power", "0", "W")
    await hass.async_block_till_done()
    await later(6)
    assert decisions.latest == before

    # Lasting discharging (from 13:09), while the plan said idle.
    _set(
        hass, "sensor.marstek_power", "460", "W"
    )  # 0.46-0.51 kWh: one rounding either way
    await hass.async_block_till_done()
    await later(6)
    assert decisions.latest["key"] == "battery_discharging"
    assert decisions.latest["message"] == (
        "Since 13:09 Venus has been supplying the house, so less power comes from "
        "the grid, expected until about 16:00, when it is empty. The plan said: "
        "neither charge nor supply now. The battery follows its own control; "
        "HomeBatteryAssist only advises."
    )

    # It stops at 14:09 at its lower limit: the period is summed up, and the
    # idle period that follows is explained (the house runs on the grid).
    await later(54)
    _set(hass, "sensor.grid", "400", "W")
    _set(hass, "sensor.marstek_soc", "10", "%")
    _set(hass, "sensor.marstek_power", "0", "W")
    await hass.async_block_till_done()
    await later(6)
    assert decisions.latest["key"] == "battery_stopped_discharging"
    assert decisions.latest["message"] == (
        "Venus supplied power from 13:09 to 14:09: 0.5 kWh — it is empty "
        "(set lower limit). Now it is idle and the house runs on the grid, "
        "expected until about 17-11 09:00, when it charges again. That matches "
        "the plan."
    )

    # Charging from the grid, as planned.
    batteries.planned_now = lambda: 1000.0
    _set(hass, "sensor.grid", "1500", "W")
    _set(hass, "sensor.marstek_power", "-1200", "W")
    await hass.async_block_till_done()
    await later(6)
    assert decisions.latest["message"] == (
        "Since 14:15 Venus has been charging with power from the grid. "
        "That matches the plan."
    )


async def test_battery_meter(hass: HomeAssistant) -> None:
    """An external meter on the battery's line gives the battery's power
    (+ into the battery = charging) instead of its power sensor."""
    from unittest.mock import patch

    from custom_components.homebatteryassist.const import (
        CONF_BATTERY_METER,
        CONF_BATTERY_METER_ADDRESS,
    )
    from custom_components.homebatteryassist.engine.measure.battery_monitor import (
        battery_power,
    )

    async def read(_hass, _address):
        return {"active_power_l1_w": 750.0}  # 750 W into the battery

    with patch(
        "custom_components.homebatteryassist.engine.devices.meters.homewizard.read_homewizard",
        read,
    ):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=GRID,
            options={CONF_HISTORY_INTERVAL: 15},
            subentries_data=[
                ConfigSubentryData(
                    data={
                        **BATTERY_INPUT,
                        CONF_PHASE: "none",
                        CONF_BATTERY_METER: "homewizard",
                        CONF_BATTERY_METER_ADDRESS: "192.0.2.50",
                    },
                    subentry_type=SUBENTRY_BATTERY,
                    title="Venus",
                    unique_id="sensor.marstek_power",
                )
            ],
        )
        entry.add_to_hass(hass)
        _set(hass, "sensor.marstek_soc", "50", "%")
        _set(hass, "sensor.marstek_power", "-100", "W")  # sensor says otherwise
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        (config,) = entry.runtime_data.batteries.configs
        assert config.meter_driver == "homewizard"
        assert battery_power(hass, config) == 750.0
        state = entry.runtime_data.batteries.states[config.id]
        assert state.power_w == 750.0
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
    # Without the meter the power sensor counts again.
    assert battery_power(hass, config) == 100.0
