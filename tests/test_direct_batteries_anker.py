"""Tests for the Anker SOLIX direct driver (prepared, not used)."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.homebatteryassist.engine.devices.batteries.anker import (
    solarbank_direct_modbus as anker,
)
from custom_components.homebatteryassist.engine.devices.batteries.anker.solarbank_direct_modbus import (
    AnkerModbusDriver,
    product_code,
)
from custom_components.homebatteryassist.engine.devices.batteries.direct.modbus_driver import (
    blocks,
)

# The vendor's batch ranges (inclusive) per function code.
RANGES = {
    4: [(10000, 10050), (10090, 10156), (10208, 10265), (32768, 32774)],
    3: [(10060, 10072), (10074, 10081), (60000, 60003)],
}


def s32(address: int, value: int) -> dict[int, int]:
    """A 32-bit value as two registers, high word first."""
    value &= 0xFFFFFFFF
    return {address: value >> 16, address + 1: value & 0xFFFF}


class FakeClient:
    """Records every request; answers from register dicts per function."""

    def __init__(self, holding: dict[int, int], inputs: dict[int, int]) -> None:
        self.registers = {3: holding, 4: inputs}
        self.calls: list[tuple] = []
        self.connected = True
        self.connect = AsyncMock()

    async def _read(self, function: int, address: int, count: int) -> list[int]:
        self.calls.append((f"read{function}", address, count))
        return [self.registers[function].get(address + i, 0) for i in range(count)]

    async def read_holding(self, address: int, count: int) -> list[int]:
        return await self._read(3, address, count)

    async def read_input(self, address: int, count: int) -> list[int]:
        return await self._read(4, address, count)

    async def write_register(self, address: int, value: int) -> None:
        self.calls.append(("write6", address, value))

    async def write_registers(self, address: int, values: list[int]) -> None:
        self.calls.append(("write16", address, list(values)))


def driver_with(
    hass: HomeAssistant,
    holding: dict[int, int] | None = None,
    inputs: dict[int, int] | None = None,
    **options,
) -> tuple[AnkerModbusDriver, FakeClient]:
    driver = AnkerModbusDriver(hass, "192.0.2.10", **options)
    client = FakeClient(holding or {}, inputs or {})
    driver.client = client  # type: ignore[assignment]
    return driver, client


INPUTS = {
    10001: 1,  # charging
    **s32(10002, 1200),
    **s32(10004, 0),
    **s32(10008, -800),  # - = charging on the wire
    **s32(10012, -150),
    10014: 56,
    10015: 0,  # SoH unknown
    **s32(10036, 0),  # not reported
    **s32(10038, 2400),
    10156: 235,
    **s32(10250, 52),
    **s32(10262, 123456),
    32774: 0b100001,
}
HOLDING = {10064: 3, 60000: 95, 60001: 10}


async def test_reading(hass: HomeAssistant) -> None:
    """Registers become a reading: + charging, scales, 32-bit words, and
    "unknown" zeros dropped."""
    driver, client = driver_with(hass, HOLDING, INPUTS)
    reading = await driver.async_read()
    assert reading.soc == 56
    assert reading.power_w == 800  # charging
    assert reading.telemetry.temperature_c == 23.5
    extra = reading.extra
    assert extra["status"] == "charging"
    assert extra["grid_power_w"] == -150
    assert extra["charged_total_kwh"] == 12345.6
    assert extra["rated_energy_kwh"] == 5.2
    assert "soh_pct" not in extra
    assert "max_charge_w" not in extra
    assert extra["max_discharge_w"] == 2400
    assert extra["mode_name"] == "third_party"
    assert extra["supported_modes"] == ["self_consumption", "third_party"]
    assert extra["charge_limit_soc"] == 95
    assert "pv_power_w" not in extra  # AC model: not an independent PV value
    # Only FC03 / FC04 reads, never 0x8007, all inside the vendor's ranges
    assert {c[0] for c in client.calls} == {"read3", "read4"}
    for name, start, count in client.calls:
        assert not start <= 32775 < start + count
        ranges = RANGES[int(name[-1])]
        assert any(lo <= start and start + count - 1 <= hi for lo, hi in ranges)


async def test_reading_dc_coupled(hass: HomeAssistant) -> None:
    """E5000 Pro: own PV, and the AC side is pack power minus PV."""
    driver, _ = driver_with(hass, HOLDING, INPUTS, dc_coupled=True)
    reading = await driver.async_read()
    assert reading.extra["pv_power_w"] == 1200
    assert reading.extra["ac_power_w"] == -400  # exporting while the pack charges


def test_blocks_never_cross_gaps() -> None:
    """Block planning follows the register map without filling gaps."""
    planned = blocks(AnkerModbusDriver.points, AnkerModbusDriver.max_block)
    assert (4, 10001, 5) in planned  # 10001-10005
    assert (4, 10008, 8) in planned  # 10008-10015
    assert (3, 60000, 4) in planned
    assert all(start + count - 1 != 32775 for _, start, count in planned)


def test_product_code() -> None:
    assert product_code("A17C5 DMWH") == "DMWH"
    assert product_code("generic", "AK7DN7M0G22") == "DN7M"
    assert product_code("unknown") is None


async def test_disabled_driver_does_not_connect(hass: HomeAssistant) -> None:
    driver, client = driver_with(hass)
    with pytest.raises(RuntimeError, match="not enabled"):
        await driver.async_open()
    with pytest.raises(RuntimeError, match="not enabled"):
        await driver.async_set_power(100)
    with pytest.raises(RuntimeError, match="not enabled"):
        await driver.async_release()
    assert client.calls == []
    client.connect.assert_not_called()


async def test_reconnect_waits(hass: HomeAssistant) -> None:
    """After a lost connection the device gets 0.7 s before a request."""
    driver, client = driver_with(hass, HOLDING, INPUTS)
    client.connected = False
    with patch.object(anker.asyncio, "sleep", AsyncMock()) as sleep:
        await driver.async_read()
    client.connect.assert_awaited_once()
    sleep.assert_awaited_once_with(0.7)


async def test_set_power_sequence(hass: HomeAssistant) -> None:
    """Mode 3 first (FC06, only when needed), then the 32-bit set-point with
    FC16, + discharging on the wire, clamped to the continuous power."""
    driver, client = driver_with(
        hass, {10064: 0}, {**s32(10036, 7000), **s32(10038, 0)}
    )
    driver.enabled = True  # instance only; never in the code
    await driver.async_set_power(5000)  # charge
    assert client.calls == [
        ("read4", 10036, 4),
        ("read3", 10064, 1),
        ("write6", 10064, 3),
        ("write16", 10071, [0xFFFF, 0xF254]),  # -3500
    ]
    client.calls.clear()
    client.registers[3][10064] = 3
    await driver.async_set_power(-1000)  # discharge, already in mode 3
    assert client.calls == [
        ("read4", 10036, 4),
        ("read3", 10064, 1),
        ("write16", 10071, [0, 1000]),
    ]


async def test_release_sequence(hass: HomeAssistant) -> None:
    """Set-point 0 first, then the mode to return to."""
    driver, client = driver_with(hass, release_mode=1)
    driver.enabled = True
    await driver.async_release()
    assert client.calls == [("write16", 10071, [0, 0]), ("write6", 10064, 1)]
