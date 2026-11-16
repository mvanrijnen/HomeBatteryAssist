"""Generic Modbus TCP battery driver: a register map as data.

A brand driver subclasses ``ModbusBatteryDriver`` and only declares:

- ``points``: the registers to read (``Point``: name, address, type, scale,
  sign, function code), mapped to the reading by name — ``soc``,
  ``power_w`` (already + charging after ``sign``), and telemetry fields such as
  ``temperature_c``, ``voltage_v``, ``cell_min_v``, ``cell_max_v``,
  ``cycles``, ``charged_today_kwh``, ``discharged_today_kwh``; other names
  end up in ``DirectReading.extra``;
- connection details (port, unit id, timeout, pause between requests);
- ``async_set_power`` / ``async_release`` with its control sequence (never
  called while HomeBatteryAssist is read-only).

Points are read in as few requests as possible (consecutive addresses of the
same function code, at most ``max_block`` registers).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from ...transports.modbus_tcp import (
    FC_READ_HOLDING,
    FC_READ_INPUT,
    ModbusTcpClient,
    decode,
)
from ..base import BatteryTelemetry
from .base import DirectBatteryDriver, DirectReading

TELEMETRY = set(BatteryTelemetry.__slots__) - {"extra"}


@dataclass(frozen=True, slots=True)
class Point:
    """One value in the device's registers."""

    name: str
    address: int
    kind: Literal["u16", "s16", "u32", "s32"] = "u16"
    scale: float = 1.0  # value = raw * scale * sign
    sign: float = 1.0  # e.g. -1 when the device counts discharging as +
    function: int = FC_READ_HOLDING
    swap_words: bool = False  # 32-bit: low word first

    @property
    def size(self) -> int:
        """Registers taken."""
        return 2 if self.kind in ("u32", "s32") else 1


def blocks(points: tuple[Point, ...], max_block: int) -> list[tuple[int, int, int]]:
    """(function, start address, count) requests covering all points."""
    result: list[tuple[int, int, int]] = []
    for function in (FC_READ_HOLDING, FC_READ_INPUT):
        spans = sorted(
            (p.address, p.address + p.size) for p in points if p.function == function
        )
        start = end = None
        for first, last in spans:
            if start is not None and first <= end and last - start <= max_block:
                end = max(end, last)
                continue
            if start is not None:
                result.append((function, start, end - start))
            start, end = first, last
        if start is not None:
            result.append((function, start, end - start))
    return result


class ModbusBatteryDriver(DirectBatteryDriver):
    """A battery read over Modbus TCP, from a register map."""

    transport = "modbus_tcp"
    port: ClassVar[int] = 502
    unit: ClassVar[int] = 1
    timeout: ClassVar[float] = 3.0
    pause: ClassVar[float] = 0.0  # seconds between requests (device needs)
    max_block: ClassVar[int] = 60  # registers per request
    points: ClassVar[tuple[Point, ...]] = ()

    def __init__(self, hass: Any, address: str, **options: Any) -> None:
        """Initialize; ``options`` may override ``port`` and ``unit``."""
        super().__init__(hass, address, **options)
        self.client = ModbusTcpClient(
            address,
            int(options.get("port", self.port)),
            int(options.get("unit", self.unit)),
            timeout=self.timeout,
            pause=self.pause,
        )

    async def async_open(self) -> None:
        """Connect (only when enabled)."""
        await super().async_open()
        await self.client.connect()

    async def async_close(self) -> None:
        """Disconnect."""
        await self.client.close()

    async def async_read(self) -> DirectReading:
        """Read all points and map them onto a reading."""
        raw: dict[tuple[int, int], int] = {}
        for function, start, count in blocks(self.points, self.max_block):
            read = (
                self.client.read_holding
                if function == FC_READ_HOLDING
                else self.client.read_input
            )
            for offset, value in enumerate(await read(start, count)):
                raw[(function, start + offset)] = value
        values: dict[str, float] = {}
        for point in self.points:
            words = [
                raw[(point.function, point.address + i)] for i in range(point.size)
            ]
            number = decode(words, point.kind, swap_words=point.swap_words)
            values[point.name] = round(number * point.scale * point.sign, 4)
        return self.reading(values)

    def reading(self, values: dict[str, float]) -> DirectReading:
        """Map decoded values onto a reading (brands may adjust)."""
        return DirectReading(
            soc=values.get("soc"),
            power_w=values.get("power_w"),
            telemetry=BatteryTelemetry(
                **{k: v for k, v in values.items() if k in TELEMETRY}
            ),
            extra={
                k: v
                for k, v in values.items()
                if k not in TELEMETRY and k not in ("soc", "power_w")
            },
        )
