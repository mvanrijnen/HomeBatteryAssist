"""Tests for the twin of a real battery: a virtual copy planned in its place."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.homebatteryassist.const import (
    CONF_CAPACITY,
    CONF_EFFICIENCY,
    CONF_FULL_CHARGE_INTERVAL,
    CONF_HISTORY_INTERVAL,
    CONF_INITIAL_SOC,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_CURRENT,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_PHASES,
    CONF_POWER_SENSOR,
    CONF_POWER_SIGN,
    CONF_SOC_SENSOR,
    CONF_TWIN_OF,
    DOMAIN,
    SUBENTRY_BATTERY,
    SUBENTRY_VIRTUAL_BATTERY,
)
from custom_components.homebatteryassist.engine.devices.batteries.virtual import (
    without_batteries,
)
from custom_components.homebatteryassist.engine.measure.house_measurement import (
    PowerFlow,
)

REAL = {
    CONF_NAME: "Venus",
    CONF_SOC_SENSOR: "sensor.venus_soc",
    CONF_POWER_SENSOR: "sensor.venus_power",
    CONF_POWER_SIGN: "charging_positive",
    CONF_CAPACITY: 5.12,
    CONF_MAX_CHARGE_POWER: 2500,
    CONF_MAX_DISCHARGE_POWER: 800,
    CONF_MIN_SOC: 10,
    CONF_MAX_SOC: 100,
    CONF_EFFICIENCY: 100,  # no loss: predictable numbers
    CONF_FULL_CHARGE_INTERVAL: 0,
}
TWIN = {
    CONF_NAME: "Venus (virtueel)",
    CONF_TWIN_OF: "real1",
    # Its own properties are not used: the real battery's are.
    CONF_CAPACITY: 1.0,
    CONF_MAX_CHARGE_POWER: 100,
    CONF_MAX_DISCHARGE_POWER: 100,
    CONF_MIN_SOC: 0,
    CONF_MAX_SOC: 100,
    "loss_min": 20,
    "loss_max": 20,
    "full_charge_interval_days": 0,
    CONF_INITIAL_SOC: 50,
}


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    hass.states.async_set("sensor.grid", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.venus_soc", "40", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.venus_power", "0", {"unit_of_measurement": "W"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.grid"},
        options={CONF_HISTORY_INTERVAL: 15},
        subentries_data=[
            {
                "data": REAL,
                "subentry_id": "real1",
                "subentry_type": SUBENTRY_BATTERY,
                "title": "Venus",
                "unique_id": "sensor.venus_power",
            },
            {
                "data": TWIN,
                "subentry_id": "twin1",
                "subentry_type": SUBENTRY_VIRTUAL_BATTERY,
                "title": "Venus (virtueel)",
                "unique_id": None,
            },
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _value(hass: HomeAssistant, battery_id: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{battery_id}_{key}"
    )
    return hass.states.get(entity_id).state


async def test_twin_copies_and_replaces_the_real_battery(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The twin has the real battery's properties, starts at its state of
    charge, is planned in its place and acts on the grid without it."""
    entry = await _setup(hass)
    batteries = entry.runtime_data.batteries
    twin = next(c for c in batteries.configs if c.id == "twin1")
    assert twin.twin_of == "real1"
    assert (twin.capacity_kwh, twin.max_discharge_w, twin.efficiency) == (
        5.12,
        800,
        1.0,
    )
    assert float(_value(hass, "twin1", "battery_soc")) == 40.0
    assert [s.config.id for s in batteries.plan_states()] == ["twin1"]

    # The real battery charges 1000 W from the sun, so the meter shows 0 W:
    # without it there is 1000 W surplus, and the twin charges that.
    hass.states.async_set("sensor.venus_power", "1000", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    for _ in range(4):
        freezer.tick(timedelta(seconds=30))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert float(_value(hass, "twin1", "battery_power")) == 1000.0

    device = next(
        d
        for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
        if (DOMAIN, "twin1") in d.identifiers
    )
    assert device.model == "Twin of Venus (simulation)"
    assert _value(hass, "twin1", "twin_difference_today") is not None


async def test_sync_twin_with_the_real_battery(hass: HomeAssistant) -> None:
    """*Sync with the real battery* copies its state of charge, told in *Why*."""
    entry = await _setup(hass)
    hass.states.async_set("sensor.venus_soc", "80", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    button = er.async_get(hass).async_get_entity_id("button", DOMAIN, "twin1_twin_sync")
    await hass.services.async_call(
        "button", "press", {"entity_id": button}, blocking=True
    )
    await hass.async_block_till_done()
    assert float(_value(hass, "twin1", "battery_soc")) == 80.0
    decisions = entry.runtime_data.decisions
    assert any(e["key"] == "twin_synced" for e in decisions.entries)


async def test_one_twin_per_real_battery(hass: HomeAssistant) -> None:
    """A real battery can have only one twin."""
    entry = await _setup(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_VIRTUAL_BATTERY), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**TWIN, CONF_NAME: "Tweede"}
    )
    assert result["errors"] == {CONF_TWIN_OF: "twin_taken"}


def test_without_batteries() -> None:
    """The flow without a battery: grid and its phase less its power."""
    flow = PowerFlow(
        grid_w=0.0,
        pv_w=2000.0,
        excluded_w=0.0,
        battery_w=900.0,
        house_w=1100.0,
        phase_w=(300.0, -300.0, 0.0),
        phase_a=(1.3, 1.3, 0.0),
    )
    out = without_batteries(flow, [(1, 900.0)])
    assert out.grid_w == -900.0
    assert out.battery_w == 0.0
    assert out.phase_w == (300.0, -1200.0, 0.0)
    assert out.phase_a == ()
    spread = without_batteries(flow, [(None, 900.0)])
    assert spread.phase_w == (0.0, -600.0, -300.0)
    assert without_batteries(flow, [(1, 0.0)]) is flow
