"""Tests for the Huawei SUN2000 + LUNA2000 direct driver (prepared, not
used)."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.homebatteryassist.engine.devices.batteries.direct.modbus_driver import (
    blocks,
)
from custom_components.homebatteryassist.engine.devices.batteries.huawei import (
    modbus as huawei,
)
from custom_components.homebatteryassist.engine.devices.batteries.huawei.sun2000_direct_modbus import (
    HuaweiModbusDriver,
)


def u32(address: int, value: int) -> dict[int, int]:
    """A 32-bit value as two registers, high word first."""
    value &= 0xFFFFFFFF
    return {address: value >> 16, address + 1: value & 0xFFFF}


class FakeClient:
    """Records every request; answers holding reads from a register dict."""

    def __init__(self, holding: dict[int, int]) -> None:
        self.holding = holding
        self.calls: list[tuple] = []
        self.connected = True
        self.connect = AsyncMock()

    async def read_holding(self, address: int, count: int) -> list[int]:
        self.calls.append(("read3", address, count))
        return [self.holding.get(address + i, 0) for i in range(count)]

    async def read_input(self, address: int, count: int) -> list[int]:
        raise AssertionError("input registers get no answer")

    async def write_register(self, address: int, value: int) -> None:
        raise AssertionError("Huawei writes with FC16 only")

    async def write_registers(self, address: int, values: list[int]) -> None:
        self.calls.append(("write16", address, list(values)))


def driver_with(
    hass: HomeAssistant, holding: dict[int, int] | None = None
) -> tuple[HuaweiModbusDriver, FakeClient]:
    driver = HuaweiModbusDriver(hass, "192.0.2.20")
    client = FakeClient(holding or {})
    driver.client = client  # type: ignore[assignment]
    return driver, client


REGISTERS = {
    37000: 2,  # running
    **u32(37001, -1500),  # discharging
    37003: 4500,
    37004: 0xFFFF,  # SoC not available
    **u32(37015, 1234),
    37022: 0x7FFF,  # temperature not available
    **u32(37046, 7000),
    **u32(37048, 0xFFFFFFFF),  # not available
    **u32(37066, 250000),
    **u32(37758, 13800),
    **u32(30075, 8800),
    **u32(32003, 1),  # off-grid now
    **u32(32064, 0x7FFFFFFF),  # PV not available
    **u32(32080, 3000),
    47000: 2,
    47081: 1000,
    47082: 2500,  # 250 %: a decode fault
    47086: 2,
    47100: 2,
    **u32(47249, 2000),
}


async def test_reading(hass: HomeAssistant) -> None:
    """Registers become a reading; "not available" markers and implausible
    values are dropped, not scaled."""
    driver, client = driver_with(hass, REGISTERS)
    reading = await driver.async_read()
    assert reading.soc is None
    assert reading.power_w == -1500
    assert reading.telemetry.voltage_v == 450.0
    assert reading.telemetry.temperature_c is None
    assert reading.telemetry.charged_today_kwh == 12.34
    extra = reading.extra
    assert extra["status"] == "discharging"
    assert extra["max_charge_w"] == 7000
    assert "max_discharge_w" not in extra
    assert "pv_power_w" not in extra
    assert extra["charged_total_kwh"] == 2500.0
    assert extra["capacity_kwh"] == 13.8
    assert extra["charge_cutoff_soc"] == 100.0
    assert "discharge_cutoff_soc" not in extra
    assert extra["working_mode_name"] == "max_self_consumption"
    assert extra["storage_type_name"] == "luna2000"
    assert extra["forcible_setpoint_w"] == -2000
    assert extra["off_grid"] is True
    assert extra["off_grid_power_w"] == 3000
    assert extra["discharge_headroom_w"] == 7300  # 8800 - (3000 - 1500)
    assert {c[0] for c in client.calls} == {"read3"}


def test_status_deadband(hass: HomeAssistant) -> None:
    """Running near 0 W is idle (the inverter idles at about +50 W)."""
    driver, _ = driver_with(hass)
    assert driver.reading({"status": 2, "power_w": 50}).extra["status"] == "idle"
    assert driver.reading({"status": 2, "power_w": 900}).extra["status"] == ("charging")
    assert driver.reading({"status": 0}).extra["status"] == "offline"


def test_blocks_never_cross_gaps() -> None:
    planned = blocks(HuaweiModbusDriver.points, HuaweiModbusDriver.max_block)
    assert {f for f, _, _ in planned} == {3}
    assert (3, 37000, 5) in planned  # 37000-37004
    assert (3, 47246, 5) in planned  # 47246-47250
    covered = {a for _, start, count in planned for a in range(start, start + count)}
    assert 37014 not in covered  # alarm: not validated
    assert 37026 not in covered  # answers with an exception


async def test_disabled_driver_does_not_connect(hass: HomeAssistant) -> None:
    driver, client = driver_with(hass)
    with pytest.raises(RuntimeError, match="not enabled"):
        await driver.async_open()
    with pytest.raises(RuntimeError, match="not enabled"):
        await driver.async_set_power(1000)
    with pytest.raises(RuntimeError, match="not enabled"):
        await driver.async_release()
    assert client.calls == []
    client.connect.assert_not_called()


async def test_open_waits_after_connect(hass: HomeAssistant) -> None:
    """The inverter drops a request that comes too soon after connecting."""
    driver, client = driver_with(hass)
    driver.enabled = True  # instance only; never in the code
    with patch.object(huawei.asyncio, "sleep", AsyncMock()) as sleep:
        await driver.async_open()
    client.connect.assert_awaited_once()
    sleep.assert_awaited_once_with(1.5)


async def test_set_power_sequence(hass: HomeAssistant) -> None:
    """Power, duration, target, and the mode register LAST; clamped to the
    live limit (a higher value would be refused)."""
    driver, client = driver_with(hass, {**u32(37046, 3000), **u32(37048, 5000)})
    driver.enabled = True
    await driver.async_set_power(5000)
    assert client.calls == [
        ("read3", 37046, 4),
        ("write16", 47247, [0, 3000]),
        ("write16", 47083, [10]),
        ("write16", 47246, [0]),
        ("write16", 47100, [1]),
    ]
    client.calls.clear()
    await driver.async_set_power(-1000, duration_min=30)
    assert client.calls == [
        ("read3", 37046, 4),
        ("write16", 47249, [0, 1000]),
        ("write16", 47083, [30]),
        ("write16", 47246, [0]),
        ("write16", 47100, [2]),
    ]
    with pytest.raises(ValueError):
        await driver.async_set_power(1000, duration_min=0)


async def test_release_sequence(hass: HomeAssistant) -> None:
    """Stop FIRST, then clear the parameters; 0 W is a release too."""
    driver, client = driver_with(hass)
    driver.enabled = True
    release = [
        ("write16", 47100, [0]),
        ("write16", 47249, [0, 0]),
        ("write16", 47083, [0]),
        ("write16", 47246, [0]),
    ]
    await driver.async_release()
    assert client.calls == release
    client.calls.clear()
    await driver.async_set_power(0)
    assert client.calls == release
