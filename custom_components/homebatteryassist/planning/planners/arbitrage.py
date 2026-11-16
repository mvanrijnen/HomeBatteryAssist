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
cost, so energy is kept for expected peaks. ``max_cycles_per_day``: when the
cheapest plan cycles more, discharging gets an extra cost per kWh, raised
(bisection) until every day is within the limit.

Without prices arbitrage is not possible and falls back to zero on the meter.

To make your own variant: copy this file (and change the relative imports, see
``nom.py``) to ``/config/homebatteryassist/planners/``.
"""

from __future__ import annotations

import math
from datetime import date

from homeassistant.util import dt as dt_util

from .base import Planner, PlannerInput, PlannerResult, grid_cost, may_discharge
from .nom import follow

SOC_STEPS = 100  # resolution of the stored energy (1 % of the usable range)
CYCLE_SEARCH_STEPS = 6  # bisection steps for the cycle limit
PEAK_PENALTY = 5.0  # extra cost per kWh imported above the peak limit


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
    extra = penalty + rules.min_margin  # per kWh discharged, steering only
    step = span / SOC_STEPS
    levels = SOC_STEPS + 1
    count = len(slots)

    # Value of energy left at the end: what it saves later, at the average price.
    avg_price = sum(s.price for s in slots) / count
    terminal = [-(i * step) / 1000 * avg_price * eff for i in range(levels)]

    # Charge hysteresis: a charge may not *start* in the top band below the
    # maximum; the state remembers whether the previous slot was charging.
    band = rules.charge_hysteresis * battery.capacity_wh / 100
    top = (
        levels
        if band <= 0
        else max(int((battery.ceiling_wh - band - battery.floor_wh) / step), 0)
    )
    flags = (0, 1) if band > 0 else (0,)
    # Next level per slot, flag and level; a fraction means "cover the house
    # load, using part of a level" (see below).
    best_next: list[list[list[float]]] = [
        [[0] * levels for _ in flags] for _ in range(count)
    ]
    future = [terminal for _ in flags]
    for t in range(count - 1, -1, -1):
        slot = slots[t]
        hours, net, price = slot.hours, slot.net_w, slot.price
        export = slot.export_price if slot.export_price is not None else price
        up = int(slot.max_charge_w * hours * eff / step)
        down = int(slot.max_discharge_w * hours / eff / step)
        current = [[0.0] * levels for _ in flags]
        for flag in flags:
            choice = best_next[t][flag]
            for i in range(levels):
                best = math.inf
                best_j = i
                for j in range(max(0, i - down), min(levels - 1, i + up) + 1):
                    if j > i and i > top and not flag:
                        continue  # no top-up charge inside the hysteresis band
                    delta = (j - i) * step  # Wh stored
                    power = delta / (hours * eff) if delta >= 0 else delta * eff / hours
                    # Own use: never discharge more than the house needs (no export).
                    if not allow_export and power < 0 and power < -max(net, 0.0) - 1e-6:
                        continue
                    if power < 0 and not may_discharge(rules, price):
                        continue
                    if (
                        power > max(-net, 0.0) + 1e-6
                        and rules.max_charge_price is not None
                        and price > rules.max_charge_price
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
                        + future[1 if (j > i and band > 0) else 0][j]
                    )
                    if cost < best:
                        best, best_j = cost, j
                # Covering a house load smaller than one level: discharge just
                # that, using a fraction of a level (valued as a mix of the two
                # levels). Without this a big battery could not cover small loads.
                need = max(net, 0.0)
                part = need * hours / eff / step if need > 0 else 0.0
                if (
                    0 < part < 1
                    and i > 0
                    and may_discharge(rules, price)
                    and need <= slot.max_discharge_w
                ):
                    cost = (
                        grid_cost(net - need, hours, price, export)
                        + need * hours / 1000 * data.cycle_cost
                        + need * hours / 1000 * extra
                        + part * future[0][i - 1]
                        + (1 - part) * future[0][i]
                    )
                    if cost < best:
                        best, best_j = cost, i - part
                current[flag][i] = best
                choice[i] = best_j
        future = current

    # Forward pass, following the real stored energy (the nearest level picks
    # the choice).
    stored = battery.stored_wh
    flag = 0
    powers = []
    for t, slot in enumerate(slots):
        i = min(max(round((stored - battery.floor_wh) / step), 0), levels - 1)
        j = best_next[t][flag][i]
        if j != int(j):
            # Cover the house load with part of a level.
            power = -min(
                max(slot.net_w, 0.0),
                max(stored - battery.floor_wh, 0.0) * eff / slot.hours,
            )
            flag = 0
        else:
            flag = 1 if (j > i and band > 0) else 0
            target = battery.floor_wh + int(j) * step
            delta = target - stored if j != i else 0.0
            power = (
                delta / (slot.hours * eff) if delta >= 0 else delta * eff / slot.hours
            )
        power = max(min(power, slot.max_charge_w), -slot.max_discharge_w)
        if not allow_export and power < 0:
            power = max(power, -max(slot.net_w, 0.0))  # own use: no export
        stored += power * slot.hours * eff if power >= 0 else power * slot.hours / eff
        powers.append(power)
    return powers


class ArbitragePlanner(Planner):
    """Cost-optimal for own use (no battery energy to the grid)."""

    key = "arbitrage"
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
            low, high = 0.0, 0.5  # extra cost per kWh discharged
            best = _optimise(data, self.allow_export, high)
            while not within(best) and high < 8:
                low, high = high, high * 2
                best = _optimise(data, self.allow_export, high)
            for _ in range(CYCLE_SEARCH_STEPS):
                middle = (low + high) / 2
                candidate = _optimise(data, self.allow_export, middle)
                if within(candidate):
                    high, best = middle, candidate
                else:
                    low = middle
            powers = best
        return PlannerResult(powers, strategy=self.key)


class ArbitrageFullPlanner(ArbitragePlanner):
    """Maximum profit: may also discharge to the grid."""

    key = "arbitrage_full"
    name = "Full arbitrage"
    allow_export = True
