"""Tests for the Marstek Venus direct drivers (prepared, not used)."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.homebatteryassist.engine.devices.batteries.direct.modbus import (
    blocks,
)
from custom_components.homebatteryassist.engine.devices.batteries.marstek import (
    modbus as marstek,
)
from custom_components.homebatteryassist.engine.devices.batteries.marstek.modbus import (
    MarstekVenusAModbus,
    MarstekVenusDModbus,
    MarstekVenusEV2Modbus,
    MarstekVenusEV3Modbus,
)
from custom_components.homebatteryassist.engine.devices.transports.modbus_tcp import (
    ModbusError,
)

DRIVERS = (
    MarstekVenusEV2Modbus,
    MarstekVenusEV3Modbus,
    MarstekVenusAModbus,
    MarstekVenusDModbus,
)


class FakeClient:
    """Registers as a dict; reads of an undefined register are refused like
    the firmware does (Modbus exception for the whole request)."""

    def __init__(self, registers: dict[int, int] | None = None) -> None:
        self.registers = registers if registers is not None else {}
        self.reads: list[tuple[int, int]] = []
        self.writes: list[tuple[int, int]] = []
        self.refuse: set[tuple[int, int]] = set()  # (start, count) refused

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def read_holding(self, address: int, count: int) -> list[int]:
        self.reads.append((address, count))
        span = range(address, address + count)
        if (address, count) in self.refuse or any(
            a not in self.registers for a in span
        ):
            raise ModbusError("exception code 2")
        return [self.registers[a] for a in span]

    async def write_register(self, address: int, value: int) -> None:
        self.writes.append((address, value))
        self.registers[address] = value


@pytest.fixture(autouse=True)
def no_wait(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Skip the driver's pauses; record them."""
    waits: list[float] = []

    async def wait(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(marstek, "_wait", wait)
    return waits


def driver_with(cls: type, hass: HomeAssistant, registers: dict[int, int]):
    driver = cls(hass, "192.0.2.10")
    driver.client = FakeClient(registers)
    return driver


def s16(value: int) -> int:
    return value & 0xFFFF


def s32(value: int) -> tuple[int, int]:
    value &= 0xFFFFFFFF
    return value >> 16, value & 0xFFFF


COMMON = {
    32105: 5120,  # 5.12 kWh
    35000: s16(-25),  # -2.5 °C
    35100: 3,  # discharging
    37007: 3350,
    37008: 3310,
    33000: 0,
    33001: 50000,  # 500.00 kWh charged
    33002: 0,
    33003: 45000,  # 450.00 kWh discharged
    41200: 1,
    42000: 0x55BB,
    42010: 2,
    42020: 0,
    42021: 800,
    44002: 2500,
    44003: 2500,
}


def test_drivers_disabled_and_unverified() -> None:
    for cls in DRIVERS:
        assert not cls.enabled
        assert not cls.verified
        assert cls.can_write
        assert "Omnibattery" in cls.source
        assert cls.models and cls.key and cls.name
        assert {p.function for p in cls.points} == {3}  # holding registers only
        names = [p.name for p in cls.points]
        assert len(names) == len(set(names))
        assert "soc" in names and "power_w" in names


async def test_disabled_driver_refuses_open(hass: HomeAssistant) -> None:
    for cls in DRIVERS:
        driver = driver_with(cls, hass, {})
        with pytest.raises(RuntimeError, match="not enabled"):
            await driver.async_open()
        assert driver.client.reads == []


def test_connection_details() -> None:
    assert MarstekVenusEV2Modbus.timeout == 10.0
    assert MarstekVenusEV2Modbus.pause == 0.05
    for cls in (MarstekVenusEV3Modbus, MarstekVenusAModbus):
        assert cls.timeout == 3.0
    assert MarstekVenusDModbus.timeout == 6.0
    for cls in DRIVERS[1:]:
        assert cls.pause == 0.15
    for cls in DRIVERS:
        assert (cls.port, cls.unit, cls.max_block) == (502, 1, 125)


def test_blocks_v2() -> None:
    """Only adjacent registers together; never across a gap."""
    assert blocks(MarstekVenusEV2Modbus.points, 125) == [
        (3, 32100, 1),
        (3, 32102, 4),  # battery power (2) + SoC + capacity
        (3, 32202, 2),
        (3, 32302, 2),
        (3, 33000, 4),
        (3, 35000, 1),
        (3, 35100, 1),
        (3, 36000, 2),
        (3, 36100, 2),
        (3, 37007, 2),
        (3, 41200, 1),
        (3, 42000, 1),
        (3, 42010, 1),
        (3, 42020, 2),
        (3, 44000, 4),  # safe on v2
    ]


def test_blocks_v3() -> None:
    assert blocks(MarstekVenusEV3Modbus.points, 125) == [
        (3, 30001, 1),
        (3, 30006, 1),
        (3, 30100, 1),
        (3, 32105, 1),
        (3, 32302, 1),
        (3, 33000, 4),
        (3, 34003, 1),
        (3, 34009, 1),
        (3, 35000, 1),
        (3, 35100, 1),
        (3, 37005, 1),
        (3, 37007, 2),
        (3, 41200, 1),
        (3, 42000, 1),
        (3, 42010, 1),
        (3, 42020, 2),
        (3, 44002, 2),
    ]


def test_blocks_venus_a_d() -> None:
    expected = [
        (3, 30001, 1),
        (3, 30006, 1),
        (3, 30037, 4),  # MPPT 1-4
        (3, 30100, 1),
        (3, 32104, 2),
        (3, 32110, 1),
        (3, 32302, 1),
        (3, 33000, 4),
        (3, 34003, 1),
        (3, 35000, 1),
        (3, 35100, 1),
        (3, 37007, 2),
        (3, 41200, 1),
        (3, 42000, 1),
        (3, 42010, 2),  # force mode + charge-to-SoC
        (3, 42020, 2),
        (3, 44002, 2),
    ]
    assert blocks(MarstekVenusAModbus.points, 125) == expected
    vd = blocks(MarstekVenusDModbus.points, 125)
    assert vd == sorted([*expected, (3, 30200, 1)], key=lambda b: b[1])


async def test_v2_reading(hass: HomeAssistant) -> None:
    """32-bit words (high first), signs and scales; + charging."""
    registers = {
        **COMMON,
        32100: 5230,
        32102: s32(-1210)[0],
        32103: s32(-1210)[1],
        32104: 64,
        32202: s32(1200)[0],  # AC + delivering on the wire
        32203: s32(1200)[1],
        32302: 0,
        32303: 0,
        36000: 0x0001,
        36001: 0x0002,
        36100: 0,
        36101: 0,
        44000: 1000,
        44001: 150,
    }
    driver = driver_with(MarstekVenusEV2Modbus, hass, registers)
    reading = await driver.async_read()
    assert reading.soc == 64
    assert reading.power_w == -1200  # discharging
    assert reading.extra["battery_power_w"] == -1210
    assert reading.telemetry.voltage_v == 52.3
    assert reading.telemetry.temperature_c == -2.5
    assert reading.telemetry.cell_max_v == 3.35
    assert reading.telemetry.cell_min_v == 3.31
    assert reading.telemetry.efficiency_pct == 90.0
    assert reading.telemetry.cycles == round(475 / 5.12, 1)  # calculated on v2
    assert reading.extra["charged_total_kwh"] == 500.0
    assert reading.extra["capacity_kwh"] == 5.12
    assert reading.extra["alarms"] == 0x00010002
    assert reading.extra["charge_cutoff_pct"] == 100.0
    assert reading.extra["discharge_cutoff_pct"] == 15.0
    assert reading.extra["status"] == "discharging"
    assert reading.extra["discharge_setpoint_w"] == 800


async def test_v3_reading(hass: HomeAssistant) -> None:
    registers = {
        **COMMON,
        37005: 81,
        30001: 950,  # battery side, + charging
        30006: s16(-1000),  # AC side, - = charging
        30100: 5150,
        32302: 0,
        34003: 123,
        34009: 1,
        35100: 2,
    }
    driver = driver_with(MarstekVenusEV3Modbus, hass, registers)
    reading = await driver.async_read()
    assert reading.soc == 81
    assert reading.power_w == 1000  # charging
    assert reading.extra["battery_power_w"] == 950
    assert reading.telemetry.cycles == 123  # read, not calculated
    assert reading.extra["balancing"] == 1
    assert reading.extra["status"] == "charging"


async def test_venus_d_reading_and_ceiling(hass: HomeAssistant) -> None:
    registers = {
        **COMMON,
        32104: 40,
        30001: 0,
        30006: 300,
        30037: 1234,
        30038: 0,
        30039: 0,
        30040: 0,
        30100: 5000,
        30200: 150,
        32110: 0b111,
        32302: 0,
        34003: 7,
        42011: 100,
    }
    driver = driver_with(MarstekVenusDModbus, hass, registers)
    assert driver.ceiling_w() == 2200  # EMS version unknown
    reading = await driver.async_read()
    assert reading.power_w == -300
    assert reading.extra["mppt1_w"] == 123.4
    assert reading.extra["packs_online"] == 3
    assert driver.ceiling_w() == 2500
    registers[30200] = 148
    await driver.async_read()
    assert driver.ceiling_w() == 2200


async def test_refused_block_read_point_by_point(hass: HomeAssistant) -> None:
    """A refused block is read point by point, now and later; a point the
    firmware lacks is left out instead of failing the reading."""
    registers = {**COMMON, 37005: 50, 30001: 0, 30006: 0, 30100: 5000, 32302: 0}
    registers.pop(44003)
    driver = driver_with(MarstekVenusEV3Modbus, hass, registers)
    reading = await driver.async_read()
    assert "max_discharge_w" not in reading.extra
    assert reading.extra["max_charge_w"] == 2500
    assert reading.telemetry.cycles == round(475 / 5.12, 1)  # calculated
    reads = driver.client.reads
    assert reads.count((44002, 2)) == 1
    assert (44002, 1) in reads and (44003, 1) in reads
    reads.clear()
    await driver.async_read()
    assert (44002, 2) not in reads


async def test_timeout_is_not_a_refusal(hass: HomeAssistant) -> None:
    driver = driver_with(MarstekVenusEV3Modbus, hass, {})

    async def timeout(address: int, count: int) -> list[int]:
        raise ModbusError("192.0.2.10: TimeoutError")

    driver.client.read_holding = timeout
    with pytest.raises(ModbusError):
        await driver.async_read()


async def test_counter_noise_dropped(hass: HomeAssistant) -> None:
    registers = {**COMMON, 37005: 50, 30001: 0, 30006: 0, 30100: 5000, 32302: 0}
    driver = driver_with(MarstekVenusEV3Modbus, hass, registers)
    assert (await driver.async_read()).extra["charged_total_kwh"] == 500.0
    registers[33001] = 10000  # 100 kWh: partial value
    registers[33003] = 0
    reading = await driver.async_read()
    assert "charged_total_kwh" not in reading.extra
    assert "discharged_total_kwh" not in reading.extra
    registers[33001] = 50100
    assert (await driver.async_read()).extra["charged_total_kwh"] == 501.0


@pytest.mark.parametrize(
    ("cls", "power", "writes"),
    [
        (
            MarstekVenusEV3Modbus,
            1000.4,
            [(42000, 0x55AA), (42021, 0), (42020, 1000), (42010, 1)],
        ),
        (
            MarstekVenusEV2Modbus,
            -3000,
            [(42000, 0x55AA), (42021, 2500), (42020, 0), (42010, 2)],
        ),
        (
            MarstekVenusAModbus,
            -3000,
            [(42000, 0x55AA), (42021, 1500), (42020, 0), (42010, 2)],
        ),
        (
            MarstekVenusDModbus,
            5000,
            [(42000, 0x55AA), (42021, 0), (42020, 2200), (42010, 1)],
        ),
        (
            MarstekVenusEV3Modbus,
            0,
            [(42000, 0x55AA), (42021, 0), (42020, 0), (42010, 0)],
        ),
    ],
)
async def test_set_power_writes(
    hass: HomeAssistant, cls: type, power: float, writes: list
) -> None:
    """RS485 on, then discharge, charge, force mode — in that order."""
    driver = driver_with(cls, hass, {})
    await driver.async_set_power(power)
    assert driver.client.writes == writes


async def test_rs485_enabled_once_per_connection(hass: HomeAssistant) -> None:
    driver = driver_with(MarstekVenusEV3Modbus, hass, {})
    await driver.async_set_power(500)
    await driver.async_set_power(-500)
    assert [w for w in driver.client.writes if w[0] == 42000] == [(42000, 0x55AA)]
    await driver.async_close()
    driver.client.writes.clear()
    await driver.async_set_power(500)
    assert driver.client.writes[0] == (42000, 0x55AA)


async def test_release_writes(hass: HomeAssistant, no_wait: list[float]) -> None:
    """Standby (discharge, charge, force), RS485 off, then close."""
    driver = driver_with(MarstekVenusEV3Modbus, hass, {41200: 1})
    await driver.async_release()
    assert driver.client.writes == [
        (42021, 0),
        (42020, 0),
        (42010, 0),
        (42000, 0x55BB),
    ]
    assert no_wait == [0.05, 0.05, 0.05, 0.1]
    assert driver._closed_at is not None


async def test_release_with_backup_load(hass: HomeAssistant) -> None:
    """Backup on (41200 = 0) with load on the backup port, or unknown: the
    battery is left alone."""
    for registers in (
        {41200: 0, 32302: 120},
        {41200: 0},  # load unknown
        {},  # backup function unknown
    ):
        driver = driver_with(MarstekVenusEV3Modbus, hass, registers)
        await driver.async_release()
        assert driver.client.writes == []
    driver = driver_with(MarstekVenusEV2Modbus, hass, {41200: 0, 32302: 0, 32303: 30})
    await driver.async_release()
    assert driver.client.writes[-1] == (42000, 0x55BB)
