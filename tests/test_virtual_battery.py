"""Tests for virtual (simulated) batteries."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_USER, ConfigSubentryData
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.homebatteryassist.const import (
    CONF_CAPACITY,
    CONF_HISTORY_INTERVAL,
    CONF_INITIAL_SOC,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_CURRENT,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_PHASES,
    DOMAIN,
    SUBENTRY_VIRTUAL_BATTERY,
)

VIRTUAL = {
    CONF_NAME: "Extra",
    CONF_CAPACITY: 5.0,
    CONF_MAX_CHARGE_POWER: 2000,
    CONF_MAX_DISCHARGE_POWER: 2000,
    CONF_MIN_SOC: 10,
    CONF_MAX_SOC: 100,
    "loss_min": 0,  # no loss: predictable numbers
    "loss_max": 0,
    "full_charge_interval_days": 0,  # no forced full charge in these tests
    CONF_INITIAL_SOC: 50,
}


async def _setup(hass: HomeAssistant, virtual: bool = True) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.grid"},
        options={CONF_HISTORY_INTERVAL: 15},
        subentries_data=[
            ConfigSubentryData(
                data=VIRTUAL,
                subentry_type=SUBENTRY_VIRTUAL_BATTERY,
                title="Extra",
                unique_id=None,
            )
        ]
        if virtual
        else [],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_add_virtual_battery(hass: HomeAssistant) -> None:
    """A virtual battery is added with its properties; no sensors needed."""
    entry = await _setup(hass, virtual=False)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_VIRTUAL_BATTERY), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**VIRTUAL, CONF_MIN_SOC: 90, CONF_MAX_SOC: 80}
    )
    assert result["errors"] == {CONF_MAX_SOC: "soc_range"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**VIRTUAL, "loss_min": 20, "loss_max": 10}
    )
    assert result["errors"] == {"loss_max": "loss_range"}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], VIRTUAL
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()  # the entry reloads with the battery


async def test_virtual_battery_follows_nom(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """NOM: it absorbs the real export and is never part of house consumption."""
    entry = await _setup(hass)
    (battery_id,) = entry.subentries
    registry = er.async_get(hass)

    def value(key: str) -> str:
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{battery_id}_{key}"
        )
        return hass.states.get(entity_id).state

    assert float(value("battery_soc")) == 50.0
    house = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_house_consumption"
    )
    hass.states.async_set("sensor.grid", "-1000", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert float(hass.states.get(house).state) == 0.0  # untouched by the simulation

    # One hour of steps, 1000 W export -> +1 kWh = +20 % of 5 kWh.
    for _ in range(120):
        freezer.tick(timedelta(seconds=30))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert float(value("battery_power")) == 1000.0
    soc = float(value("battery_soc"))
    assert abs(soc - 70.0) < 0.2  # one step more or less
    assert float(value("battery_charged_energy")) >= 0.98

    device = next(
        d
        for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
        if (DOMAIN, battery_id) in d.identifiers
    )
    assert device.model == "Virtual battery (simulation)"
    # No totals of real batteries.
    assert (
        registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_batteries_soc"
        )
        is None
    )

    # It survives a restart of the integration with its state of charge.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert float(value("battery_soc")) == soc


def test_random_loss_within_range() -> None:
    """Each step loses a random share between the minimum and maximum."""
    from types import SimpleNamespace

    from custom_components.homebatteryassist.engine.batteries.virtual import (
        limit_power,
        random_efficiency,
    )

    config = SimpleNamespace(
        capacity_kwh=10.0,
        max_charge_w=5000,
        max_discharge_w=5000,
        min_soc=0.0,
        max_soc=100.0,
        efficiency=0.85,
        loss_min=0.10,
        loss_max=0.20,
    )
    for _ in range(50):
        eff = random_efficiency(config)
        assert 0.80 <= eff <= 0.90
        _, soc = limit_power(config, 50.0, 1000.0, 1.0, eff)
        # 1 kWh in at sqrt(eff) one way: between +0.89 and +0.95 kWh stored
        assert 58.9 <= soc <= 59.5
