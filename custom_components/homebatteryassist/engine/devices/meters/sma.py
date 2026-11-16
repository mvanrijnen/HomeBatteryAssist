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
41/42 = L2, 61/62 = L3 (import/export). Record 0x90000000 holds the software
version (4 bytes).
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

from .connection import SOURCE_SPEEDWIRE, DirectMeter

_LOGGER = logging.getLogger(__name__)


GROUP = "239.12.255.254"
PORT = 9522
PROTOCOL_EMETER = 0x6069

# index of import power per phase (export = index + 1)
PHASE_INDEX = (21, 41, 61)


@dataclass(frozen=True, slots=True)
class MeterTelegram:
    """One energy meter measurement."""

    serial: int
    susy_id: int
    ticker_ms: int
    power_w: float  # total, + import / - export
    phase_w: tuple[float, float, float]  # per phase, + import / - export


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
            actual[index] = struct.unpack_from(">I", data, pos)[0] / 10  # 0.1 W
            pos += 4
        elif kind == 8:
            pos += 8
        elif channel == 0 and index == 0 and kind == 0:
            break  # end marker
        else:
            return None  # unknown record: do not guess
    if 1 not in actual or not all(i in actual for i in PHASE_INDEX):
        return None
    phases = tuple(round(actual[i] - actual.get(i + 1, 0.0), 1) for i in PHASE_INDEX)
    return MeterTelegram(
        serial,
        susy_id,
        ticker,
        round(actual[1] - actual.get(2, 0.0), 1),
        phases,  # type: ignore[arg-type]
    )


class _SpeedwireProtocol(asyncio.DatagramProtocol):
    def __init__(self, handler: Callable[[bytes, str], None]) -> None:
        self._handler = handler

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        self._handler(data, addr[0])


def _multicast_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind(("", PORT))
    membership = struct.pack(
        "4s4s", socket.inet_aton(GROUP), socket.inet_aton("0.0.0.0")
    )
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    sock.setblocking(False)
    return sock


class SpeedwireMeter(DirectMeter):
    """Receives the multicast telegrams of one SMA Home Manager / Energy Meter."""

    label = SOURCE_SPEEDWIRE

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Initialize; ``address`` is the meter's IP address."""
        super().__init__(hass, address)
        self._transport: asyncio.DatagramTransport | None = None

    async def async_start(self) -> None:
        """Join the multicast group (receive only)."""
        try:
            self._transport, _ = await self.hass.loop.create_datagram_endpoint(
                lambda: _SpeedwireProtocol(self._received), sock=_multicast_socket()
            )
        except OSError as err:
            _LOGGER.warning("Cannot receive SMA Speedwire telegrams: %s", err)

    async def async_stop(self) -> None:
        """Leave the multicast group."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    @callback
    def _received(self, data: bytes, host: str) -> None:
        if host != self.address:
            return
        if (telegram := decode(data)) is not None:
            self._set(telegram.phase_w)


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
