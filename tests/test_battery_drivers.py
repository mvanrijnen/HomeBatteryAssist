"""Tests for the battery drivers (reading only)."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist.engine.drivers.batteries import (
    DRIVERS,
    driver_for,
    telemetry,
)
from custom_components.homebatteryassist.engine.drivers.batteries.template import (
    TemplateBatteryDriver,
)
from custom_components.homebatteryassist.engine.inputs.batteries import BatteryConfig


def test_template_not_registered() -> None:
    assert not any(isinstance(d, TemplateBatteryDriver) for d in DRIVERS)


async def test_marstek_modbus_telemetry(hass: HomeAssistant) -> None:
    """Details are read from the sensors on the battery's device."""
    source = MockConfigEntry(domain="marstek_modbus")
    source.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=source.entry_id, identifiers={("marstek_modbus", "v1")}
    )
    registry = er.async_get(hass)
    values = {
        "battery_soc": "55",
        "max_cell_temperature": "21.5",
        "battery_voltage": "52.3",
        "min_cell_voltage": "3.267",
        "max_cell_voltage": "3.274",
        "battery_cycle_count": "9",
        "total_daily_charging_energy": "1.08",
        "total_daily_discharging_energy": "0.8",
        "round_trip_efficiency_total": "84.7",
    }
    for key, value in values.items():
        entry = registry.async_get_or_create(
            "sensor",
            "marstek_modbus",
            f"v1_{key}",
            device_id=device.id,
            translation_key=key,
            suggested_object_id=f"venus_{key}",
        )
        hass.states.async_set(entry.entity_id, value)
    config = BatteryConfig(
        id="b1",
        name="Venus",
        soc_sensor="sensor.venus_battery_soc",
        power_sensor="sensor.x",
        power_sign="charging_positive",
        capacity_kwh=5.12,
        max_charge_w=2500,
        max_discharge_w=2500,
        min_soc=12,
        max_soc=100,
        efficiency=0.85,
        full_charge_interval_days=0,
        phase="l3",
    )
    assert driver_for(hass, config).key == "marstek_modbus"
    details = telemetry(hass, config).as_dict()
    assert details["temperature_c"] == 21.5
    assert details["cycles"] == 9
    assert details["discharged_today_kwh"] == 0.8
    assert details["efficiency_pct"] == 84.7
