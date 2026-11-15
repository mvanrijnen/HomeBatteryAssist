"""Battery plan over the planning window, per mode (advice; no control yet).

Modes (more will follow):

- ``nom`` (nul op de meter / zero on the meter): charge with PV surplus,
  discharge on shortage, never from or to the grid on purpose.
- ``arbitrage`` (for own use): cost-optimal; may also charge from the grid when
  cheap, and discharges to cover the own consumption when expensive, but never
  exports battery energy to the grid.
- ``arbitrage_full`` (maximum profit): like arbitrage, but may also discharge
  to the grid when the export price makes that worthwhile.

- ``manual``: always a fixed power (``planning.schedule``);
- ``time_slots``: the actions of the configured time slots, zero on the meter
  outside them.

Peak shaving (``peak_w`` > 0, arbitrage modes): grid import above ``peak_w``
(all phases together) gets a high extra cost, so the plan keeps energy in
reserve for expected peaks and does not charge into a peak.

Both arbitrage modes respect ``max_cycles_per_day`` (full cycles = energy
discharged / capacity, per local day): when the cheapest plan cycles more,
discharging gets an extra cost per kWh, raised (bisection) until every day is
within the limit; the reported costs stay the real ones.

Both are always calculated, with the expected cost compared with no battery,
so their returns can be compared. For arbitrage the planner chooses per slot
the battery power that minimises the expected energy cost over the window:

    cost = sum(grid import * price - grid export * export price)
         + cycle_cost * energy through the battery
         - value of the energy left at the end

with grid = house - PV + battery power (+ charging). Solved exactly by dynamic
programming over the stored energy, discretised in ``SOC_STEPS`` steps, within
the batteries' power limits, min/max state of charge and round-trip efficiency
(split evenly over charging and discharging). All batteries are planned
together as one.

Optional ``limits`` per slot (charge, discharge in W) keep the grid
connection's phases within their maximum current (``phase_limit``); a slot
where they made the batteries charge or discharge less is marked ``limited``.

Without prices arbitrage is not possible and falls back to nom.
The plan is designed so it can later be turned into battery commands 1:1.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from homeassistant.util import dt as dt_util

from ..forecasts.consumption import ForecastSlot
from ..inputs.batteries import BatteryState
from ..inputs.prices import PricePoint
from .schedule import Target

SOC_STEPS = 100  # resolution of the stored energy (1 % of the usable range)
DEFAULT_EXPORT_FACTOR = 1.0  # export earns the import price (net metering)
DEFAULT_CYCLE_COST = 0.02  # per kWh through the battery (wear)
MODE_NOM = "nom"
MODE_ARBITRAGE = "arbitrage"
MODE_ARBITRAGE_FULL = "arbitrage_full"
MODE_MANUAL = "manual"
MODE_TIME_SLOTS = "time_slots"
PLAN_MODES = (
    MODE_NOM,
    MODE_ARBITRAGE,
    MODE_ARBITRAGE_FULL,
    MODE_TIME_SLOTS,
    MODE_MANUAL,
)
FIXED_MODES = (MODE_MANUAL, MODE_TIME_SLOTS)
ARBITRAGE_MODES = (MODE_ARBITRAGE, MODE_ARBITRAGE_FULL)
CYCLE_SEARCH_STEPS = 6  # bisection steps for the cycle limit
PEAK_PENALTY = 5.0  # extra cost per kWh imported above the peak limit
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
    limited: bool = False  # less power because of the phase limits
    export_price: float | None = None  # what exported energy earns in this slot
    reason: str | None = None  # time slot name / "manual" in the fixed modes


@dataclass(frozen=True, slots=True)
class BatteryPlan:
    """The plan and what it is expected to bring."""

    mode: str  # requested mode
    strategy: str  # mode actually used (arbitrage falls back to nom without prices)
    slots: list[PlanSlot]
    cost: float | None  # expected cost with the plan (price unit x kWh)
    cost_without: float | None  # expected cost without battery
    capacity_kwh: float = 0.0  # behind the state of charge in the slots
    value_per_kwh: float = 0.0  # value of stored energy (avg price x efficiency)

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


def _grid_cost(grid_w: float, hours: float, price: float, export_price: float) -> float:
    kwh = grid_w * hours / 1000
    return kwh * price if kwh >= 0 else kwh * export_price


def plan_batteries(
    states: Iterable[BatteryState],
    consumption: Sequence[ForecastSlot],
    pv_wh: Mapping[datetime, float],
    prices: Sequence[PricePoint],
    *,
    mode: str = DEFAULT_PLAN_MODE,
    export_factor: float = DEFAULT_EXPORT_FACTOR,
    cycle_cost: float = DEFAULT_CYCLE_COST,
    limits: Mapping[datetime, tuple[float, float]] | None = None,
    export_prices: Sequence[PricePoint] = (),
    max_cycles_per_day: float = 0.0,
    peak_w: float = 0.0,
    target: Callable[[datetime], Target | None] | None = None,
) -> BatteryPlan | None:
    """Plan the batteries in ``mode`` over the consumption slots; None without batteries.

    ``export_prices``: what exported energy earns per period; where it is not
    known, the import price x ``export_factor``.
    """
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
        max_c, max_d = (limits or {}).get(
            slot.start, (pack.max_charge, pack.max_discharge)
        )
        price = _price_at(prices, slot.start)
        export = _price_at(export_prices, slot.start)
        if export is None and price is not None:
            export = price * export_factor
        slots.append(
            (
                slot,
                hours,
                net,
                price,
                max(min(max_c, pack.max_charge), 0.0),
                max(min(max_d, pack.max_discharge), 0.0),
                export,
            )
        )

    if not slots:
        return None
    priced = all(s[3] is not None for s in slots)
    if mode in ARBITRAGE_MODES and priced:
        return _optimise_limited(
            pack,
            slots,
            cycle_cost,
            mode,
            mode == MODE_ARBITRAGE_FULL,
            max_cycles_per_day,
            peak_w,
        )
    if mode in FIXED_MODES:
        return _nom(pack, slots, cycle_cost, mode, priced, target)
    return _nom(pack, slots, cycle_cost, mode, priced)


def cycles_per_day(plan: BatteryPlan) -> dict[date, float]:
    """Full cycles per local day: energy discharged / capacity."""
    days: dict[date, float] = {}
    if not plan.capacity_kwh:
        return days
    for slot in plan.slots:
        if slot.power_w < 0:
            hours = (slot.end - slot.start).total_seconds() / 3600
            day = dt_util.as_local(slot.start).date()
            days[day] = days.get(day, 0.0) - slot.power_w * hours / 1000
    return {d: kwh / plan.capacity_kwh for d, kwh in days.items()}


def _optimise_limited(
    pack: _Pack,
    slots: list,
    cycle_cost: float,
    mode: str,
    allow_export: bool,
    max_cycles: float,
    peak_w: float = 0.0,
) -> BatteryPlan:
    """The cheapest plan within ``max_cycles`` full cycles per day (0 = no limit)."""
    plan = _optimise(pack, slots, cycle_cost, mode, allow_export, peak_w=peak_w)

    def within(p: BatteryPlan) -> bool:
        return max(cycles_per_day(p).values(), default=0.0) <= max_cycles + 0.01

    if max_cycles <= 0 or within(plan):
        return plan
    low, high = 0.0, 0.5  # extra cost per kWh discharged
    best = _optimise(pack, slots, cycle_cost, mode, allow_export, high, peak_w)
    while not within(best) and high < 8:
        low, high = high, high * 2
        best = _optimise(pack, slots, cycle_cost, mode, allow_export, high, peak_w)
    for _ in range(CYCLE_SEARCH_STEPS):
        middle = (low + high) / 2
        candidate = _optimise(
            pack, slots, cycle_cost, mode, allow_export, middle, peak_w
        )
        if within(candidate):
            high, best = middle, candidate
        else:
            low = middle
    return best


def _nom(
    pack: _Pack,
    slots: list,
    cycle_cost: float,
    mode: str,
    priced: bool,
    target: Callable[[datetime], Target | None] | None = None,
) -> BatteryPlan:
    """Zero on the meter: charge with surplus, discharge on shortage.

    With ``target`` (manual / time slots): its fixed action where it gives one.
    """
    stored = pack.stored
    result: list[PlanSlot] = []
    cost_with = cost_without = 0.0
    for slot, hours, net, price, max_c, max_d, export in slots:
        power = 0.0
        fixed = target(slot.start) if target else None
        if fixed is not None:
            if fixed.power_w > 0:
                top = pack.ceiling
                if fixed.soc_limit is not None:
                    top = min(top, fixed.soc_limit * pack.capacity / 100)
                room = max(top - stored, 0.0)
                power = min(fixed.power_w, max_c, room / (hours * pack.eff))
                stored += power * hours * pack.eff
            elif fixed.power_w < 0:
                bottom = pack.floor
                if fixed.soc_limit is not None:
                    bottom = max(bottom, fixed.soc_limit * pack.capacity / 100)
                available = max(stored - bottom, 0.0)
                power = -min(-fixed.power_w, max_d, available * pack.eff / hours)
                stored += power * hours / pack.eff
        elif net < 0:
            room = max(pack.ceiling - stored, 0.0)
            power = min(-net, max_c, room / (hours * pack.eff))
            stored += power * hours * pack.eff
        elif net > 0:
            available = max(stored - pack.floor, 0.0)
            power = -min(net, max_d, available * pack.eff / hours)
            stored += power * hours / pack.eff
        if priced:
            cost_with += _grid_cost(net + power, hours, price, export)
            cost_with += abs(power) * hours / 1000 * cycle_cost
            cost_without += _grid_cost(net, hours, price, export)
        result.append(
            PlanSlot(
                slot.start,
                slot.end,
                round(power, 1) + 0.0,  # no "-0.0"
                round(stored / pack.capacity * 100, 1),
                round(net + power, 1),
                price,
                _limited(pack, power, max_c, max_d),
                export,
                fixed.reason if fixed is not None else None,
            )
        )
    strategy = mode if mode in FIXED_MODES else MODE_NOM
    if not priced:
        return BatteryPlan(mode, strategy, result, None, None)
    avg_price = sum(s[3] for s in slots) / len(slots)
    cost_with += (pack.stored - stored) / 1000 * avg_price * pack.eff
    return BatteryPlan(
        mode,
        strategy,
        result,
        round(cost_with, 4),
        round(cost_without, 4),
        pack.capacity / 1000,
        avg_price * pack.eff,
    )


def _optimise(
    pack: _Pack,
    slots: list,
    cycle_cost: float,
    mode: str,
    allow_export: bool = False,
    penalty: float = 0.0,
    peak_w: float = 0.0,
) -> BatteryPlan:
    """Dynamic programming over the stored energy (backward), then forward.

    ``penalty``: extra cost per kWh discharged, only to steer the choices
    (cycle limit); it is not part of the reported costs.
    """
    span = max(pack.ceiling - pack.floor, 0.0)
    if span <= 0:
        return _nom(pack, slots, cycle_cost, mode, True)
    step = span / SOC_STEPS
    levels = SOC_STEPS + 1
    energy = [pack.floor + i * step for i in range(levels)]
    count = len(slots)

    # Value of energy left at the end: what it saves later, at the average price.
    avg_price = sum(s[3] for s in slots) / count
    terminal = [-(e - pack.floor) / 1000 * avg_price * pack.eff for e in energy]

    best_next: list[list[int]] = [[0] * levels for _ in range(count)]
    future = terminal
    for t in range(count - 1, -1, -1):
        _slot, hours, net, price, max_c, max_d, export = slots[t]
        up = int(max_c * hours * pack.eff / step)
        down = int(max_d * hours / pack.eff / step)
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
                # Own use: never discharge more than the house needs (no export).
                if not allow_export and power < 0 and power < -max(net, 0.0) - 1e-6:
                    continue
                cost = (
                    _grid_cost(net + power, hours, price, export)
                    + abs(power) * hours / 1000 * cycle_cost
                    + (-power * hours / 1000 * penalty if power < 0 else 0.0)
                    + (
                        max(net + power - peak_w, 0.0) * hours / 1000 * PEAK_PENALTY
                        if peak_w > 0
                        else 0.0
                    )
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
    for t, (slot, hours, net, price, max_c, max_d, export) in enumerate(slots):
        j = best_next[t][i]
        delta = (j - i) * step
        power = delta / (hours * pack.eff) if delta >= 0 else delta * pack.eff / hours
        cost_with += _grid_cost(net + power, hours, price, export)
        cost_with += abs(power) * hours / 1000 * cycle_cost
        cost_without += _grid_cost(net, hours, price, export)
        result.append(
            PlanSlot(
                slot.start,
                slot.end,
                round(power, 1) + 0.0,  # no "-0.0"
                round(energy[j] / pack.capacity * 100, 1),
                round(net + power, 1),
                price,
                _limited(pack, power, max_c, max_d),
                export,
            )
        )
        i = j
    # Count the change in stored energy at its value, so "with" and "without"
    # are comparable over the same window.
    cost_with += (pack.stored - energy[i]) / 1000 * avg_price * pack.eff
    return BatteryPlan(
        mode,
        mode,
        result,
        round(cost_with, 4),
        round(cost_without, 4),
        pack.capacity / 1000,
        avg_price * pack.eff,
    )


def _limited(pack: _Pack, power: float, max_c: float, max_d: float) -> bool:
    """Whether the phase limits held the power back in this slot."""
    if power > 0:
        return max_c < pack.max_charge - 1 and power >= max_c - 50
    if power < 0:
        return max_d < pack.max_discharge - 1 and -power >= max_d - 50
    return False


def slot_costs(
    plan: BatteryPlan, export_factor: float, cycle_cost: float
) -> list[float]:
    """Expected cost per slot of a plan (grid cost + battery wear)."""
    costs = []
    for slot in plan.slots:
        hours = (slot.end - slot.start).total_seconds() / 3600
        cost = abs(slot.power_w) * hours / 1000 * cycle_cost
        if slot.price is not None:
            export = (
                slot.export_price
                if slot.export_price is not None
                else slot.price * export_factor
            )
            cost += _grid_cost(slot.grid_w, hours, slot.price, export)
        costs.append(cost)
    return costs


def compare_modes(
    plans: dict[str, BatteryPlan],
    first: str,
    second: str,
    export_factor: float,
    cycle_cost: float,
) -> list[tuple[datetime, float]]:
    """Cumulative advantage of ``first`` over ``second`` per slot (+ = cheaper).

    Includes the value of the difference in stored energy at that moment, so
    the last value equals the difference in expected saving.
    """
    a, b = plans.get(first), plans.get(second)
    if a is None or b is None or a.cost is None or b.cost is None:
        return []
    total = 0.0
    series = []
    for slot, slot_b, cost_a, cost_b in zip(
        a.slots,
        b.slots,
        slot_costs(a, export_factor, cycle_cost),
        slot_costs(b, export_factor, cycle_cost),
        strict=False,
    ):
        total += cost_b - cost_a
        stored = (slot.soc - slot_b.soc) / 100 * a.capacity_kwh * a.value_per_kwh
        series.append((slot.start, round(total + stored, 4)))
    return series
