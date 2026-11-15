"""Battery plan over the planning window, per mode (advice; no control yet).

Modes (more will follow):

- ``nom`` (nul op de meter / zero on the meter): charge with PV surplus,
  discharge on shortage, never from or to the grid on purpose.
- ``arbitrage``: cost-optimal; may also charge from the grid when cheap and
  discharge (even to the grid) when expensive.

Both are always calculated, with the expected cost compared with no battery,
so their returns can be compared. For arbitrage the planner chooses per slot
the battery power that minimises the expected energy cost over the window:

    cost = sum(grid import * price - grid export * price * export_factor)
         + cycle_cost * energy through the battery
         - value of the energy left at the end

with grid = house - PV + battery power (+ charging). Solved exactly by dynamic
programming over the stored energy, discretised in ``SOC_STEPS`` steps, within
the batteries' power limits, min/max state of charge and round-trip efficiency
(split evenly over charging and discharging). All batteries are planned
together as one.

Without prices arbitrage is not possible and falls back to nom.
The plan is designed so it can later be turned into battery commands 1:1.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from ..forecasts.consumption import ForecastSlot
from ..inputs.batteries import BatteryState
from ..inputs.prices import PricePoint

SOC_STEPS = 100  # resolution of the stored energy (1 % of the usable range)
DEFAULT_EXPORT_FACTOR = 1.0  # export earns the import price (net metering)
DEFAULT_CYCLE_COST = 0.02  # per kWh through the battery (wear)
MODE_NOM = "nom"
MODE_ARBITRAGE = "arbitrage"
PLAN_MODES = (MODE_NOM, MODE_ARBITRAGE)
DEFAULT_PLAN_MODE = MODE_NOM


@dataclass(frozen=True, slots=True)
class PlanSlot:
    """Planned battery behaviour and resulting grid exchange in one slot."""

    start: datetime
    end: datetime
    power_w: float  # + charging / - discharging (grid side)
    soc: float  # % at the end of the slot (over all batteries)
    grid_w: float  # expected grid exchange with the plan, + import / - export
    price: float | None  # price used for this slot


@dataclass(frozen=True, slots=True)
class BatteryPlan:
    """The plan and what it is expected to bring."""

    mode: str  # requested mode
    strategy: str  # mode actually used (arbitrage falls back to nom without prices)
    slots: list[PlanSlot]
    cost: float | None  # expected cost with the plan (price unit x kWh)
    cost_without: float | None  # expected cost without battery

    @property
    def saving(self) -> float | None:
        """Expected saving of the plan compared with no battery."""
        if self.cost is None or self.cost_without is None:
            return None
        return self.cost_without - self.cost


@dataclass(frozen=True, slots=True)
class _Pack:
    capacity: float  # Wh
    stored: float  # Wh now
    floor: float  # Wh at min SoC
    ceiling: float  # Wh at max SoC
    max_charge: float  # W
    max_discharge: float  # W
    eff: float  # one-way efficiency


def _pack(states: Iterable[BatteryState]) -> _Pack | None:
    usable = [s for s in states if s.soc is not None and s.config.capacity_kwh > 0]
    if not usable:
        return None
    capacity = sum(s.config.capacity_kwh for s in usable) * 1000
    return _Pack(
        capacity=capacity,
        stored=sum(s.soc * s.config.capacity_kwh * 10 for s in usable),
        floor=sum(s.config.min_soc * s.config.capacity_kwh * 10 for s in usable),
        ceiling=sum(s.config.max_soc * s.config.capacity_kwh * 10 for s in usable),
        max_charge=sum(s.config.max_charge_w for s in usable),
        max_discharge=sum(s.config.max_discharge_w for s in usable),
        eff=math.sqrt(
            sum(s.config.efficiency * s.config.capacity_kwh for s in usable)
            / (capacity / 1000)
        ),
    )


def _price_at(prices: Sequence[PricePoint], when: datetime) -> float | None:
    for point in prices:
        if point.start <= when < point.end:
            return point.price
    return None


def _grid_cost(
    grid_w: float, hours: float, price: float, export_factor: float
) -> float:
    kwh = grid_w * hours / 1000
    return kwh * price if kwh >= 0 else kwh * price * export_factor


def plan_batteries(
    states: Iterable[BatteryState],
    consumption: Sequence[ForecastSlot],
    pv_wh: Mapping[datetime, float],
    prices: Sequence[PricePoint],
    *,
    mode: str = DEFAULT_PLAN_MODE,
    export_factor: float = DEFAULT_EXPORT_FACTOR,
    cycle_cost: float = DEFAULT_CYCLE_COST,
) -> BatteryPlan | None:
    """Plan the batteries in ``mode`` over the consumption slots; None without batteries."""
    pack = _pack(states)
    if pack is None or not consumption:
        return None

    slots = []
    for slot in consumption:
        hours = (slot.end - slot.start).total_seconds() / 3600
        if hours <= 0:
            continue
        hour = slot.start.replace(minute=0, second=0, microsecond=0)
        net = slot.power_w - pv_wh.get(hour, 0.0)  # + shortage / - surplus
        slots.append((slot, hours, net, _price_at(prices, slot.start)))

    if not slots:
        return None
    priced = all(price is not None for *_, price in slots)
    if mode == MODE_ARBITRAGE and priced:
        return _optimise(pack, slots, export_factor, cycle_cost, mode)
    return _nom(pack, slots, export_factor, cycle_cost, mode, priced)


def _nom(
    pack: _Pack,
    slots: list,
    export_factor: float,
    cycle_cost: float,
    mode: str,
    priced: bool,
) -> BatteryPlan:
    """Zero on the meter: charge with surplus, discharge on shortage."""
    stored = pack.stored
    result: list[PlanSlot] = []
    cost_with = cost_without = 0.0
    for slot, hours, net, price in slots:
        power = 0.0
        if net < 0:
            room = max(pack.ceiling - stored, 0.0)
            power = min(-net, pack.max_charge, room / (hours * pack.eff))
            stored += power * hours * pack.eff
        elif net > 0:
            available = max(stored - pack.floor, 0.0)
            power = -min(net, pack.max_discharge, available * pack.eff / hours)
            stored += power * hours / pack.eff
        if priced:
            cost_with += _grid_cost(net + power, hours, price, export_factor)
            cost_with += abs(power) * hours / 1000 * cycle_cost
            cost_without += _grid_cost(net, hours, price, export_factor)
        result.append(
            PlanSlot(
                slot.start,
                slot.end,
                round(power, 1) + 0.0,  # no "-0.0"
                round(stored / pack.capacity * 100, 1),
                round(net + power, 1),
                price,
            )
        )
    if not priced:
        return BatteryPlan(mode, MODE_NOM, result, None, None)
    avg_price = sum(p for *_, p in slots) / len(slots)
    cost_with += (pack.stored - stored) / 1000 * avg_price * pack.eff
    return BatteryPlan(
        mode, MODE_NOM, result, round(cost_with, 4), round(cost_without, 4)
    )


def _optimise(
    pack: _Pack, slots: list, export_factor: float, cycle_cost: float, mode: str
) -> BatteryPlan:
    """Dynamic programming over the stored energy (backward), then forward."""
    span = max(pack.ceiling - pack.floor, 0.0)
    if span <= 0:
        return _nom(pack, slots, export_factor, cycle_cost, mode, True)
    step = span / SOC_STEPS
    levels = SOC_STEPS + 1
    energy = [pack.floor + i * step for i in range(levels)]
    count = len(slots)

    # Value of energy left at the end: what it saves later, at the average price.
    avg_price = sum(p for *_, p in slots) / count
    terminal = [-(e - pack.floor) / 1000 * avg_price * pack.eff for e in energy]

    best_next: list[list[int]] = [[0] * levels for _ in range(count)]
    future = terminal
    for t in range(count - 1, -1, -1):
        _slot, hours, net, price = slots[t]
        up = int(pack.max_charge * hours * pack.eff / step)
        down = int(pack.max_discharge * hours / pack.eff / step)
        current = [0.0] * levels
        choice = best_next[t]
        for i in range(levels):
            best = math.inf
            best_j = i
            for j in range(max(0, i - down), min(levels - 1, i + up) + 1):
                delta = (j - i) * step  # Wh stored
                power = (
                    delta / (hours * pack.eff)
                    if delta >= 0
                    else delta * pack.eff / hours
                )
                cost = (
                    _grid_cost(net + power, hours, price, export_factor)
                    + abs(power) * hours / 1000 * cycle_cost
                    + future[j]
                )
                if cost < best:
                    best, best_j = cost, j
            current[i] = best
            choice[i] = best_j
        future = current

    # Forward pass from the current state of charge (nearest level).
    i = min(max(round((pack.stored - pack.floor) / step), 0), levels - 1)
    result: list[PlanSlot] = []
    cost_with = cost_without = 0.0
    for t, (slot, hours, net, price) in enumerate(slots):
        j = best_next[t][i]
        delta = (j - i) * step
        power = delta / (hours * pack.eff) if delta >= 0 else delta * pack.eff / hours
        cost_with += _grid_cost(net + power, hours, price, export_factor)
        cost_with += abs(power) * hours / 1000 * cycle_cost
        cost_without += _grid_cost(net, hours, price, export_factor)
        result.append(
            PlanSlot(
                slot.start,
                slot.end,
                round(power, 1) + 0.0,  # no "-0.0"
                round(energy[j] / pack.capacity * 100, 1),
                round(net + power, 1),
                price,
            )
        )
        i = j
    # Count the change in stored energy at its value, so "with" and "without"
    # are comparable over the same window.
    cost_with += (pack.stored - energy[i]) / 1000 * avg_price * pack.eff
    return BatteryPlan(
        mode, MODE_ARBITRAGE, result, round(cost_with, 4), round(cost_without, 4)
    )
