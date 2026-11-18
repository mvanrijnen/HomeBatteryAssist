"""PV inverter drivers: how an inverter's power could be limited.

To keep the export within a limit (``engine/planning/export_limit.py``) an
inverter can be told to produce less. A driver describes how for one kind of
inverter. **In this phase nothing is sent**: ``enabled`` is False for every
driver and ``async_set_limit`` is never called (HomeBatteryAssist only reads;
it does not open its own connection to an inverter either). The export limit
is shown and explained, with what each driver would send.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant


@dataclass(frozen=True, slots=True)
class Point:
    """One setting the driver would write (e.g. a Modbus register)."""

    address: int
    name: str
    value: str  # what would be written, e.g. "802" or "{limit_w}"


class InverterDriver:
    """How to limit one kind of inverter."""

    key: str = ""
    name: str = ""
    # Never True in this phase: nothing is sent to an inverter.
    enabled: bool = False
    # Checked on a real device (False: from the manufacturer's documentation).
    verified: bool = False
    # What it limits: "export" (the grid export, the meter's own control) or
    # "power" (the inverter's own output).
    limits: str = "power"
    points: tuple[Point, ...] = ()

    def describe(self, address: str, limit_w: float) -> str:
        """What it would send for this limit (for the attributes and *Why*)."""
        parts = [
            f"{p.address}={p.value.format(limit_w=round(limit_w))}" for p in self.points
        ]
        return f"{self.name} {address}: " + ", ".join(parts)

    async def async_set_limit(
        self, hass: HomeAssistant, address: str, limit_w: float | None
    ) -> None:
        """Limit the inverter to ``limit_w`` (None = no limit).

        NEVER called in this phase; drivers do not implement it yet.
        """
        raise NotImplementedError
