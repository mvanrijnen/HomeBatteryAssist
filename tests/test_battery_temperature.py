"""Observations of what a battery can do at its temperature."""

from datetime import UTC, datetime, timedelta

from custom_components.homebatteryassist.engine.devices.batteries import (
    BatteryCommand,
)
from custom_components.homebatteryassist.engine.evaluation.battery_temperature import (
    BatteryTemperature,
    band_of,
)
from custom_components.homebatteryassist.engine.measure.battery_monitor import (
    BatteryConfig,
)

T0 = datetime(2026, 11, 22, 3, 0, tzinfo=UTC)
LOOK = timedelta(seconds=15)
CONFIG = BatteryConfig(
    id="b1",
    name="Venus",
    soc_sensor="sensor.venus_battery_soc",
    power_sensor="sensor.venus_ac_power",
    power_sign="discharging_positive",
    capacity_kwh=5.12,
    max_charge_w=2500,
    max_discharge_w=2500,
    min_soc=12,
    max_soc=100,
    efficiency=0.85,
    full_charge_interval_days=0,
    phase="l1",
)


def _looks(battery, start, count, command, soc, power, temp, outdoor=None):
    for i in range(count):
        battery.observe(start + i * LOOK, CONFIG, command, soc, power, temp, outdoor)


def test_bands():
    assert band_of(1.9) == 0
    assert band_of(-0.5) == -2
    assert band_of(13.0) == 12


def test_limited_in_the_cold_counted_per_band():
    battery = BatteryTemperature()
    _looks(battery, T0, 5, BatteryCommand(2000), 50.0, 600.0, 1.0)
    _looks(battery, T0 + 5 * LOOK, 5, BatteryCommand(2000), 50.0, 1990.0, 13.0)
    rows = {r["from_c"]: r for r in battery.summary()["charge"]}
    # The first look has no earlier command to compare with.
    assert rows[0.0]["looks"] == 4 and rows[0.0]["limited_pct"] == 100
    assert rows[0.0]["limited_w"] == 600
    assert rows[12.0]["limited_pct"] == 0 and rows[12.0]["max_w"] == 1990.0


def test_not_counted_when_it_is_not_the_temperature():
    battery = BatteryTemperature()
    # Nearly full, switched off, small command, a changing command.
    _looks(battery, T0, 4, BatteryCommand(2000), 97.0, 300.0, 1.0)
    _looks(battery, T0, 4, BatteryCommand(2000, charge_allowed=False), 50.0, 0.0, 1.0)
    _looks(battery, T0, 4, BatteryCommand(80), 50.0, 0.0, 1.0)
    for i, watts in enumerate((500, 1000, 1500, 2000)):
        battery.observe(T0 + i * LOOK, CONFIG, BatteryCommand(watts), 50.0, 100.0, 1.0)
    # Nearly empty when discharging.
    _looks(battery, T0, 4, BatteryCommand(-800), 15.0, -100.0, 1.0)
    assert battery.summary()["charge"] == []
    assert battery.summary()["discharge"] == []


def test_hours_with_outdoor_temperature_and_energy():
    battery = BatteryTemperature()
    _looks(battery, T0, 240, None, 50.0, 1000.0, 10.0, 4.0)  # one hour
    battery.observe(T0 + timedelta(hours=1, seconds=5), CONFIG, None, 50.0, 0.0, 9.0)
    assert len(battery.hours) == 1
    hour = battery.hours[0]
    assert hour["temp_c"] == 10.0 and hour["outdoor_c"] == 4.0
    assert abs(hour["kwh"] - 1.0) < 0.01
    again = BatteryTemperature.from_dict(battery.as_dict())
    assert again.hours == battery.hours and again.bands == battery.bands
