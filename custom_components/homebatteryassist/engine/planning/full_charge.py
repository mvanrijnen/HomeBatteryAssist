"""Periodic full charges (cell balancing), planned at the cheapest moment.

Every battery with a full charge interval must reach 100 % at least once per
interval. A full charge that happens by itself (e.g. on a sunny day) resets the
clock. Otherwise, from ``window_days`` before the deadline (or right away when
it has passed), a forced full charge is planned in the cheapest block within
that period:

- the block is as long as charging from the current state of charge to 100 %
  takes at the battery's maximum charge power;
- its cost is the sum of the (forecast) prices over the block;
- batteries are handled by earliest deadline. They may charge fully at the
  same time when that costs nothing extra: ``fits(start, powers)`` tells
  whether the batteries charging in a slot fit within the grid connection
  (phase limits). Where they do not, a later battery gets the cheapest block
  that does fit.

Advice for real batteries; virtual batteries carry it out.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from ..batteries.monitor import BatteryState
from ..inputs.prices import PricePoint

DEFAULT_WINDOW_DAYS = 3


@dataclass(frozen=True, slots=True)
class FullCharge:
    """A planned full charge of one battery."""

    battery_id: str
    name: str
    start: datetime
    end: datetime
    deadline: datetime
    last_full: datetime | None
    power_w: float  # average charge power during the block
    price: float | None = None  # average price in the block
    avg_price: float | None = None  # average price in the period it could be in

    def active(self, when: datetime) -> bool:
        """True while the block is running."""
        return self.start <= when < self.end


def full_charge_due(
    last_full: datetime | None, interval_days: int, now: datetime
) -> datetime | None:
    """Deadline of the next full charge, or None if not configured."""
    if interval_days <= 0:
        return None
    return now if last_full is None else last_full + timedelta(days=interval_days)


def schedule_full_charges(
    states: Iterable[BatteryState],
    last_full: Mapping[str, datetime | None],
    prices: Sequence[PricePoint],
    window_days: int,
    now: datetime,
    step: timedelta = timedelta(minutes=15),
    fits: Callable[[datetime, Mapping[str, float]], bool] | None = None,
    preferred_day: int | None = None,
    slot_price: Callable[[datetime, float, float], float] | None = None,
) -> list[FullCharge]:
    """Plan the full charges that are due within ``window_days``.

    ``fits``: whether charging with these powers (battery id -> W) in the slot
    starting at the given time stays within the grid connection; without it,
    full charges never overlap.
    ``preferred_day``: weekday (0 = Monday) to prefer, if it fits in the period.
    ``slot_price(start, price, power)``: the effective price of charging in a
    slot, e.g. lower when there is solar surplus.
    """
    if not prices:
        return []
    horizon_end = max(p.end for p in prices)
    window = timedelta(days=window_days)

    due: list[tuple[datetime, BatteryState]] = []
    for state in states:
        deadline = full_charge_due(
            last_full.get(state.config.id), state.config.full_charge_interval_days, now
        )
        if deadline is None or state.soc is None or now < deadline - window:
            continue
        due.append((deadline, state))
    due.sort(key=lambda item: item[0])

    # Clock-aligned slots with a known price.
    ts = now.timestamp()
    seconds = step.total_seconds()
    first = dt_util.utc_from_timestamp(ts - ts % seconds) + step
    slots: list[tuple[datetime, float]] = []
    when = first
    while when + step <= horizon_end:
        price = next((p.price for p in prices if p.start <= when < p.end), None)
        if price is not None:
            slots.append((when, price))
        when += step

    planned: list[FullCharge] = []
    for deadline, state in due:
        config = state.config
        # Overdue: catch up within the window; otherwise finish before the deadline.
        latest_end = min(deadline if deadline > now else now + window, horizon_end)
        missing_wh = max(100.0 - state.soc, 0.0) * config.capacity_kwh * 10
        eff = math.sqrt(config.efficiency)
        hours = missing_wh / (config.max_charge_w * eff) if config.max_charge_w else 0
        count = max(1, math.ceil(hours * 3600 / seconds))
        power = round(
            min(config.max_charge_w, missing_wh / eff / (count * seconds / 3600)), 1
        )

        def allowed(
            start: datetime, end: datetime, power: float = power, own: str = config.id
        ) -> bool:
            overlapping = [p for p in planned if start < p.end and end > p.start]
            if not overlapping:
                return True
            if fits is None:
                return False
            when = start
            while when < end:
                powers = {
                    p.battery_id: p.power_w for p in overlapping if p.active(when)
                }
                if powers and not fits(when, {**powers, own: power}):
                    return False
                when += step
            return True

        best: tuple[float, int] | None = None
        for i in range(len(slots) - count + 1):
            block = slots[i : i + count]
            start, end = block[0][0], block[-1][0] + step
            if end > latest_end:
                break
            if block[-1][0] - start != step * (count - 1):
                continue  # gap in the prices
            if not allowed(start, end):
                continue  # together they would overload the connection
            cost = sum(
                slot_price(when, price, power) if slot_price else price
                for when, price in block
            )
            if (
                preferred_day is not None
                and dt_util.as_local(start).weekday() != preferred_day
            ):
                cost += 1000  # only when the preferred day is not possible
            if best is None or cost < best[0]:
                best = (cost, i)
        if best is None:
            continue
        start = slots[best[1]][0]
        end = start + step * count
        candidates = [price for when, price in slots if when + step <= latest_end]
        planned.append(
            FullCharge(
                config.id,
                config.name,
                start,
                end,
                deadline,
                last_full.get(config.id),
                power,
                round((best[0] % 1000) / count, 5),
                round(sum(candidates) / len(candidates), 5) if candidates else None,
            )
        )
    return planned
