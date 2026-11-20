"""A small Modbus TCP client (asyncio, no extra dependencies).

Only what battery drivers need: read holding / input registers (function codes
3 and 4) and write single / multiple registers (6 and 16). One request at a
time per connection, with a timeout and an optional pause between requests
(some devices need that). Values are 16-bit registers; ``decode`` combines
them into signed / unsigned 16- or 32-bit numbers.

Many devices allow only ONE Modbus TCP client at a time. A driver using this
client must therefore never connect while another integration owns the
device; HomeBatteryAssist's direct battery drivers are disabled by default.
"""

from __future__ import annotations

import asyncio
import contextlib
import struct
from typing import Literal

FC_READ_HOLDING = 3
FC_READ_INPUT = 4
FC_WRITE_SINGLE = 6
FC_WRITE_MULTIPLE = 16
MAX_READ = 125  # registers per read request (Modbus limit)


class ModbusError(Exception):
    """A Modbus exception response, a timeout or a broken connection."""


class ModbusTcpClient:
    """One Modbus TCP connection to one device."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit: int = 1,
        *,
        timeout: float = 3.0,
        pause: float = 0.0,
        reconnect_delay: float = 0.0,
    ) -> None:
        """Initialize; ``pause`` seconds are waited between requests and
        ``reconnect_delay`` seconds between a close and the next connect
        (some devices refuse a fast reconnect)."""
        self.host = host
        self.port = port
        self.unit = unit
        self.timeout = timeout
        self.pause = pause
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self.reconnect_delay = reconnect_delay
        self.allowed = False  # set by an enabled driver when it opens
        self._lock = asyncio.Lock()
        self._transaction = 0
        self._closed_at: float | None = None

    @property
    def connected(self) -> bool:
        """Whether the connection is open."""
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Open the connection (after ``reconnect_delay`` since a close)."""
        if not self.allowed:
            # Only a driver that was deliberately enabled and opened may
            # connect (read-only phase: never a second client to a battery).
            raise ModbusError("Modbus TCP client not opened by an enabled driver")
        if self._closed_at is not None and self.reconnect_delay:
            wait = (
                self._closed_at
                + self.reconnect_delay
                - asyncio.get_running_loop().time()
            )
            if wait > 0:
                await asyncio.sleep(wait)
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
        except (OSError, TimeoutError) as err:
            raise ModbusError(
                f"cannot connect to {self.host}:{self.port}: {err}"
            ) from err

    async def close(self) -> None:
        """Close the connection."""
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(OSError):
                await self._writer.wait_closed()
            self._closed_at = asyncio.get_running_loop().time()
        self._reader = self._writer = None

    async def read_holding(self, address: int, count: int) -> list[int]:
        """Holding registers (function code 3)."""
        return await self._read(FC_READ_HOLDING, address, count)

    async def read_input(self, address: int, count: int) -> list[int]:
        """Input registers (function code 4)."""
        return await self._read(FC_READ_INPUT, address, count)

    async def write_register(self, address: int, value: int) -> None:
        """One holding register (function code 6)."""
        await self._request(
            FC_WRITE_SINGLE, struct.pack(">HH", address, value & 0xFFFF)
        )

    async def write_registers(self, address: int, values: list[int]) -> None:
        """Several consecutive holding registers (function code 16)."""
        data = b"".join(struct.pack(">H", v & 0xFFFF) for v in values)
        await self._request(
            FC_WRITE_MULTIPLE,
            struct.pack(">HHB", address, len(values), len(data)) + data,
        )

    async def _read(self, function: int, address: int, count: int) -> list[int]:
        if not 1 <= count <= MAX_READ:
            raise ValueError(f"count {count} out of range")
        payload = await self._request(function, struct.pack(">HH", address, count))
        if not payload or payload[0] != 2 * count or len(payload) != 1 + 2 * count:
            raise ModbusError("unexpected read response length")
        return list(struct.unpack(f">{count}H", payload[1:]))

    async def _request(self, function: int, body: bytes) -> bytes:
        async with self._lock:
            if not self.connected:
                await self.connect()
            assert self._reader is not None and self._writer is not None
            self._transaction = (self._transaction + 1) & 0xFFFF
            pdu = bytes([function]) + body
            frame = struct.pack(">HHHB", self._transaction, 0, len(pdu) + 1, self.unit)
            try:
                self._writer.write(frame + pdu)
                await self._writer.drain()
                header = await asyncio.wait_for(
                    self._reader.readexactly(7), self.timeout
                )
                transaction, _protocol, length, _unit = struct.unpack(">HHHB", header)
                first = await asyncio.wait_for(
                    self._reader.readexactly(1), self.timeout
                )
                if first[0] & 0x80:
                    # Exception: only the code follows. Read just that, since
                    # some devices announce a wrong length for this frame.
                    response = first + await asyncio.wait_for(
                        self._reader.readexactly(1), self.timeout
                    )
                else:
                    response = first + await asyncio.wait_for(
                        self._reader.readexactly(length - 2), self.timeout
                    )
            except (OSError, TimeoutError, asyncio.IncompleteReadError) as err:
                await self.close()
                raise ModbusError(f"{self.host}: {err or type(err).__name__}") from err
            finally:
                if self.pause:
                    await asyncio.sleep(self.pause)
            if transaction != self._transaction:
                await self.close()
                raise ModbusError("transaction id mismatch")
            if response[0] == function | 0x80:
                raise ModbusError(f"exception code {response[1]}")
            if response[0] != function:
                raise ModbusError("unexpected function code in response")
            return response[1:]


def decode(
    registers: list[int],
    kind: Literal["u16", "s16", "u32", "s32"],
    *,
    swap_words: bool = False,
) -> int:
    """A number from one or two registers (big-endian words unless swapped)."""
    if kind in ("u16", "s16"):
        value = registers[0]
        return value - 0x10000 if kind == "s16" and value >= 0x8000 else value
    high, low = (registers[1], registers[0]) if swap_words else registers[:2]
    value = (high << 16) | low
    return value - 0x100000000 if kind == "s32" and value >= 0x80000000 else value
