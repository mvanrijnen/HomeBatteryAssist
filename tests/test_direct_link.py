"""A battery's direct connection (DirectLink) end to end: a fake Marstek Venus
E v3 answering Modbus TCP frames, read through the real client and driver,
used by BatteryInput's reading and controlled by the test control."""

from __future__ import annotations

import asyncio
import struct
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.const import DIRECT_LINKS_KEY
from custom_components.homebatteryassist.engine.control.control_test import (
    ControlTest,
)
from custom_components.homebatteryassist.engine.devices.batteries import (
    command,
    direct_driver,
)
from custom_components.homebatteryassist.engine.devices.batteries.direct import link
from custom_components.homebatteryassist.engine.devices.batteries.direct.link import (
    DirectLink,
)
from custom_components.homebatteryassist.engine.devices.batteries.marstek import (
    venus_direct_modbus as marstek,
)
from custom_components.homebatteryassist.engine.measure.battery_monitor import (
    BatteryConfig,
    BatteryState,
    read_battery,
)

MODBUS = "custom_components.homebatteryassist.engine.devices.transports.modbus_tcp"

CONFIG = BatteryConfig(
    id="b1",
    name="Venus",
    soc_sensor="",
    power_sensor="",
    power_sign="charging_positive",
    capacity_kwh=5.12,
    max_charge_w=2500,
    max_discharge_w=2500,
    min_soc=12,
    max_soc=100,
    efficiency=0.85,
    full_charge_interval_days=0,
    phase="l3",
    direct_driver="marstek_venus_e_v3_modbus",
    direct_address="192.0.2.158",
)


class FakeVenus:
    """A Venus E v3 on Modbus TCP: holding registers; a read that touches an
    undefined register is refused as a whole (exception 2, with the v3's
    wrong length); writes to 42000 / 42010 / 42020 / 42021 drive it."""

    def __init__(self) -> None:
        self.registers: dict[int, int] = {
            37005: 13,  # SoC %
            34009: 0,
            30001: 0,
            30006: 0,
            32302: 0,
            30100: 5320,
            34003: 13,
            32105: 5120,
            35000: 180,  # 18.0 °C
            35100: 1,
            37007: 3300,
            37008: 3290,
            33000: 0,
            33001: 50000,
            33002: 0,
            33003: 45000,
            41200: 1,  # backup function off
            42000: 0x55BB,
            42010: 0,
            42020: 0,
            42021: 0,
            44002: 2500,
            44003: 2500,
        }
        self.writes: list[tuple[int, int]] = []
        self.connects = 0
        self.down = False

    def follow(self) -> None:
        """The battery does what the registers say (power on the AC side)."""
        controlled = self.registers[42000] == 0x55AA
        force = self.registers[42010] if controlled else 0
        watts = (
            self.registers[42020]
            if force == 1
            else -self.registers[42021]
            if force == 2
            else 0
        )
        self.registers[30001] = watts & 0xFFFF
        self.registers[30006] = (-watts) & 0xFFFF  # + delivering on the wire

    def answer(self, frame: bytes) -> bytes:
        transaction, _p, length, unit = struct.unpack(">HHHB", frame[:7])
        pdu = frame[7 : 6 + length]
        function = pdu[0]
        if function == 3:
            address, count = struct.unpack(">HH", pdu[1:5])
            span = range(address, address + count)
            if any(a not in self.registers for a in span):
                reply = bytes([0x83, 2])
                return struct.pack(">HHHB", transaction, 0, 4, unit) + reply
            values = [self.registers[a] for a in span]
            reply = bytes([3, 2 * count]) + struct.pack(f">{count}H", *values)
        elif function == 6:
            address, value = struct.unpack(">HH", pdu[1:5])
            self.writes.append((address, value))
            self.registers[address] = value
            self.follow()
            reply = pdu
        else:
            reply = bytes([function | 0x80, 1])
        return struct.pack(">HHHB", transaction, 0, len(reply) + 1, unit) + reply


class _Writer:
    def __init__(self, device: FakeVenus, reader: asyncio.StreamReader) -> None:
        self._device, self._reader, self._closed = device, reader, False

    def write(self, data: bytes) -> None:
        self._reader.feed_data(self._device.answer(data))

    async def drain(self) -> None:
        return None

    def is_closing(self) -> bool:
        return self._closed

    def close(self) -> None:
        self._closed = True

    async def wait_closed(self) -> None:
        return None


@pytest.fixture
def venus():
    """The fake battery behind every Modbus TCP connection; no pauses."""
    fake = FakeVenus()

    async def open_connection(host, port):
        if fake.down:
            raise OSError("connection refused")
        fake.connects += 1
        reader = asyncio.StreamReader()
        return reader, _Writer(fake, reader)

    async def no_wait(seconds: float) -> None:
        return None

    with (
        patch(f"{MODBUS}.asyncio.open_connection", open_connection),
        patch.object(marstek, "_wait", no_wait),
        patch.object(marstek.MarstekVenusModbus, "pause", 0.0),
    ):
        yield fake


def _link(hass: HomeAssistant) -> DirectLink:
    cls = direct_driver(CONFIG.direct_driver)
    assert cls is not None and not cls.enabled  # off until a battery chooses it
    driver = cls(hass, CONFIG.direct_address, port=502, unit=1)
    return DirectLink(hass, CONFIG.id, CONFIG.name, driver)


async def test_reads_the_battery(hass: HomeAssistant, venus: FakeVenus) -> None:
    link_ = _link(hass)
    await link_.async_start()
    try:
        assert link_.state == link.STATE_CONNECTED
        assert link_.soc == 13
        assert link_.power_w == 0
        # BatteryInput's reading takes it from the link (no sensors at all).
        state = read_battery(hass, CONFIG)
        assert state.soc == 13 and state.power_w == 0
        details = link_.as_dict()
        assert details["temperature_c"] == 18.0
        assert details["status"] == "standby"
        # RS485 control off: the battery follows its own logic.
        assert command(hass, CONFIG) is None
    finally:
        await link_.async_stop()
    assert DIRECT_LINKS_KEY not in hass.data or "b1" not in hass.data[DIRECT_LINKS_KEY]
    assert link_.state == link.STATE_STOPPED


async def test_charge_discharge_and_release(
    hass: HomeAssistant, venus: FakeVenus
) -> None:
    link_ = _link(hass)
    await link_.async_start()
    try:
        await link_.async_set_power(800)
        assert venus.writes == [(42000, 0x55AA), (42021, 0), (42020, 800), (42010, 1)]
        await link_._async_poll(dt_util.utcnow())
        assert link_.power_w == 800  # + charging
        assert command(hass, CONFIG).power_w == 800
        venus.writes.clear()
        await link_.async_set_power(-300)
        assert venus.writes == [(42021, 300), (42020, 0), (42010, 2)]  # once: RS485
        await link_._async_poll(dt_util.utcnow())
        assert link_.power_w == -300
        assert command(hass, CONFIG).power_w == -300
        venus.writes.clear()
        await link_.async_release()
        assert venus.writes == [(42021, 0), (42020, 0), (42010, 0), (42000, 0x55BB)]
        assert not link_.controlled
        # The release closed the connection (single slot): the next poll
        # opens it again.
        connects = venus.connects
        await link_._async_poll(dt_util.utcnow())
        assert venus.connects == connects + 1 and link_.power_w == 0
    finally:
        await link_.async_stop()


async def test_stop_releases_a_controlled_battery(
    hass: HomeAssistant, venus: FakeVenus
) -> None:
    link_ = _link(hass)
    await link_.async_start()
    await link_.async_set_power(500)
    await link_.async_stop()
    assert venus.registers[42000] == 0x55BB and venus.registers[42010] == 0


async def test_backs_off_when_the_battery_is_unreachable(
    hass: HomeAssistant, venus: FakeVenus
) -> None:
    venus.down = True
    link_ = _link(hass)
    await link_.async_start()
    try:
        assert link_.state == link.STATE_ERROR and link_.error
        assert read_battery(hass, CONFIG).soc is None
        # Polls during the back-off do not reconnect.
        now = dt_util.utcnow()
        venus.down = False
        await link_._async_poll(now + timedelta(seconds=1))
        assert venus.connects == 0
        await link_._async_poll(now + timedelta(seconds=6))
        assert venus.connects == 1 and link_.state == link.STATE_CONNECTED
    finally:
        await link_.async_stop()


class FakeLog:
    def __init__(self) -> None:
        self.keys: list = []

    def async_log(self, category, key, **params) -> None:
        self.keys.append((key, params))


async def test_control_test_goes_through_the_link(
    hass: HomeAssistant, venus: FakeVenus
) -> None:
    link_ = _link(hass)
    await link_.async_start()
    log = FakeLog()
    batteries = SimpleNamespace(
        configs=[CONFIG],
        states={"b1": BatteryState(CONFIG, 13.0, 0.0)},
        stats={"b1": {"charged_kwh": 1.0, "discharged_kwh": 0.5}},
    )
    test = ControlTest(hass, batteries, log, allowed=True)
    try:
        assert test.status("b1") == "ready"
        test.power_w["b1"] = 800
        await test.async_start("b1", charge=True)
        assert test.status("b1") == "charging"
        assert venus.registers[42010] == 1 and venus.registers[42020] == 800
        started = dict(log.keys)["control_test_started"]
        assert started["integration"] == "Marstek Venus E v3 (Modbus TCP)"
        await test.async_stop("b1")
        assert venus.registers[42000] == 0x55BB and venus.registers[42010] == 0
        assert test.status("b1") == "ready"
    finally:
        await test.async_stop_all()
        await link_.async_stop()


async def test_control_test_off_sends_nothing(
    hass: HomeAssistant, venus: FakeVenus
) -> None:
    link_ = _link(hass)
    await link_.async_start()
    log = FakeLog()
    batteries = SimpleNamespace(
        configs=[CONFIG],
        states={"b1": BatteryState(CONFIG, 50.0, 0.0)},
        stats={"b1": {}},
    )
    test = ControlTest(hass, batteries, log)
    try:
        await test.async_start("b1", charge=True)
        assert venus.writes == []
        assert log.keys[-1][0] == "control_test_blocked"
    finally:
        await link_.async_stop()


async def test_an_earlier_refusal_does_not_stop_a_new_test(
    hass: HomeAssistant, venus: FakeVenus
) -> None:
    """A discharge test the battery refused leaves the command check's
    problem behind; the next test starts over instead of stopping at once."""
    from custom_components.homebatteryassist.engine.evaluation.command_check import (
        CommandCheck,
    )

    link_ = _link(hass)
    await link_.async_start()
    check = CommandCheck()
    check.event = SimpleNamespace(reason=None, start=dt_util.utcnow())
    assert check.problem
    log = FakeLog()
    batteries = SimpleNamespace(
        configs=[CONFIG],
        states={"b1": BatteryState(CONFIG, 40.0, 0.0)},
        stats={"b1": {}},
    )
    test = ControlTest(
        hass,
        batteries,
        log,
        commands=SimpleNamespace(checks={"b1": check}),
        allowed=True,
    )
    try:
        await test.async_start("b1", charge=True)
        await test._async_tick(dt_util.utcnow())
        assert test.status("b1") == "charging"
        assert not check.problem
    finally:
        await test.async_stop_all()
        await link_.async_stop()
