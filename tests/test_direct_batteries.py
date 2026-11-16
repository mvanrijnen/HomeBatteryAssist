"""Tests for the direct battery drivers (prepared, not used)."""

import pytest
from homeassistant.core import HomeAssistant

from custom_components.homebatteryassist.engine.devices.batteries import (
    DIRECT_DRIVERS,
    model_for,
)
from custom_components.homebatteryassist.engine.devices.batteries.direct.modbus import (
    Point,
    blocks,
)
from custom_components.homebatteryassist.engine.devices.batteries.hoymiles.mqtt import (
    HoymilesMqttDriver,
)


def test_direct_drivers_disabled() -> None:
    """No direct driver is enabled: none may open a connection."""
    assert DIRECT_DRIVERS
    assert not any(d.enabled for d in DIRECT_DRIVERS)


async def test_disabled_driver_does_not_connect(hass: HomeAssistant) -> None:
    driver = HoymilesMqttDriver(hass, "MSA-280024341346")
    with pytest.raises(RuntimeError, match="not enabled"):
        await driver.async_open()


def test_modbus_blocks() -> None:
    """Consecutive points are read together; never across a gap (some devices
    refuse reads of undefined registers) or beyond the block size."""
    points = (
        Point("a", 100),
        Point("b", 101, "u32"),
        Point("c", 110),
        Point("d", 300),
        Point("e", 5, function=4),
    )
    assert blocks(points, 60) == [(3, 100, 3), (3, 110, 1), (3, 300, 1), (4, 5, 1)]
    assert blocks(points, 2) == [
        (3, 100, 1),
        (3, 101, 2),
        (3, 110, 1),
        (3, 300, 1),
        (4, 5, 1),
    ]


def test_hoymiles_reading(hass: HomeAssistant) -> None:
    """MQTT payloads become a reading: + charging, system values first."""
    driver = HoymilesMqttDriver(hass, "MSA-1")
    quick, device, system, limits = driver.topics()
    reading = driver.reading(
        {
            quick: {"sys_soc": "56", "sys_bat_p": 800, "bat_sts": "Discharge"},
            device: {"bat_v": 51.2, "bat_temp": 22, "pack_num": 2},
            system: {"chg_e": 1500, "dchg_e": "900", "ems_mode": "general"},
            limits: {"min": -1000, "max": 2000, "device": {"model": "MS-A2"}},
        }
    )
    assert reading.soc == 56
    assert reading.power_w == -800  # discharging
    assert reading.telemetry.charged_today_kwh == 1.5
    assert reading.extra["status"] == "discharging"
    assert reading.extra["max_charge_w"] == 1000
    assert model_for(reading.extra["model"]).type == "MS-A2"
