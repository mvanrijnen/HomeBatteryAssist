"""Periodic full charges (cell balancing), planned at the cheapest moment.

Every battery with a full charge interval must reach 100 % at least once per
interval. A full charge that happens by itself (e.g. on a sunny day) resets the
clock. Otherwise, from ``window_days`` before the deadline (or right away when
it has passed), a forced full charge is planned in the cheapest block within
that period:

- the block is as long as charging from the current state of charge to 100 %
  takes at the battery's maximum charge power;
- its cost is the sum of the (forecast) prices over the block;
- never two batteries at the same time (owner's rule): a later battery gets
  the cheapest block that does not overlap the ones planned before it;
- the order: ``together`` "parallel" by earliest deadline, "sequential" the
  emptiest battery first.

Advice for real batteries; virtual batteries carry it out.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from ..measure.battery_monitor import BatteryState
from ..sources.prices.price_points import PricePoint

DEFAULT_WINDOW_DAYS = 3


def _price_over(
    prices: Sequence[PricePoint], start: datetime, end: datetime
) -> float | None:
    """The time-weighted price over a slot (quarter prices in an hour slot);
    None when no price covers it."""
    total = seconds = 0.0
    for point in prices:
        overlap = (min(point.end, end) - max(point.start, start)).total_seconds()
        if overlap > 0:
            total += point.price * overlap
            seconds += overlap
    return total / seconds if seconds else None


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
    preferred_day: int | None = None,
    slot_price: Callable[[datetime, float, float], float] | None = None,
    together: str = "parallel",
    max_charge_w: float = 0.0,
    window_end: datetime | None = None,
    room: Callable[[datetime, str], float] | None = None,
    fixed: Sequence[FullCharge] = (),
) -> list[FullCharge]:
    """Plan the full charges that are due within ``window_days``.

    ``room(start, battery_id)``: the most that battery can charge in that
    slot (W) within the phase limits (its own phase too) and the peak limit; a block is made as long as it takes to
    really reach 100 % with it (else it would end short and be planned again).
    Full charges never overlap (one battery at a time); ``step`` should be the
    plan's slot length, so two blocks never share a plan slot either.
    ``max_charge_w``: the system's max charge power (0 = none); with a
    battery's ``charge_factor`` (warm: derated) it sizes the block, so the
    plan can really charge it in that time.
    ``preferred_day``: weekday (0 = Monday) to prefer, if it fits in the period.
    ``slot_price(start, price, power)``: the effective price of charging in a
    slot, e.g. lower when there is solar surplus.
    """
    if not prices:
        return list(fixed)  # running blocks stay
    horizon_end = max(p.end for p in prices)
    if window_end is not None:
        horizon_end = min(horizon_end, window_end)  # never past the window
    window = timedelta(days=window_days)

    due: list[tuple[datetime, BatteryState]] = []
    for state in states:
        deadline = full_charge_due(
            last_full.get(state.config.id), state.config.full_charge_interval_days, now
        )
        if deadline is None or state.soc is None or now < deadline - window:
            continue
        if any(f.battery_id == state.config.id for f in fixed):
            continue  # running: its block stays (``fixed``)
        due.append((deadline, state))
    if together == "sequential":
        # One after the other: the emptiest battery first.
        due.sort(key=lambda item: (item[1].soc, item[0]))
    else:
        due.sort(key=lambda item: item[0])

    # Clock-aligned slots with a known price.
    ts = now.timestamp()
    seconds = step.total_seconds()
    first = dt_util.utc_from_timestamp(ts - ts % seconds) + step
    slots: list[tuple[datetime, float]] = []
    when = first
    while when + step <= horizon_end:
        price = _price_over(prices, when, when + step)
        if price is not None:
            slots.append((when, price))
        when += step

    # Running blocks stay; the others are planned around them.
    planned: list[FullCharge] = [
        f
        for f in fixed
        if any(
            f.battery_id == s.config.id
            and full_charge_due(
                last_full.get(s.config.id), s.config.full_charge_interval_days, now
            )
            is not None
            for s in states
        )
    ]
    for deadline, state in due:
        config = state.config
        # Overdue: catch up within the window; otherwise finish before the deadline.
        latest_end = min(deadline if deadline > now else now + window, horizon_end)
        # Sized for the worst case: by the time the block runs the battery
        # may be as low as its minimum (it can be days later). A block that
        # turns out longer than needed stops at full (``finalise``).
        start_soc = min(state.soc, getattr(config, "min_soc", state.soc))
        missing_wh = max(100.0 - start_soc, 0.0) * config.capacity_kwh * 10
        eff = math.sqrt(config.efficiency)
        can_w = config.max_charge_w * getattr(state, "charge_factor", 1.0)
        if max_charge_w > 0:
            can_w = min(can_w, max_charge_w)
        hours = missing_wh / (can_w * eff) if can_w > 0 else 0
        count = max(1, math.ceil(hours * 3600 / seconds))
        power = round(min(can_w, missing_wh / eff / (count * seconds / 3600)), 1)

        def allowed(start: datetime, end: datetime) -> bool:
            """Never two full charges at the same time."""
            return not any(start < p.end and end > p.start for p in planned)

        def length(
            i: int,
            count: int = count,
            missing_wh: float = missing_wh,
            can_w: float = can_w,
            eff: float = eff,
            battery_id: str = config.id,
        ) -> int | None:
            """Slots from ``i`` needed to charge ``missing_wh`` within the
            room per slot (None: not within the prices)."""
            if room is None:
                return count
            energy, n = 0.0, 0
            while energy < missing_wh - 1e-6:
                if i + n >= len(slots) or n > 4 * count + 96:
                    return None
                w = min(can_w, max(room(slots[i + n][0], battery_id), 0.0))
                energy += w * eff * seconds / 3600
                n += 1
            return max(n, count)

        # Before the deadline if a block fits; else (the deadline is closer
        # than the block takes) within the window, as when it is overdue.
        ends = [latest_end]
        if deadline > now and (late := min(now + window, horizon_end)) > latest_end:
            ends.append(late)
        best: tuple[float, int, float, int, float] | None = None
        for latest_end in ends:
            # (rank, index, cost, slots, power)
            best = None
            for i in range(len(slots) - count + 1):
                n = length(i)
                if n is None:
                    break
                block = slots[i : i + n]
                start, end = block[0][0], block[-1][0] + step
                if end > latest_end:
                    break
                if block[-1][0] - start != step * (n - 1):
                    continue  # gap in the prices
                if not allowed(start, end):
                    continue  # another battery charges fully then
                # What the energy charged costs: per slot the price of the energy
                # charged in it (a slot the limits squeeze counts for less).
                block_w = power if room is None else can_w
                cost = left = 0.0
                left = missing_wh
                for when, price in block:
                    w = (
                        block_w
                        if room is None
                        else min(block_w, max(room(when, config.id), 0.0))
                    )
                    energy = min(w * eff * seconds / 3600, left)
                    left -= energy
                    rate = slot_price(when, price, w) if slot_price else price
                    cost += rate * energy / 1000
                rank = cost
                if (
                    preferred_day is not None
                    and dt_util.as_local(start).weekday() != preferred_day
                ):
                    rank += 1000  # only when the preferred day is not possible
                if best is None or rank < best[0]:
                    # With limits per slot: at the most it can in every slot (the
                    # length counted on that; finalise stops at 100 %).
                    best = (
                        rank,
                        i,
                        cost,
                        n,
                        power if room is None else round(can_w, 1),
                    )
            if best is not None:
                break
        if best is None:
            continue
        start = slots[best[1]][0]
        end = start + step * best[3]
        candidates = [price for when, price in slots if when + step <= latest_end]
        planned.append(
            FullCharge(
                config.id,
                config.name,
                start,
                end,
                deadline,
                last_full.get(config.id),
                best[4],
                # The average price of the energy charged.
                round(best[2] / (missing_wh / 1000), 5) if missing_wh > 0 else None,
                round(sum(candidates) / len(candidates), 5) if candidates else None,
            )
        )
    return planned
