"""The export limit: the most that may be exported to the grid now.

- when exporting earns too little: the export price minus the export
  costs of the contract (a fee or penalty per kWh) below the export limit
  price (default 0: only when exporting earns money) -> nothing is exported: limit 0 W (the batteries still take what they can;
  the inverters would produce no more than the house and batteries use);
- never export (setting): always 0 W;
- else a fixed maximum when set (e.g. a grid operator's limit);
- else no limit: the most that can be exported (``export_capacity_w``):
  the grid connection's maximum (phases x fuse x 230 V), or less when the
  breakers of all PV inverters are known (their sum: no more can pass
  them).

In this phase only shown and explained (sensor *Max export* on the grid
connection, *Why*); later the inverter drivers would carry it out.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ...const import NOMINAL_VOLTAGE

REASON_NONE = "none"
REASON_PRICE = "price"
REASON_FIXED = "fixed"
REASON_NEVER = "never"


# A coming period is told in *Why* when it is clear: at least this long,
# with at least this much export expected (by the plan).
EXPECT_MIN = timedelta(hours=1)
EXPECT_MIN_KWH = 0.5


@dataclass(frozen=True, slots=True)
class ExpectedLimit:
    """A coming period in which the plan exports while that earns too little."""

    start: datetime
    end: datetime
    kwh: float  # export the plan expects then (what would be held back)
    lowest_price: float | None  # lowest net export price in the period


def expected_limits(
    slots: list[Any],
    now: datetime,
    *,
    enabled: bool,
    threshold: float,
    cost: float = 0.0,
    export_factor: float = 1.0,
    never: bool = False,
) -> list[ExpectedLimit]:
    """Coming periods (from now) in which the plan expects export while the
    net export price is below the limit price, merged over adjacent slots;
    only the clear ones (``EXPECT_MIN``, ``EXPECT_MIN_KWH``)."""
    if not enabled and not never:
        return []
    periods: list[ExpectedLimit] = []
    run: list[Any] = []

    def close() -> None:
        if not run:
            return
        kwh = sum(
            -s.grid_w * (s.end - s.start).total_seconds() / 3_600_000 for s in run
        )
        prices = [p for s in run if (p := _net(s, cost, export_factor)) is not None]
        if run[-1].end - run[0].start >= EXPECT_MIN and kwh >= EXPECT_MIN_KWH:
            periods.append(
                ExpectedLimit(
                    run[0].start, run[-1].end, round(kwh, 2), min(prices, default=None)
                )
            )
        run.clear()

    for slot in slots:
        if slot.end <= now:
            continue
        net = _net(slot, cost, export_factor)
        stopped = never or (net is not None and net < threshold)
        if slot.grid_w < -1 and stopped:
            if run and run[-1].end != slot.start:
                close()
            run.append(slot)
        else:
            close()
    close()
    return periods


def _net(slot: Any, cost: float, export_factor: float) -> float | None:
    """What a kWh exported in this slot earns after the export costs."""
    price = slot.export_price
    if price is None and slot.price is not None:
        price = slot.price * export_factor
    return None if price is None else price - cost


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


def inverter_max_w(max_current: float | None, phases: int) -> float | None:
    """The most an inverter can deliver through its breaker (None: unknown)."""
    if not max_current or max_current <= 0:
        return None
    return max(phases, 1) * max_current * NOMINAL_VOLTAGE


def export_capacity_w(connection: float, inverters: list[float | None]) -> float:
    """The most the inverters can export: the connection, or the sum of the
    inverters' breakers when that is lower (only when every inverter's
    breaker is known)."""
    if not inverters or any(w is None for w in inverters):
        return connection
    return min(connection, sum(w for w in inverters if w is not None))


def production_limits(
    limit_w: float,
    grid_w: float,
    pv_w: float,
    maxima: list[float | None],
) -> list[float]:
    """What each inverter that limits its own output may produce so the
    export stays within ``limit_w``.

    An inverter limits its production, not the export: together they may
    give what the house and the batteries use now plus the export allowed,
    minus what other (not limited) PV gives. With ``pv_w`` = the PV of these
    inverters only and ``grid_w`` = the **measured** grid (+ import /
    - export, the real batteries as they are): ``pv + grid + limit``, so at
    0 W export the house is still fed. That total is split over the
    inverters by their maximum (breaker) when all are known, else equally,
    and capped at each one's maximum. An export limit (a Home Manager) gets
    ``limit_w`` itself.
    """
    if not maxima:
        return []
    total = max(pv_w + grid_w + limit_w, 0.0)
    known = all(m is not None and m > 0 for m in maxima)
    weights = [m if known and m is not None else 1.0 for m in maxima]
    whole = sum(weights)
    shares = [total * w / whole for w in weights]
    return [
        min(share, m) if m is not None and m > 0 else share
        for share, m in zip(shares, maxima, strict=True)
    ]


def export_limit(
    *,
    enabled: bool,
    price: float | None,
    threshold: float,
    cost: float = 0.0,
    fixed_w: float,
    connection: float,
    never: bool = False,
) -> ExportLimit:
    """The export limit now (see the module docstring)."""
    if never:
        return ExportLimit(0.0, True, REASON_NEVER)
    if enabled and price is not None and price - cost < threshold:
        return ExportLimit(0.0, True, REASON_PRICE)
    if fixed_w > 0 and fixed_w < connection:
        return ExportLimit(float(fixed_w), True, REASON_FIXED)
    return ExportLimit(connection, False, REASON_NONE)
