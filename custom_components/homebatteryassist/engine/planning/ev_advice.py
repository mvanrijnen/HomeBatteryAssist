"""When to charge an electric car: advice only (the charger is not controlled).

The user gives the energy to charge (kWh from the grid connection), the
charger's power and the period in which it must be done. The advice is one
block (switched on once, off once) within that period at the lowest
expected cost, from the selected battery plan per slot:

- what a kWh costs then (the import price after the tariff);
- the expected solar surplus left after the batteries (the plan's export,
  ``-grid_w``): charging from it costs only what exporting it would have
  earned (the export price), as the plans count solar charging.

The car is an excluded load: the batteries never discharge for it, so the
plan's grid is not changed by the advice.

Later (todo, by the owner's decision when control is allowed): switch the
charger on and off at the advised times through its integration.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

# Within this (money) of the cheapest, the earliest block wins (no jumping
# to a later one for a rounding difference).
TIE = 1e-6


@dataclass(frozen=True, slots=True)
class EvSlot:
    """One slot of the plan, as far as the car is concerned."""

    start: datetime
    end: datetime
    price: float  # import, per kWh
    export_price: float | None  # what exporting earns, per kWh
    surplus_w: float  # expected export after the batteries (>= 0)


@dataclass(frozen=True, slots=True)
class EvAdvice:
    """The advised block, or why there is none (``reason``)."""

    start: datetime | None = None
    end: datetime | None = None
    kwh: float = 0.0
    cost: float | None = None  # expected cost of the block
    sun_kwh: float = 0.0  # of which from the expected solar surplus
    now_cost: float | None = None  # starting as early as possible instead
    now_start: datetime | None = None
    prices_until: datetime | None = None  # how far the plan's prices reach
    reason: str | None = None  # no_prices / too_short / beyond_prices / invalid

    @property
    def avg_price(self) -> float | None:
        """Average cost per kWh of the block."""
        return self.cost / self.kwh if self.cost is not None and self.kwh else None


def _cost(
    slots: Sequence[EvSlot], start: datetime, end: datetime, power_w: float
) -> tuple[float, float] | None:
    """(cost, kWh from the sun) of charging ``power_w`` from start to end;
    None when a part of it has no slot (no price)."""
    cost = sun = 0.0
    covered = timedelta(0)
    for slot in slots:
        a, b = max(slot.start, start), min(slot.end, end)
        if b <= a:
            continue
        hours = (b - a).total_seconds() / 3600
        covered += b - a
        from_sun = min(power_w, max(slot.surplus_w, 0.0))
        export = slot.export_price if slot.export_price is not None else slot.price
        cost += (from_sun * export + (power_w - from_sun) * slot.price) * hours / 1000
        sun += from_sun * hours / 1000
    if covered < (end - start) - timedelta(seconds=1):
        return None
    return cost, sun


def advise(
    slots: Sequence[EvSlot],
    kwh: float,
    power_w: float,
    earliest: datetime,
    latest: datetime,
    now: datetime,
) -> EvAdvice:
    """The cheapest single block of ``kwh`` at ``power_w`` that starts at or
    after ``earliest`` (and not before now) and ends by ``latest``."""
    if kwh <= 0 or power_w <= 0 or latest <= earliest:
        return EvAdvice(reason="invalid")
    slots = sorted(slots, key=lambda s: s.start)
    if not slots:
        return EvAdvice(reason="no_prices")
    begin = max(earliest, now)
    duration = timedelta(hours=kwh * 1000 / power_w)
    prices_until = slots[-1].end
    if begin + duration > latest:
        return EvAdvice(kwh=kwh, prices_until=prices_until, reason="too_short")
    last_end = min(latest, prices_until)
    if begin + duration > last_end:
        return EvAdvice(kwh=kwh, prices_until=prices_until, reason="beyond_prices")
    # Candidate starts: as early as possible, every slot start, and every
    # start that makes the block end on a slot boundary (the cheapest block
    # often ends where a cheap period ends).
    starts = {begin}
    for slot in slots:
        for when in (slot.start, slot.end - duration):
            if begin <= when and when + duration <= last_end:
                starts.add(when)
    best: tuple[float, datetime, float] | None = None
    for start in sorted(starts):
        result = _cost(slots, start, start + duration, power_w)
        if result is None:
            continue
        cost, sun = result
        if best is None or cost < best[0] - TIE:
            best = (cost, start, sun)
    if best is None:
        return EvAdvice(kwh=kwh, prices_until=prices_until, reason="no_prices")
    now_result = _cost(slots, begin, begin + duration, power_w)
    cost, start, sun = best
    return EvAdvice(
        start=start,
        end=start + duration,
        kwh=kwh,
        cost=round(cost, 4),
        sun_kwh=round(sun, 2),
        now_cost=None if now_result is None else round(now_result[0], 4),
        now_start=begin,
        prices_until=prices_until,
    )


def slots_from_plan(plan: object) -> list[EvSlot]:
    """The selected battery plan's slots with a price, for ``advise``."""
    return [
        EvSlot(
            s.start,
            s.end,
            s.price,
            s.export_price,
            max(-s.grid_w, 0.0),
        )
        for s in getattr(plan, "slots", None) or []
        if s.price is not None
    ]
