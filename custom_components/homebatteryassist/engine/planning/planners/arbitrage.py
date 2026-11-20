"""Built-in planners: arbitrage and full arbitrage.

- ``arbitrage`` (for own use): cost-optimal; may also charge from the grid when
  cheap, and discharges to cover the own consumption when expensive, but never
  exports battery energy to the grid.
- ``arbitrage_full`` (maximum profit): like arbitrage, but may also discharge
  to the grid when the export price makes that worthwhile.

The planner chooses per slot the battery power that minimises the expected
energy cost over the window:

    cost = sum(grid import * price - grid export * export price)
         + cycle_cost * energy through the battery
         - value of the energy left at the end

with grid = house - PV + battery power (+ charging). Solved exactly by dynamic
programming over the stored energy, discretised in ``SOC_STEPS`` steps, within
the batteries' power limits, min/max state of charge and efficiency.

Peak shaving (``peak_w`` > 0): grid import above ``peak_w`` gets a high extra
cost, so energy is kept for expected peaks; below the peak reserve
(``peak_floor_wh``) only that import is discharged for. Night reserve
(``reserve_wh`` per slot): never discharged below during the night; where it is
not there when the sun comes up (``reserve_due``), the missing energy costs
``RESERVE_PENALTY`` per kWh, so it is charged from the grid at the cheapest
moment before. ``max_cycles_per_day``: when the
cheapest plan cycles more, discharging gets an extra cost per kWh, raised
(bisection) until every day is within the limit.

Without prices arbitrage is not possible and falls back to zero on the meter.

To make your own variant: copy this file (and change the relative imports, see
``nom.py``) to ``/config/homebatteryassist/planners/``.
"""

from __future__ import annotations

import math
from datetime import date
from typing import ClassVar

from homeassistant.util import dt as dt_util

from .base import (
    Planner,
    PlannerInput,
    PlannerResult,
    discharge_room,
    grid_cost,
    may_discharge,
    outlook_split,
    stored_value,
)
from .zero_on_meter import follow

SOC_STEPS = 100  # resolution of the stored energy (1 % of the usable range)
CYCLE_SEARCH_STEPS = 6  # bisection steps for the cycle limit
PEAK_PENALTY = 5.0  # extra cost per kWh imported above the peak limit
RESERVE_PENALTY = 5.0  # per kWh of night reserve missing when the sun comes up
MIN_GAIN_PER_KWH = 0.01  # a cycle must bring at least this per kWh discharged


def _cycles_per_day(data: PlannerInput, powers: list[float]) -> dict[date, float]:
    days: dict[date, float] = {}
    for slot, power in zip(data.slots, powers, strict=False):
        if power < 0:
            day = dt_util.as_local(slot.start).date()
            days[day] = days.get(day, 0.0) - power * slot.hours / 1000
    capacity = data.battery.capacity_wh / 1000
    return {d: kwh / capacity for d, kwh in days.items()} if capacity else {}


def _optimise(
    data: PlannerInput, allow_export: bool, penalty: float = 0.0
) -> list[float]:
    """Dynamic programming over the stored energy (backward), then forward.

    ``penalty``: extra cost per kWh discharged, only to steer the choices
    (cycle limit).
    """
    battery = data.battery
    rules = data.rules
    eff = battery.efficiency
    span = max(battery.ceiling_wh - battery.floor_wh, 0.0)
    slots = data.slots
    # Per kWh discharged, steering only: the user's minimum margin on top of
    # a built-in floor, so a cycle that brings next to nothing is not done.
    extra = penalty + rules.min_margin + MIN_GAIN_PER_KWH
    step = span / SOC_STEPS
    levels = SOC_STEPS + 1
    count = len(slots)

    def level(wh: float) -> int:
        """The lowest level at or above ``wh`` stored."""
        if step <= 0 or wh <= battery.floor_wh:
            return 0
        return min(math.ceil((wh - battery.floor_wh) / step - 1e-9), levels - 1)

    # Night reserve per slot and the peak reserve, as levels.
    night = [level(s.reserve_wh) for s in slots]
    peak_level = level(battery.peak_floor_wh) if data.peak_w > 0 else 0

    # Value of energy left at the end: what it saves later, at the average
    # price, minus what using it then costs (wear, the minimum gain), as a
    # discharge now pays them too; else with flat prices nothing is used.
    avg_price = sum(s.price for s in slots) / count
    # (Not the cycle limit's steering penalty: that is for discharging now.)
    later = max(
        avg_price * eff - data.cycle_cost - rules.min_margin - MIN_GAIN_PER_KWH, 0.0
    )
    # The sun after the window fills the battery again (``Outlook``): of what
    # is left, the part above what the house uses before that sun plus the
    # room the surplus cannot fill only pushes that surplus to the grid —
    # worth its export price, not the import price. (So in summer the battery
    # is used in the evening and night instead of the grid.)
    keep, overflow = outlook_split(data, span, eff, later)
    terminal = [-stored_value(i * step, keep, later, overflow) for i in range(levels)]

    # Charge hysteresis (as zero on the meter and the virtual batteries): once
    # the battery was full, it does not charge again until it has dropped
    # below the band under its maximum. The state per level: 1 = free to
    # charge, 0 = held (it was full and is still in the band).
    band = rules.charge_hysteresis * battery.capacity_wh / 100
    top = (
        levels
        if band <= 0
        else max(int((battery.ceiling_wh - band - battery.floor_wh) / step), 0)
    )
    flags = (0, 1) if band > 0 else (0,)

    def after(flag: int, level: float) -> int:
        """The state after reaching ``level`` from state ``flag``."""
        if band <= 0:
            return 0
        if level >= levels - 1 - 1e-9:
            return 0  # full: held until it drops below the band
        if level <= top:
            return 1  # below the band: free again
        return flag

    # Next level per slot, flag and level; a fraction means "cover the house
    # load, using part of a level" (see below).
    best_next: list[list[list[float]]] = [
        [[0] * levels for _ in flags] for _ in range(count)
    ]
    # What a fractional next level means: "surplus" (store the solar
    # surplus), "cover" (cover the house load), "max" (charge at the slot's
    # full power, also from the grid).
    kinds: list[list[list[str]]] = [
        [[""] * levels for _ in flags] for _ in range(count)
    ]
    future = [terminal for _ in flags]
    for t in range(count - 1, -1, -1):
        slot = slots[t]
        hours, net, price = slot.hours, slot.net_w, slot.price
        export = slot.export_price if slot.export_price is not None else price
        up = int(slot.max_charge_w * hours * eff / step)
        down = int(slot.max_discharge_w * hours / eff / step)
        current = [[0.0] * levels for _ in flags]
        reserve = night[t]
        normal = max(reserve, peak_level)  # discharging below: restricted
        above_peak = max(net - data.peak_w, 0.0) if data.peak_w > 0 else 0.0
        # A periodic full charge in this slot (finalise adds it anyway): no
        # choice charges less than that.
        forced_w = data.forced.get(slot.start, 0.0)
        for flag in flags:
            choice = best_next[t][flag]
            kind = kinds[t][flag]
            for i in range(levels):
                best = math.inf
                best_j: float = i
                best_kind = ""
                for j in range(max(0, i - down), min(levels - 1, i + up) + 1):
                    if j > i and i > top and not flag and forced_w <= 0:
                        continue  # no top-up charge inside the hysteresis band
                    delta = (j - i) * step  # Wh stored
                    power = delta / (hours * eff) if delta >= 0 else delta * eff / hours
                    if (
                        forced_w > 0
                        and power < forced_w - 1e-6
                        and j < min(levels - 1, i + up)
                    ):
                        continue  # less than the full charge
                    # Own use: never discharge more than the house needs (no export).
                    if not allow_export and power < 0 and power < -max(net, 0.0) - 1e-6:
                        continue
                    if power < 0 and not may_discharge(rules, price):
                        continue
                    if j < i and j < normal:
                        if j < reserve:
                            continue  # the night reserve stays
                        # Below the peak reserve: only for import above the peak.
                        deep = (min(i, normal) - j) * step * eff / hours
                        if deep > max(above_peak - (-power - deep), 0.0) + 1e-6:
                            continue
                    if (
                        power > max(-net, 0.0) + 1e-6
                        and rules.max_charge_price is not None
                        and price > rules.max_charge_price
                        and forced_w <= 0  # a full charge must happen
                    ):
                        continue  # charging from the grid only when cheap enough
                    cost = (
                        grid_cost(net + power, hours, price, export)
                        + abs(power) * hours / 1000 * data.cycle_cost
                        + (-power * hours / 1000 * extra if power < 0 else 0.0)
                        + (
                            max(net + power - data.peak_w, 0.0)
                            * hours
                            / 1000
                            * PEAK_PENALTY
                            if data.peak_w > 0
                            else 0.0
                        )
                        + future[after(flag, j)][j]
                    )
                    if slot.reserve_due and j < reserve:
                        cost += (reserve - j) * step / 1000 * RESERVE_PENALTY
                    if cost < best:
                        best, best_j, best_kind = cost, j, ""
                # Covering the house load exactly: discharge just that, also
                # when it is not a whole number of levels (valued as a mix of
                # the two levels around it). Without this the plan could only
                # discharge whole levels (e.g. 331 or 663 W for a 640 W load)
                # and would leave energy unused.
                # (At most the slot's discharge power: a larger load is
                # covered as far as it goes, not in whole levels only.)
                need = min(max(net, 0.0), slot.max_discharge_w)
                part = need * hours / eff / step if need > 0 else 0.0
                target = i - part
                if (
                    part > 0
                    and part != int(part)
                    and target >= normal
                    and may_discharge(rules, price)
                    and forced_w <= 0
                ):
                    low = int(target)
                    frac = target - low
                    cost = (
                        grid_cost(net - need, hours, price, export)
                        + need * hours / 1000 * data.cycle_cost
                        + need * hours / 1000 * extra
                        + (
                            max(net - need - data.peak_w, 0.0)
                            * hours
                            / 1000
                            * PEAK_PENALTY
                            if data.peak_w > 0
                            else 0.0
                        )
                        + (1 - frac) * future[after(flag, low)][low]
                        + frac
                        * future[after(flag, min(low + 1, levels - 1))][
                            min(low + 1, levels - 1)
                        ]
                    )
                    if slot.reserve_due and target < reserve:
                        cost += (reserve - target) * step / 1000 * RESERVE_PENALTY
                    if cost < best:
                        best, best_j, best_kind = cost, target, "cover"
                # Storing the solar surplus exactly: charge just that, also
                # when it is not a whole number of levels (else a small surplus
                # could only be exported, or rounded up with grid power).
                surplus = min(max(-net, 0.0), slot.max_charge_w)
                part = surplus * hours * eff / step if surplus > 0 else 0.0
                target = i + part
                if (
                    part > 0
                    and part != int(part)
                    and target <= levels - 1
                    and surplus >= forced_w - 1e-6
                    and not (i > top and not flag)
                ):
                    low = int(target)
                    frac = target - low
                    cost = (
                        grid_cost(net + surplus, hours, price, export)
                        + surplus * hours / 1000 * data.cycle_cost
                        + (1 - frac) * future[after(flag, low)][low]
                        + frac
                        * future[after(flag, min(low + 1, levels - 1))][
                            min(low + 1, levels - 1)
                        ]
                    )
                    if slot.reserve_due and target < reserve:
                        cost += (reserve - target) * step / 1000 * RESERVE_PENALTY
                    if cost < best:
                        best, best_j, best_kind = cost, target, "surplus"
                # Charging at the slot's full power (also from the grid),
                # when that is not a whole number of levels (a short slot or
                # a low power would else charge less or not at all).
                full_w = slot.max_charge_w
                part = full_w * hours * eff / step if full_w > 0 else 0.0
                target = i + part
                grid_part = full_w > max(-net, 0.0) + 1e-6
                if (
                    part > 0
                    and part != int(part)
                    and target <= levels - 1
                    and not (i > top and not flag)
                    and not (
                        grid_part
                        and rules.max_charge_price is not None
                        and price > rules.max_charge_price
                        and forced_w <= 0
                    )
                ):
                    low = int(target)
                    frac = target - low
                    cost = (
                        grid_cost(net + full_w, hours, price, export)
                        + full_w * hours / 1000 * data.cycle_cost
                        + (
                            max(net + full_w - data.peak_w, 0.0)
                            * hours
                            / 1000
                            * PEAK_PENALTY
                            if data.peak_w > 0
                            else 0.0
                        )
                        + (1 - frac) * future[after(flag, low)][low]
                        + frac
                        * future[after(flag, min(low + 1, levels - 1))][
                            min(low + 1, levels - 1)
                        ]
                    )
                    if slot.reserve_due and target < reserve:
                        cost += (reserve - target) * step / 1000 * RESERVE_PENALTY
                    if cost < best:
                        best, best_j, best_kind = cost, target, "max"
                current[flag][i] = best
                choice[i] = best_j
                kind[i] = best_kind
        future = current

    # Forward pass, following the real stored energy (the nearest level picks
    # the choice).
    stored = battery.stored_wh
    # Held when it is (nearly) full now; else free to charge.
    flag = 0 if band <= 0 or stored >= battery.ceiling_wh - 1.0 or battery.held else 1
    powers = []
    for t, slot in enumerate(slots):
        i = min(max(round((stored - battery.floor_wh) / step), 0), levels - 1)
        j = best_next[t][flag][i]
        kind = kinds[t][flag][i]
        if kind == "max":
            # Charge at the slot's full power.
            room = max(battery.ceiling_wh - stored, 0.0) / (slot.hours * eff)
            power = min(slot.max_charge_w, room)
        elif kind == "surplus" or (j != int(j) and j > i):
            # Store the solar surplus with part of a level.
            room = max(battery.ceiling_wh - stored, 0.0) / (slot.hours * eff)
            power = min(max(-slot.net_w, 0.0), room)
        elif kind == "cover" or j != int(j):
            # Cover the house load with part of a level.
            power = -min(max(slot.net_w, 0.0), discharge_room(data, slot, stored))
        else:
            target = battery.floor_wh + int(j) * step
            delta = target - stored if j != i else 0.0
            power = (
                delta / (slot.hours * eff) if delta >= 0 else delta * eff / slot.hours
            )
        power = max(min(power, slot.max_charge_w), -slot.max_discharge_w)
        if not allow_export and power < 0:
            power = max(power, -max(slot.net_w, 0.0))  # own use: no export
        stored += power * slot.hours * eff if power >= 0 else power * slot.hours / eff
        flag = after(flag, (stored - battery.floor_wh) / step)
        powers.append(power)
    return powers


WARM_SEARCH_STEPS = 3  # bisection steps when starting near the last penalty


class ArbitragePlanner(Planner):
    """Cost-optimal for own use (no battery energy to the grid)."""

    # The last cycle limit penalty per planner key (a warm start).
    _penalty: ClassVar[dict[str, float]] = {}

    key = "arbitrage"
    verified = True
    name = "Arbitrage"
    allow_export = False

    def plan(self, data: PlannerInput) -> PlannerResult:
        battery = data.battery
        if not data.priced or battery.ceiling_wh - battery.floor_wh <= 0:
            result = follow(data, False)
            result.strategy = "nom" if not data.priced else self.key
            return result
        powers = _optimise(data, self.allow_export)
        limit = data.max_cycles_per_day

        def within(candidate: list[float]) -> bool:
            return (
                max(_cycles_per_day(data, candidate).values(), default=0.0)
                <= limit + 0.01
            )

        if limit > 0 and not within(powers):
            # Extra cost per kWh discharged that keeps the cycles within the
            # limit. It hardly changes from one cycle to the next: the search
            # starts around the last one (a few runs instead of a dozen).
            last = self._penalty.get(self.key)
            steps = CYCLE_SEARCH_STEPS
            if last:
                low, high = last * 0.7, last * 1.3
                best = _optimise(data, self.allow_export, high)
                if within(best):
                    candidate = _optimise(data, self.allow_export, low)
                    if within(candidate):
                        low, high, best = 0.0, low, candidate  # lower than before
                    else:
                        steps = WARM_SEARCH_STEPS
                else:
                    low, high = high, high * 2
                    best = _optimise(data, self.allow_export, high)
                    while not within(best) and high < 8:
                        low, high = high, high * 2
                        best = _optimise(data, self.allow_export, high)
                    steps = WARM_SEARCH_STEPS
            else:
                low, high = 0.0, 0.5
                best = _optimise(data, self.allow_export, high)
                while not within(best) and high < 8:
                    low, high = high, high * 2
                    best = _optimise(data, self.allow_export, high)
            for _ in range(steps):
                middle = (low + high) / 2
                candidate = _optimise(data, self.allow_export, middle)
                if within(candidate):
                    high, best = middle, candidate
                else:
                    low = middle
            self._penalty[self.key] = high
            powers = best
        return PlannerResult(powers, strategy=self.key)


class ArbitrageFullPlanner(ArbitragePlanner):
    """Maximum profit: may also discharge to the grid."""

    key = "arbitrage_full"
    verified = False
    name = "Full arbitrage"
    allow_export = True
