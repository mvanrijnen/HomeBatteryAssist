"""Tests for the small Modbus TCP client against an in-memory fake device."""

import asyncio
import struct
from unittest.mock import patch

import pytest

from custom_components.homebatteryassist.engine.devices.transports.modbus_tcp import (
    ModbusError,
    ModbusTcpClient,
    decode,
)


class FakeDevice:
    """Answers Modbus TCP frames; holding registers address * 10; records writes."""

    def __init__(self) -> None:
        self.registers = {i: i * 10 for i in range(200)}
        self.writes: list[tuple[int, list[int]]] = []

    def answer(self, frame: bytes) -> bytes:
        transaction, _p, length, unit = struct.unpack(">HHHB", frame[:7])
        pdu = frame[7 : 6 + length]
        function = pdu[0]
        if function in (3, 4):
            address, count = struct.unpack(">HH", pdu[1:5])
            if address >= 1000:  # illegal address
                reply = bytes([function | 0x80, 2])
                if address == 2000:  # a device announcing a wrong length
                    return struct.pack(">HHHB", transaction, 0, 4, unit) + reply
            else:
                values = [self.registers.get(address + i, 0) for i in range(count)]
                reply = bytes([function, 2 * count]) + struct.pack(
                    f">{count}H", *values
                )
        elif function == 6:
            address, value = struct.unpack(">HH", pdu[1:5])
            self.writes.append((address, [value]))
            reply = pdu
        else:  # 16
            address, count, _n = struct.unpack(">HHB", pdu[1:6])
            self.writes.append(
                (address, list(struct.unpack(f">{count}H", pdu[6 : 6 + 2 * count])))
            )
            reply = bytes([16]) + struct.pack(">HH", address, count)
        return struct.pack(">HHHB", transaction, 0, len(reply) + 1, unit) + reply


class _Writer:
    def __init__(self, device: FakeDevice, reader: asyncio.StreamReader) -> None:
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
def device():
    fake = FakeDevice()

    async def open_connection(host, port):
        reader = asyncio.StreamReader()
        return reader, _Writer(fake, reader)

    with patch(
        "custom_components.homebatteryassist.engine.devices.transports.modbus_tcp.asyncio.open_connection",
        open_connection,
    ):
        yield fake


async def test_read_write(device: FakeDevice) -> None:
    client = ModbusTcpClient("192.0.2.1")
    assert await client.read_holding(10, 3) == [100, 110, 120]
    assert await client.read_input(0, 2) == [0, 10]
    await client.write_register(5, -1)
    await client.write_registers(7, [1, 2])
    assert device.writes == [(5, [0xFFFF]), (7, [1, 2])]
    with pytest.raises(ModbusError, match="exception code 2"):
        await client.read_holding(1000, 1)
    with pytest.raises(ModbusError, match="exception code 2"):
        await client.read_holding(2000, 1)  # malformed length: no timeout
    with pytest.raises(ValueError):
        await client.read_holding(0, 200)
    await client.close()


def test_decode() -> None:
    assert decode([0xFFFF], "s16") == -1
    assert decode([0xFFFF], "u16") == 65535
    assert decode([0x0001, 0x0002], "u32") == 0x00010002
    assert decode([0x0002, 0x0001], "u32", swap_words=True) == 0x00010002
    assert decode([0xFFFF, 0xFFFE], "s32") == -2
