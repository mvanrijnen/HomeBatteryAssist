"""The export limit: the most that may be exported to the grid now.

- below the export limit price (default 0, so at a negative export price)
  nothing is exported: limit 0 W (the batteries still take what they can;
  the inverters would produce no more than the house and batteries use);
- else a fixed maximum when set (e.g. a grid operator's limit);
- else no limit: the grid connection's maximum (phases x fuse x 230 V).

In this phase only shown and explained (sensor *Max export* on the grid
connection, *Why*); later the inverter drivers would carry it out.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...const import NOMINAL_VOLTAGE

REASON_NONE = "none"
REASON_PRICE = "price"
REASON_FIXED = "fixed"


@dataclass(frozen=True, slots=True)
class ExportLimit:
    """The limit now."""

    limit_w: float  # W; the connection's maximum when not limited
    limited: bool
    reason: str  # REASON_*

    def amps_per_phase(self, phases: int) -> float:
        """The limit as current per phase (A), spread over the phases."""
        return self.limit_w / max(phases, 1) / NOMINAL_VOLTAGE


def connection_w(phases: int, max_current: float) -> float:
    """The most the grid connection carries (W)."""
    return phases * max_current * NOMINAL_VOLTAGE


def export_limit(
    *,
    enabled: bool,
    price: float | None,
    threshold: float,
    fixed_w: float,
    connection: float,
) -> ExportLimit:
    """The export limit now (see the module docstring)."""
    if enabled and price is not None and price < threshold:
        return ExportLimit(0.0, True, REASON_PRICE)
    if fixed_w > 0 and fixed_w < connection:
        return ExportLimit(float(fixed_w), True, REASON_FIXED)
    return ExportLimit(connection, False, REASON_NONE)
