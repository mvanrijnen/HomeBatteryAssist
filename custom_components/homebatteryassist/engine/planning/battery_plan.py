"""Battery plan over the planning window (advice; no control yet).

The plan itself is made by a planner module (``planning/planners``): the
built-in ones (``nom``, ``arbitrage``, ``arbitrage_full``, ``time_slots``,
``manual``) or the user's own from ``/config/homebatteryassist/planners``.
This module prepares the planner's input (consumption, PV, prices and the
limits per slot, all batteries as one) and keeps the final say: ``finalise``
cuts every requested power back to what the batteries, the phase limits, the
minimum/maximum state of charge and the user's price rules allow, and works
out the state of charge, the grid exchange and the expected cost compared
with no battery. Periodic full charges are inserted after that
(``full_charge``).

Optional ``limits`` per slot (charge, discharge in W) keep the grid
connection's phases within their maximum current (``phase_limit``); a slot
where they made the batteries charge or discharge less is marked ``limited``.
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
from ..modules.planners import (
    BUILTIN,
    Planner,
    PlannerBattery,
    PlannerInput,
    PlannerResult,
)
from ..modules.planners import PlannerSlot as _InSlot
from ..modules.planners.base import grid_cost, may_discharge
from .schedule import Target

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
class PlanRules:
    """User rules every plan respects (all optional; 0 / None = off).

    - ``reserve_soc``: never plan below this state of charge (%), e.g. as backup
      reserve; on top of each battery's own minimum;
    - ``max_charge_w`` / ``max_discharge_w``: all batteries together;
    - ``nom_target_w``: zero on the meter aims at this grid power (+ import);
    - ``min_discharge_price``: discharge only at or above this price;
    - ``max_charge_price``: charge from the grid only at or below this price
      (charging with surplus solar power is always fine);
    - ``min_margin``: an arbitrage cycle must bring at least this per kWh
      (on top of the wear cost).
    """

    reserve_soc: float = 0.0
    max_charge_w: float = 0.0
    max_discharge_w: float = 0.0
    nom_target_w: float = 0.0
    min_discharge_price: float | None = None
    max_charge_price: float | None = None
    min_margin: float = 0.0
    charge_hysteresis: float = 0.0  # % below max SoC before charging again


@dataclass(frozen=True, slots=True)
class _Pack:
    capacity: float  # Wh
    stored: float  # Wh now
    floor: float  # Wh at min SoC
    ceiling: float  # Wh at max SoC
    max_charge: float  # W
    max_discharge: float  # W
    eff: float  # one-way efficiency
    rules: PlanRules = PlanRules()


def _pack(
    states: Iterable[BatteryState], rules: PlanRules = PlanRules()
) -> _Pack | None:
    usable = [s for s in states if s.soc is not None and s.config.capacity_kwh > 0]
    if not usable:
        return None
    capacity = sum(s.config.capacity_kwh for s in usable) * 1000
    max_charge = sum(
        s.config.max_charge_w * getattr(s, "charge_factor", 1.0) for s in usable
    )
    max_discharge = sum(
        s.config.max_discharge_w * getattr(s, "discharge_factor", 1.0) for s in usable
    )
    if rules.max_charge_w > 0:
        max_charge = min(max_charge, rules.max_charge_w)
    if rules.max_discharge_w > 0:
        max_discharge = min(max_discharge, rules.max_discharge_w)
    return _Pack(
        capacity=capacity,
        stored=sum(s.soc * s.config.capacity_kwh * 10 for s in usable),
        floor=sum(
            min(max(s.config.min_soc, rules.reserve_soc), s.config.max_soc)
            * s.config.capacity_kwh
            * 10
            for s in usable
        ),
        ceiling=sum(s.config.max_soc * s.config.capacity_kwh * 10 for s in usable),
        max_charge=max_charge,
        max_discharge=max_discharge,
        rules=rules,
        eff=math.sqrt(
            sum(s.config.efficiency * s.config.capacity_kwh for s in usable)
            / (capacity / 1000)
        ),
    )


def reach_times(
    slots: Sequence[PlanSlot], soc: float, floor_soc: float, ceiling_soc: float
) -> tuple[datetime | None, datetime | None]:
    """When the plan's state of charge, starting at ``soc`` (%), first reaches
    ``floor_soc`` (empty) and ``ceiling_soc`` (full), interpolated within the
    slot; ``None`` if not within the plan or already there."""
    empty = full = None
    margin = 0.5  # %
    for slot in slots:
        if empty is None and soc > floor_soc + margin >= slot.soc:
            part = (soc - floor_soc) / (soc - slot.soc)
            empty = slot.start + (slot.end - slot.start) * min(part, 1.0)
        if full is None and soc < ceiling_soc - margin <= slot.soc:
            part = (ceiling_soc - soc) / (slot.soc - soc)
            full = slot.start + (slot.end - slot.start) * min(part, 1.0)
        if empty is not None and full is not None:
            break
        soc = slot.soc
    return empty, full


def _price_at(prices: Sequence[PricePoint], when: datetime) -> float | None:
    for point in prices:
        if point.start <= when < point.end:
            return point.price
    return None


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
    rules: PlanRules = PlanRules(),
    planner: Planner | None = None,
    now: datetime | None = None,
) -> BatteryPlan | None:
    """Plan the batteries with ``planner`` (default: the built-in planner of
    ``mode``) over the consumption slots, checked by ``finalise``; None
    without batteries.

    ``export_prices``: what exported energy earns per period; where it is not
    known, the import price x ``export_factor``.
    """
    data = planner_input(
        states,
        consumption,
        pv_wh,
        prices,
        export_factor=export_factor,
        cycle_cost=cycle_cost,
        limits=limits,
        export_prices=export_prices,
        max_cycles_per_day=max_cycles_per_day,
        peak_w=peak_w,
        target=target,
        rules=rules,
        now=now,
    )
    if data is None:
        return None
    planner = planner or BUILTIN.get(mode) or BUILTIN[MODE_NOM]
    return finalise(data, planner.plan(data), mode)


def planner_input(
    states: Iterable[BatteryState],
    consumption: Sequence[ForecastSlot],
    pv_wh: Mapping[datetime, float],
    prices: Sequence[PricePoint],
    *,
    export_factor: float = DEFAULT_EXPORT_FACTOR,
    cycle_cost: float = DEFAULT_CYCLE_COST,
    limits: Mapping[datetime, tuple[float, float]] | None = None,
    export_prices: Sequence[PricePoint] = (),
    max_cycles_per_day: float = 0.0,
    peak_w: float = 0.0,
    target: Callable[[datetime], Target | None] | None = None,
    rules: PlanRules = PlanRules(),
    now: datetime | None = None,
) -> PlannerInput | None:
    """What a planner gets; None without batteries or slots."""
    pack = _pack(states, rules)
    if pack is None or not consumption:
        return None
    slots: list[_InSlot] = []
    for slot in consumption:
        hours = (slot.end - slot.start).total_seconds() / 3600
        if hours <= 0:
            continue
        hour = slot.start.replace(minute=0, second=0, microsecond=0)
        max_c, max_d = (limits or {}).get(
            slot.start, (pack.max_charge, pack.max_discharge)
        )
        price = _price_at(prices, slot.start)
        export = _price_at(export_prices, slot.start)
        if export is None and price is not None:
            export = price * export_factor
        slots.append(
            _InSlot(
                slot.start,
                slot.end,
                hours,
                slot.power_w,
                pv_wh.get(hour, 0.0),
                price,
                export,
                max(min(max_c, pack.max_charge), 0.0),
                max(min(max_d, pack.max_discharge), 0.0),
            )
        )
    if not slots:
        return None
    return PlannerInput(
        now or slots[0].start,
        slots,
        PlannerBattery(
            pack.capacity,
            pack.stored,
            pack.floor,
            pack.ceiling,
            pack.eff,
            pack.max_charge,
            pack.max_discharge,
        ),
        rules,
        cycle_cost,
        max_cycles_per_day,
        peak_w,
        target,
    )


def finalise(
    data: PlannerInput, result: PlannerResult | list[float], mode: str
) -> BatteryPlan:
    """HomeBatteryAssist's final check of a planner's requested powers.

    Every power is cut back to the slot's charge/discharge limit (batteries
    and phases), to the room up to the maximum and the energy above the
    minimum state of charge, and to the price rules (no discharging below the
    minimum discharge price, no charging from the grid above the maximum
    charge price) except for fixed actions the user set (manual / time
    slots). Then state of charge, grid exchange and costs are worked out.
    """
    if not isinstance(result, PlannerResult):
        result = PlannerResult(list(result))
    battery = data.battery
    rules = data.rules
    eff = battery.efficiency
    stored = battery.stored_wh
    reasons = result.reasons or []
    out: list[PlanSlot] = []
    cost_with = cost_without = 0.0
    for index, slot in enumerate(data.slots):
        try:
            requested = float(result.powers[index])
        except (IndexError, TypeError, ValueError):
            requested = 0.0
        if not math.isfinite(requested):
            requested = 0.0
        reason = reasons[index] if index < len(reasons) else None
        # Only a fixed action the user set (manual / time slot) may break the
        # price rules; a planner's own reason never does.
        fixed = data.target is not None and data.target(slot.start) is not None
        hours = slot.hours
        power = 0.0
        if requested > 0:
            power = min(
                requested,
                slot.max_charge_w,
                max(battery.ceiling_wh - stored, 0.0) / (hours * eff),
            )
            if (
                not fixed
                and rules.max_charge_price is not None
                and slot.price is not None
                and slot.price > rules.max_charge_price
            ):
                power = min(power, max(-slot.net_w, 0.0))  # only surplus PV
        elif requested < 0 and (fixed or may_discharge(rules, slot.price)):
            power = -min(
                -requested,
                slot.max_discharge_w,
                max(stored - battery.floor_wh, 0.0) * eff / hours,
            )
        power = max(power, 0.0) if requested > 0 else min(power, 0.0)
        stored += power * hours * eff if power >= 0 else power * hours / eff
        grid = slot.net_w + power
        if data.priced:
            export = slot.export_price if slot.export_price is not None else slot.price
            cost_with += grid_cost(grid, hours, slot.price, export)
            cost_with += abs(power) * hours / 1000 * data.cycle_cost
            cost_without += grid_cost(slot.net_w, hours, slot.price, export)
        out.append(
            PlanSlot(
                slot.start,
                slot.end,
                round(power, 1) + 0.0,  # no "-0.0"
                round(stored / battery.capacity_wh * 100, 1),
                round(grid, 1),
                slot.price,
                _limited(battery, power, slot.max_charge_w, slot.max_discharge_w),
                slot.export_price,
                reason,
            )
        )
    strategy = result.strategy or mode
    if not data.priced:
        return BatteryPlan(mode, strategy, out, None, None)
    avg_price = sum(s.price for s in data.slots) / len(data.slots)
    # Count the change in stored energy at its value, so "with" and "without"
    # are comparable over the same window.
    cost_with += (battery.stored_wh - stored) / 1000 * avg_price * eff
    return BatteryPlan(
        mode,
        strategy,
        out,
        round(cost_with, 4),
        round(cost_without, 4),
        battery.capacity_wh / 1000,
        avg_price * eff,
    )


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


def _limited(battery: PlannerBattery, power: float, max_c: float, max_d: float) -> bool:
    """Whether the phase limits held the power back in this slot."""
    if power > 0:
        return max_c < battery.max_charge_w - 1 and power >= max_c - 50
    if power < 0:
        return max_d < battery.max_discharge_w - 1 and -power >= max_d - 50
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
            cost += grid_cost(slot.grid_w, hours, slot.price, export)
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
