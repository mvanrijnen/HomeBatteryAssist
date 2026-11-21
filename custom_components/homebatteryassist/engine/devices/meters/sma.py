"""SMA Sunny Home Manager 2.0 / Energy Meter: the Speedwire telegrams the
meter multicasts on the network anyway. Only received; nothing is ever sent
to the meter. Verified.

Decoding of SMA Speedwire energy meter telegrams (Home Manager, Energy Meter).

An SMA Home Manager 2.0 / Energy Meter sends its measurements about once a
second as a UDP multicast to 239.12.255.254:9522, for SMA inverters and
batteries on the network. Receiving them is passive: nothing is sent to the
meter and nothing changes for the other listeners.

Telegram layout (big endian):

    0   "SMA\\0"
    4   tag 0x02A0 (group), group number
    12  length of the data, tag 0x0010
    16  protocol id 0x6069 (energy meter), SUSy id (2), serial (4), ticker ms (4)
    28  OBIS records: channel, index, type, tariff (1 byte each), value

``type`` 4 = actual value (4 bytes), 8 = counter (8 bytes). Active power is
in 0.1 W, counters in Ws. Indexes: 1/2 = total import/export, 21/22 = L1,
41/42 = L2, 61/62 = L3 (import/export); per phase also current (31/51/71, mA),
voltage (32/52/72, mV) and power factor (33/53/73, 0.001), when the meter
sends them. Record 0x90000000 holds the software version (4 bytes).
"""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from .direct_reading import SOURCE_SPEEDWIRE, DirectMeter

_LOGGER = logging.getLogger(__name__)


GROUP = "239.12.255.254"
PORT = 9522
PROTOCOL_EMETER = 0x6069

# index of import power per phase (export = index + 1)
PHASE_INDEX = (21, 41, 61)
CURRENT_INDEX = (31, 51, 71)  # mA
VOLTAGE_INDEX = (32, 52, 72)  # mV
FACTOR_INDEX = (33, 53, 73)  # 0.001


@dataclass(frozen=True, slots=True)
class MeterTelegram:
    """One energy meter measurement."""

    serial: int
    susy_id: int
    ticker_ms: int
    power_w: float  # total, + import / - export
    phase_w: tuple[float, float, float]  # per phase, + import / - export
    phase_a: tuple[float, ...] | None = None  # current per phase (A), if sent
    phase_v: tuple[float, ...] | None = None  # voltage per phase (V), if sent
    phase_pf: tuple[float, ...] | None = None  # power factor per phase, if sent


def decode(data: bytes) -> MeterTelegram | None:
    """Decode a telegram; None if it is not an energy meter telegram."""
    if len(data) < 32 or data[:4] != b"SMA\x00":
        return None
    length = struct.unpack_from(">H", data, 12)[0]
    if struct.unpack_from(">H", data, 16)[0] != PROTOCOL_EMETER:
        return None
    susy_id, serial, ticker = struct.unpack_from(">HII", data, 18)
    end = min(16 + length, len(data))
    pos = 28
    actual: dict[int, float] = {}
    while pos + 4 <= end:
        channel, index, kind, _tariff = data[pos : pos + 4]
        pos += 4
        if channel == 0x90:  # software version
            pos += 4
            continue
        if kind == 4:
            if pos + 4 > end:
                break
            actual[index] = struct.unpack_from(">I", data, pos)[0]
            pos += 4
        elif kind == 8:
            pos += 8
        elif channel == 0 and index == 0 and kind == 0:
            break  # end marker
        else:
            return None  # unknown record: do not guess
    if 1 not in actual or not all(i in actual for i in PHASE_INDEX):
        return None
    phases = tuple(
        round((actual[i] - actual.get(i + 1, 0.0)) / 10, 1) for i in PHASE_INDEX
    )

    def per_phase(indexes: tuple[int, ...], scale: float) -> tuple[float, ...] | None:
        if not all(i in actual for i in indexes):
            return None
        return tuple(round(actual[i] / scale, 3) for i in indexes)

    return MeterTelegram(
        serial,
        susy_id,
        ticker,
        round((actual[1] - actual.get(2, 0.0)) / 10, 1),
        phases,  # type: ignore[arg-type]
        per_phase(CURRENT_INDEX, 1000),
        per_phase(VOLTAGE_INDEX, 1000),
        per_phase(FACTOR_INDEX, 1000),
    )


RETRY_S = 60  # seconds between attempts to join the multicast group


class _SpeedwireProtocol(asyncio.DatagramProtocol):
    def __init__(self, handler: Callable[[bytes, str], None]) -> None:
        self._handler = handler

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        self._handler(data, addr[0])


def _multicast_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(("", PORT))
        membership = struct.pack(
            "4s4s", socket.inet_aton(GROUP), socket.inet_aton("0.0.0.0")
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        sock.setblocking(False)
    except OSError:
        sock.close()  # the network is not ready: no socket left behind
        raise
    return sock


class SpeedwireMeter(DirectMeter):
    """Receives the multicast telegrams of one SMA Home Manager / Energy Meter.

    The meter is known by its **serial number** (``address`` = the serial):
    every telegram carries it, so a new IP address (DHCP) changes nothing.
    An older setting with an IP address still works: the serial is learned
    from the first telegram from that address and handed to ``on_serial``
    (which stores it in the setting instead).
    """

    label = SOURCE_SPEEDWIRE

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Initialize; ``address`` is the meter's serial (or an IP address)."""
        super().__init__(hass, address)
        self._transport: asyncio.DatagramTransport | None = None
        self._retry: Callable[[], None] | None = None
        self._stopped = False
        text = str(address).strip()
        self._serial: int | None = int(text) if text.isdigit() else None
        self.host: str | None = None if text.isdigit() else text
        # Called once with the serial learned for an IP address setting.
        self.on_serial: Callable[[int], None] | None = None

    @property
    def serial(self) -> int | None:
        """The meter's serial number (None until known)."""
        return self._serial

    async def async_start(self) -> None:
        """Join the multicast group (receive only); retried every minute when
        the network is not ready yet (e.g. at boot)."""
        self._stopped = False
        await self._async_join()

    async def _async_join(self) -> None:
        try:
            transport, _ = await self.hass.loop.create_datagram_endpoint(
                lambda: _SpeedwireProtocol(self._received), sock=_multicast_socket()
            )
        except OSError as err:
            _LOGGER.warning(
                "Cannot receive SMA Speedwire telegrams yet (retry in %s s): %s",
                RETRY_S,
                err,
            )
            if not self._stopped:
                self._retry = async_call_later(self.hass, RETRY_S, self._async_retry)
            return
        if self._stopped:
            transport.close()  # stopped (unload) while joining: leave again
            return
        self._transport = transport

    async def _async_retry(self, _now: Any) -> None:
        self._retry = None
        if not self._stopped and self._transport is None:
            await self._async_join()

    async def async_stop(self) -> None:
        """Leave the multicast group."""
        self._stopped = True
        self.cancel_stale()
        if self._retry is not None:
            self._retry()
            self._retry = None
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    @callback
    def _received(self, data: bytes, host: str) -> None:
        if self._serial is None and host != self.host:
            return  # set up by IP address: until its serial is known
        telegram = decode(data)
        if telegram is None:
            return
        if self._serial is None:
            self._serial = telegram.serial
            _LOGGER.info("SMA meter at %s has serial %s", host, telegram.serial)
            if self.on_serial is not None:
                self.on_serial(telegram.serial)
        elif telegram.serial != self._serial:
            return  # another meter
        if host != self.host:
            if self.host is not None:
                _LOGGER.info("SMA meter %s now at %s", self._serial, host)
            self.host = host
        self.phase_v = telegram.phase_v
        self.phase_pf = telegram.phase_pf
        self._set(telegram.phase_w, telegram.phase_a)

    def diagnostics(self) -> dict[str, Any]:
        """State for the diagnostics download (with the serial)."""
        return {**super().diagnostics(), "serial": self._serial}


async def discover_speedwire(
    hass: HomeAssistant, seconds: float = 3.0
) -> dict[str, int]:
    """Listen briefly (receive only): IP address -> serial of energy meters."""
    found: dict[str, int] = {}

    def handler(data: bytes, host: str) -> None:
        if (telegram := decode(data)) is not None:
            found[host] = telegram.serial

    try:
        transport, _ = await hass.loop.create_datagram_endpoint(
            lambda: _SpeedwireProtocol(handler), sock=_multicast_socket()
        )
    except Exception as err:
        _LOGGER.debug("Speedwire not available: %s", err)
        return found
    try:
        await asyncio.sleep(seconds)
    finally:
        transport.close()
    return found
