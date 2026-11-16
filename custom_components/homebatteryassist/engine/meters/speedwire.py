"""Decoding of SMA Speedwire energy meter telegrams (Home Manager, Energy Meter).

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

import struct
from dataclasses import dataclass

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
