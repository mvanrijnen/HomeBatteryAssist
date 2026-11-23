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
from bisect import bisect_right
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any

from homeassistant.util import dt as dt_util

from ..forecast.consumption_forecast import ForecastSlot
from ..measure.battery_monitor import BatteryState
from ..sources.prices.price_points import PricePoint
from .planners import (
    BUILTIN,
    Planner,
    PlannerBattery,
    PlannerInput,
    PlannerResult,
)
from .planners import PlannerSlot as _InSlot
from .planners.base import (
    Outlook,
    PackMember,
    discharge_room,
    grid_cost,
    may_discharge,
    outlook_split,
    stored_value,
)
from .time_slots import Target

# Without an export price: the import price x this (no net metering; the
# coordinator always passes the setting).
DEFAULT_EXPORT_FACTOR = 0.25
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
    # Hours planned (the slot now only from now); None = the whole slot
    hours: float | None = None
    # Steering margin per kWh from/for the grid: the price is (partly) an
    # estimate (``PlanRules.estimated_margin``); 0 = published.
    price_margin: float = 0.0
    # Price thresholds (planners that know them, e.g. arbitrage): using the
    # batteries pays above ``use_above``, charging from the grid below
    # ``charge_below`` (after losses, wear, margins and the price rules).
    use_above: float | None = None
    charge_below: float | None = None

    @property
    def duration_h(self) -> float:
        """The planned hours of the slot (energy = power x this)."""
        if self.hours is not None:
            return self.hours
        return (self.end - self.start).total_seconds() / 3600


@dataclass(frozen=True, slots=True)
class BatteryPlan:
    """The plan and what it is expected to bring."""

    mode: str  # requested mode
    strategy: str  # mode actually used (arbitrage falls back to nom without prices)
    slots: list[PlanSlot]
    cost: float | None  # expected cost with the plan (price unit x kWh)
    cost_without: float | None  # expected cost without battery
    capacity_kwh: float = 0.0  # behind the state of charge in the slots
    value_per_kwh: float = 0.0  # stored energy: avg price x efficiency - wear
    start_soc: float | None = None  # % now (slot SoCs are at their end)
    # How finalise valued what is left (``outlook_split``): above ``keep_wh``
    # (over ``floor_wh``) only ``overflow_per_kwh``.
    floor_wh: float = 0.0
    keep_wh: float = math.inf
    overflow_per_kwh: float | None = None

    def stored_value(self, soc: float) -> float:
        """What the energy at ``soc`` % is worth, as the plan's costs count it
        (comparisons over time add up to the saving)."""
        wh = soc / 100 * self.capacity_kwh * 1000 - self.floor_wh
        overflow = (
            self.value_per_kwh
            if self.overflow_per_kwh is None
            else self.overflow_per_kwh
        )
        return stored_value(wh, self.keep_wh, self.value_per_kwh, overflow)

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
    - ``night_reserve_soc``: from the evening (the sun gone) until the sun is
      up again (``night_starts``) not below this state of charge; arbitrage
      charges from the grid for it before sunrise when needed, zero on the
      meter only keeps it;
    - ``peak_reserve_soc``: below this state of charge only discharge for
      grid import above the peak limit (with a peak limit);
    - ``max_charge_w`` / ``max_discharge_w``: all batteries together;
    - ``nom_target_w``: zero on the meter aims at this grid power (+ import);
    - ``min_discharge_price``: discharge only at or above this price;
    - ``max_charge_price``: charge from the grid only at or below this price
      (charging with surplus solar power is always fine);
    - ``min_margin``: an arbitrage cycle must bring at least this per kWh
      (on top of the wear cost);
    - ``estimated_margin``: per kWh charged from or discharged for the grid
      in a slot whose price is only estimated (not yet published): steering
      only, so the plan acts on an estimate only when it brings at least that
      much more than acting at a published price.
    """

    reserve_soc: float = 0.0
    night_reserve_soc: float = 0.0
    peak_reserve_soc: float = 0.0
    max_charge_w: float = 0.0
    max_discharge_w: float = 0.0
    nom_target_w: float = 0.0
    min_discharge_price: float | None = None
    max_charge_price: float | None = None
    min_margin: float = 0.0
    estimated_margin: float = 0.0
    charge_hysteresis: float = 0.0  # % below max SoC before charging again
    # Several batteries charge one after the other (the emptiest first, the
    # next only for what it cannot take at its full power), not all at once.
    charge_sequential: bool = False


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
    night_floor: float = 0.0  # Wh at the night reserve (0 = off)
    peak_floor: float = 0.0  # Wh at the peak reserve (0 = off)
    members: tuple[PackMember, ...] = ()
    held: bool = False  # charge hysteresis holds now (was full, still in band)


def _pack(
    states: Iterable[BatteryState],
    rules: PlanRules = PlanRules(),
    held: Iterable[str] = (),
) -> _Pack | None:
    usable = [s for s in states if s.soc is not None and s.config.capacity_kwh > 0]
    if not usable:
        return None
    # Charge hysteresis now: a battery that was full and has not dropped
    # below its band since (live state), so the plan starts as the batteries
    # do. The pack (one battery to the planners) is held only when every
    # battery is: one below its band or never full may still charge.
    band = rules.charge_hysteresis
    held_ids = set(held)
    is_held = band > 0 and all(
        s.soc >= s.config.max_soc - band
        and (
            getattr(s.config, "id", None) in held_ids
            or s.soc >= s.config.max_soc - 0.05
        )
        for s in usable
    )
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

    def one(s: BatteryState, soc: float) -> float:
        """Wh of one battery at ``soc`` (within its own min/max)."""
        if soc <= 0:
            return 0.0
        return (
            min(max(s.config.min_soc, rules.reserve_soc, soc), s.config.max_soc)
            * s.config.capacity_kwh
            * 10
        )

    def at(soc: float) -> float:
        """Wh over all batteries at ``soc`` (each within its own min/max)."""
        return sum(one(s, soc) for s in usable)

    def floor_of(s: BatteryState) -> float:
        return (
            min(max(s.config.min_soc, rules.reserve_soc), s.config.max_soc)
            * s.config.capacity_kwh
            * 10
        )

    def wh_of(s: BatteryState) -> float:
        return s.soc * s.config.capacity_kwh * 10

    def ceiling_of(s: BatteryState) -> float:
        return s.config.max_soc * s.config.capacity_kwh * 10

    # The pack as one battery, with the room of each battery: one above its
    # maximum (after a full charge) or below its minimum does not hide the
    # room of another; the final check keeps each within its own limits.
    # One battery has no others and no per-battery check: its own limits.
    above = below = 0.0
    if len(usable) > 1:
        above = sum(max(wh_of(s) - ceiling_of(s), 0.0) for s in usable)
        below = sum(max(floor_of(s) - wh_of(s), 0.0) for s in usable)
    return _Pack(
        capacity=capacity,
        stored=sum(wh_of(s) for s in usable),
        floor=max(sum(floor_of(s) for s in usable) - below, 0.0),
        ceiling=sum(ceiling_of(s) for s in usable) + above,
        max_charge=max_charge,
        max_discharge=max_discharge,
        rules=rules,
        # A battery below its minimum does not hide another's room at night
        # or under the peak reserve either (its shortfall to the minimum; a
        # battery between its minimum and the night level still counts at
        # the night level: the pack's reserve, which arbitrage charges for).
        night_floor=max(at(rules.night_reserve_soc) - below, 0.0),
        peak_floor=max(at(rules.peak_reserve_soc) - below, 0.0),
        eff=math.sqrt(
            sum(s.config.efficiency * s.config.capacity_kwh for s in usable)
            / (capacity / 1000)
        ),
        members=tuple(
            PackMember(
                s.config.capacity_kwh * 1000,
                s.soc * s.config.capacity_kwh * 10,
                min(max(s.config.min_soc, rules.reserve_soc), s.config.max_soc)
                * s.config.capacity_kwh
                * 10,
                s.config.max_soc * s.config.capacity_kwh * 10,
                math.sqrt(s.config.efficiency),
                s.config.max_charge_w * getattr(s, "charge_factor", 1.0),
                s.config.max_discharge_w * getattr(s, "discharge_factor", 1.0),
                getattr(s.config, "id", ""),
                one(s, rules.night_reserve_soc),
                one(s, rules.peak_reserve_soc),
            )
            for s in usable
        )
        if len(usable) > 1
        else (),
        held=is_held,
    )


def reach_times(
    slots: Sequence[PlanSlot],
    soc: float,
    floor_soc: float,
    ceiling_soc: float,
    now: datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    """When the plan's state of charge, starting at ``soc`` (%) now, first
    reaches ``floor_soc`` (empty) and ``ceiling_soc`` (full), interpolated
    within the slot (the slot now from ``now`` to its end); ``None`` if not
    within the plan or already there."""
    empty = full = None
    margin = 0.5  # %
    for slot in slots:
        if now is not None and slot.end <= now:
            continue  # already over
        begin = slot.start if now is None else max(slot.start, now)
        if empty is None and soc > floor_soc + margin >= slot.soc:
            part = (soc - floor_soc) / (soc - slot.soc)
            empty = begin + (slot.end - begin) * min(part, 1.0)
        if full is None and soc < ceiling_soc - margin <= slot.soc:
            part = (ceiling_soc - soc) / (slot.soc - soc)
            full = begin + (slot.end - begin) * min(part, 1.0)
        if empty is not None and full is not None:
            break
        soc = slot.soc
    return empty, full


SUN_W = 100.0  # expected PV (average W in the hour) from which the sun is up


def night_starts(
    consumption: Sequence[ForecastSlot], pv_wh: Mapping[datetime, float]
) -> set[datetime]:
    """The slots (by start) of the night reserve: per local day outside the
    first to the last slot with sun (expected PV >= ``SUN_W``), so from the
    evening until the sun is up again. Empty without a PV forecast (when the
    sun comes up is not known then); a day after the last day the PV
    forecast reaches is left out too, not taken as one long night (today's
    evening stays night, also from a source that sends daylight hours only)."""
    if not pv_wh:
        return set()
    days: dict[date, list[ForecastSlot]] = {}
    for slot in consumption:
        days.setdefault(dt_util.as_local(slot.start).date(), []).append(slot)
    result: set[datetime] = set()
    last_day = max(dt_util.as_local(start).date() for start in pv_wh)
    for day, slots in days.items():
        if day > last_day:
            continue  # beyond the PV forecast: when the sun is up is not known
        sun = [
            i
            for i, s in enumerate(slots)
            if pv_wh.get(s.start.replace(minute=0, second=0, microsecond=0), 0.0)
            >= SUN_W
        ]
        first, last = (sun[0], sun[-1]) if sun else (len(slots), -1)
        result.update(s.start for i, s in enumerate(slots) if i < first or i > last)
    return result


def _price_over(
    prices: Sequence[PricePoint], start: datetime, end: datetime
) -> float | None:
    """The price over a slot: the time-weighted average of the prices in it
    (e.g. four quarter-hour prices in an hour slot), over the part that has
    a price; None when no price covers the slot."""
    total = 0.0
    seconds = 0.0
    # Prices are in time order: start a little before the slot.
    first = max(bisect_right(prices, start, key=lambda p: p.start) - 1, 0)
    for point in prices[first:]:
        if point.start >= end:
            break
        overlap = (min(point.end, end) - max(point.start, start)).total_seconds()
        if overlap > 0:
            total += point.price * overlap
            seconds += overlap
    return total / seconds if seconds > 0 else None


def _estimated_share(
    prices: Sequence[PricePoint], start: datetime, end: datetime
) -> float:
    """The part (0..1) of the priced time of a slot whose price is only
    estimated (as ``_price_over`` weighs the prices)."""
    estimated = seconds = 0.0
    first = max(bisect_right(prices, start, key=lambda p: p.start) - 1, 0)
    for point in prices[first:]:
        if point.start >= end:
            break
        overlap = (min(point.end, end) - max(point.start, start)).total_seconds()
        if overlap > 0:
            seconds += overlap
            if point.estimated:
                estimated += overlap
    return estimated / seconds if seconds > 0 else 0.0


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
    forced: Mapping[datetime, float] | None = None,
    forced_by: Mapping[datetime, Mapping[str, float]] | None = None,
    member_limits: Mapping[datetime, Mapping[str, tuple[float, float]]] | None = None,
    phase_rooms: Mapping[datetime, Any] | None = None,
    outlook: Outlook | None = None,
    held: Iterable[str] = (),
    previous: BatteryPlan | None = None,
) -> BatteryPlan | None:
    """Plan the batteries with ``planner`` (default: the built-in planner of
    ``mode``) over the consumption slots, checked by ``finalise``; None
    without batteries.

    ``export_prices``: what exported energy earns per period; where it is not
    known, the import price x ``export_factor``. ``previous``: the plan of
    this mode from the cycle before (``PlannerInput.previous_w``).
    """
    prices = sorted(prices, key=lambda p: p.start)
    export_prices = sorted(export_prices, key=lambda p: p.start)
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
        forced=forced,
        forced_by=forced_by,
        member_limits=member_limits,
        phase_rooms=phase_rooms,
        outlook=outlook,
        held=held,
        previous=previous,
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
    forced: Mapping[datetime, float] | None = None,
    forced_by: Mapping[datetime, Mapping[str, float]] | None = None,
    member_limits: Mapping[datetime, Mapping[str, tuple[float, float]]] | None = None,
    phase_rooms: Mapping[datetime, Any] | None = None,
    outlook: Outlook | None = None,
    held: Iterable[str] = (),
    previous: BatteryPlan | None = None,
) -> PlannerInput | None:
    """What a planner gets; None without batteries or slots."""
    states = list(states)
    pack = _pack(states, rules, held)
    if pack is None or not consumption:
        return None
    night = night_starts(consumption, pv_wh) if pack.night_floor > 0 else set()
    slots: list[_InSlot] = []
    for slot in consumption:
        # The slot now has only the time left (it starts at the boundary
        # before now): a full slot of energy would not fit in it.
        begin = max(slot.start, now) if now is not None else slot.start
        hours = (slot.end - begin).total_seconds() / 3600
        if hours <= 0:
            continue
        hour = slot.start.replace(minute=0, second=0, microsecond=0)
        max_c, max_d = (limits or {}).get(
            slot.start, (pack.max_charge, pack.max_discharge)
        )
        # The slot now: the prices of the time left (quarter prices in an
        # hour slot), not of the whole slot.
        price = _price_over(prices, begin, slot.end)
        if price is None:
            price = _price_over(prices, slot.start, slot.end)
        export = _price_over(export_prices, begin, slot.end)
        if export is None:
            export = _price_over(export_prices, slot.start, slot.end)
        if export is None and price is not None:
            export = price * export_factor
        margin = 0.0
        if rules.estimated_margin > 0 and price is not None:
            share = _estimated_share(prices, begin, slot.end)
            if not share and _price_over(prices, begin, slot.end) is None:
                share = _estimated_share(prices, slot.start, slot.end)
            margin = rules.estimated_margin * share
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
                pack.night_floor if slot.start in night else 0.0,
                price_margin=margin,
            )
        )
    if not slots:
        return None
    # The night reserve should be there when the sun comes up: at the end of
    # the last night slot before a slot with sun.
    slots = [
        replace(s, reserve_due=True)
        if s.reserve_wh > 0
        and index + 1 < len(slots)
        and not slots[index + 1].reserve_wh
        else s
        for index, s in enumerate(slots)
    ]
    forced = dict(forced or {})
    forced_by = {k: dict(v) for k, v in (forced_by or {}).items()}
    # A full charge only for a battery that is in the plan now (one whose
    # state of charge is unknown is left out: its block is not given to
    # another battery).
    usable = {
        getattr(s.config, "id", None)
        for s in states
        if s.soc is not None and s.config.capacity_kwh > 0
    }
    for start, by in list(forced_by.items()):
        gone = sum(w for i, w in by.items() if i not in usable)
        if gone <= 0:
            continue
        forced_by[start] = {i: w for i, w in by.items() if i in usable}
        forced[start] = max(forced.get(start, 0.0) - gone, 0.0)
        if not forced_by[start]:
            forced_by.pop(start)
            forced.pop(start, None)
    if peak_w > 0:
        # A full charge stays under the peak limit (live, peak shaving would
        # cut it): the planners plan with what can really happen.
        for s in slots:
            want = forced.get(s.start, 0.0)
            room = max(peak_w - s.net_w, 0.0)
            if want > room:
                forced[s.start] = room
                if want > 0 and s.start in forced_by:
                    forced_by[s.start] = {
                        i: w * room / want for i, w in forced_by[s.start].items()
                    }
    if forced_by:
        # Each block at most its battery's power and phase room. (How full it
        # is when the block runs depends on the plan before it: once it is
        # full, finalise drops the rest of its block, per slot.)
        by_id = {getattr(s.config, "id", None): s for s in states}
        for s in slots:
            by = forced_by.get(s.start)
            if not by:
                continue
            limits = (member_limits or {}).get(s.start) or {}
            given: dict[str, float] = {}
            for i, w in by.items():
                st = by_id.get(i)
                if st is None or st.soc is None:
                    continue
                most = st.config.max_charge_w * getattr(st, "charge_factor", 1.0)
                if i in limits:
                    most = min(most, max(limits[i][0], 0.0))
                given[i] = max(min(w, most), 0.0)
            total = sum(given.values())
            if total > 0.5:
                forced_by[s.start] = given
                forced[s.start] = min(forced.get(s.start, 0.0), total)
            else:
                forced_by.pop(s.start)
                forced.pop(s.start, None)
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
            pack.peak_floor,
            pack.members,
            pack.held,
        ),
        rules,
        cycle_cost,
        max_cycles_per_day,
        peak_w,
        target,
        forced,
        forced_by,
        dict(member_limits or {}),
        dict(phase_rooms or {}),
        outlook,
        _previous_w(previous, slots[0].start),
    )


def _previous_w(previous: BatteryPlan | None, start: datetime) -> float | None:
    """The power the previous plan had for the slot holding ``start``."""
    if previous is None:
        return None
    return next((s.power_w for s in previous.slots if s.start <= start < s.end), None)


def finalise(
    data: PlannerInput, result: PlannerResult | list[float], mode: str
) -> BatteryPlan:
    """HomeBatteryAssist's final check of a planner's requested powers.

    Every power is cut back to the slot's charge/discharge limit (batteries
    and phases), to the room up to the maximum and the energy above the
    minimum state of charge and the reserves (night reserve; below the peak
    reserve only import above the peak limit), and to the price rules (no discharging below the
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
    # Several batteries: each apart, so a full one takes no more charge and an
    # empty one gives nothing (the pack's sum would allow both).
    member_wh = [m.stored_wh for m in battery.members]
    reasons = result.reasons or []
    thresholds = result.thresholds or []
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
        extra = data.forced.get(slot.start, 0.0)
        asked = extra  # the full charge the planner was given
        first = data.forced_by.get(slot.start)
        if extra > 0 and member_wh and first:
            # Only what the batteries charging fully can still take (up to
            # 100 %: a full charge goes above the maximum state of charge):
            # once full, their block does not spill over to the others.
            extra = min(
                extra,
                sum(
                    min(
                        first[m.id],
                        # What _share can give it (its phase room too).
                        _cap(m, data.member_limits.get(slot.start), 0),
                        max(m.capacity_wh - wh, 0.0) / (slot.hours * m.efficiency),
                    )
                    for m, wh in zip(battery.members, member_wh, strict=True)
                    if m.id in first
                ),
            )
        elif extra > 0 and not member_wh:
            extra = min(
                extra, max(battery.capacity_wh - stored, 0.0) / (slot.hours * eff)
            )
        if extra > 0 and data.peak_w > 0:
            # Not above the peak limit (live, peak shaving would cut it).
            extra = min(extra, max(data.peak_w - slot.net_w, 0.0))
        if (
            getattr(result, "forced_included", True)
            and asked - extra > 0.5
            and requested >= asked - 1.0
        ):
            # The planner charged at least the full charge it was given, but
            # its battery takes less now (full): not that part, it would go
            # to the other batteries (from the grid).
            requested = max(requested - (asked - extra), extra)
        if extra > 0:
            # A periodic full charge must happen: when the plan charges
            # anyway, the battery that charges fully is part of that power
            # (the larger of the two, not both). Price rules do not stop the
            # full charge itself, but still the rest of the request.
            requested = max(requested, extra)
        hours = slot.hours
        power = 0.0
        if requested > 0:
            power = min(
                requested,
                slot.max_charge_w,
                _charge_room(battery, member_wh, stored, hours, eff),
            )
            # A full charge up to 100 % (above the maximum state of charge).
            power = max(power, min(extra, slot.max_charge_w))
            if (
                not fixed
                and rules.max_charge_price is not None
                and slot.price is not None
                and slot.price > rules.max_charge_price
            ):
                # Only surplus PV (and a periodic full charge).
                power = min(power, max(extra, -slot.net_w, 0.0))
        elif requested < 0 and (fixed or may_discharge(rules, slot.price)):
            power = -min(
                -requested,
                slot.max_discharge_w,
                _discharge_room(data, slot, member_wh, stored),
            )
        power = max(power, 0.0) if requested > 0 else min(power, 0.0)
        if member_wh:
            power, member_wh = _share(
                battery.members,
                member_wh,
                power,
                hours,
                data.forced_by.get(slot.start),
                sequential=rules.charge_sequential,
                limits=data.member_limits.get(slot.start),
                phases=data.phase_rooms.get(slot.start),
                night=slot.reserve_wh > 0,
                peak=data.peak_w > 0,
                peak_excess=max(slot.net_w - data.peak_w, 0.0),
            )
            stored = sum(member_wh)
        else:
            stored += power * hours * eff if power >= 0 else power * hours / eff
        grid = slot.net_w + power
        use_above, charge_below = (
            thresholds[index] if index < len(thresholds) else (None, None)
        )
        # The price rules hold as well.
        lowest = getattr(rules, "min_discharge_price", None)
        if use_above is not None and lowest is not None:
            use_above = max(use_above, lowest)
        if charge_below is not None and rules.max_charge_price is not None:
            charge_below = min(charge_below, rules.max_charge_price)
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
                hours,
                slot.price_margin,
                None if use_above is None else round(use_above, 4),
                None if charge_below is None else round(charge_below, 4),
            )
        )
    strategy = result.strategy or mode
    if not data.priced:
        return BatteryPlan(mode, strategy, out, None, None)
    avg_price = sum(s.price for s in data.slots) / len(data.slots)
    # Count the change in stored energy at its value, so "with" and "without"
    # are comparable over the same window; valued as arbitrage values what is
    # left (``outlook_split``: what the next sun fills anyway at its export
    # price), so a plan that empties the battery for that sun is not shown
    # as costing more. Minus the wear of using it later (as the arbitrage
    # planner values it): with flat prices using it now or later is the
    # same, not a loss.
    rate = max(avg_price * eff - data.cycle_cost, 0.0)
    keep, overflow = outlook_split(
        data, max(battery.ceiling_wh - battery.floor_wh, 0.0), eff, rate
    )
    floor = battery.floor_wh
    cost_with += stored_value(
        battery.stored_wh - floor, keep, rate, overflow
    ) - stored_value(stored - floor, keep, rate, overflow)
    return BatteryPlan(
        mode,
        strategy,
        out,
        round(cost_with, 4),
        round(cost_without, 4),
        battery.capacity_wh / 1000,
        rate,
        round(battery.stored_wh / battery.capacity_wh * 100, 2)
        if battery.capacity_wh
        else None,
        floor_wh=floor,
        keep_wh=keep,
        overflow_per_kwh=overflow,
    )


def _charge_room(
    battery: Any, member_wh: list[float], stored: float, hours: float, eff: float
) -> float:
    """The most the batteries can still charge (W): per battery up to its own
    maximum (one battery above its maximum does not hide another's room)."""
    if not member_wh:
        return max(battery.ceiling_wh - stored, 0.0) / (hours * eff)
    return sum(
        max(m.ceiling_wh - wh, 0.0) / (hours * m.efficiency)
        for m, wh in zip(battery.members, member_wh, strict=True)
    )


def _discharge_room(
    data: PlannerInput, slot: Any, member_wh: list[float], stored: float
) -> float:
    """The most the batteries may discharge (W): per battery down to its own
    floor and reserves (``discharge_room`` for one battery)."""
    if not member_wh:
        return discharge_room(data, slot, stored)
    room = deep = 0.0
    night = slot.reserve_wh > 0
    limits = data.member_limits.get(slot.start)
    for m, wh in zip(data.battery.members, member_wh, strict=True):
        floor = max(m.floor_wh, m.night_floor_wh if night else 0.0)
        normal = max(floor, m.peak_floor_wh) if data.peak_w > 0 else floor
        # Each at most what it can give (its power, its phase room).
        cap = _cap(m, limits, 1)
        own = min(cap, max(wh - normal, 0.0) * m.efficiency / slot.hours)
        room += own
        if normal > floor:
            deep += min(
                cap - own,
                max(min(wh, normal) - floor, 0.0) * m.efficiency / slot.hours,
            )
    # Below the peak reserve: only for the import above the peak limit.
    return room + min(deep, max(slot.net_w - data.peak_w - room, 0.0))


def _cap(
    member: PackMember, limits: Mapping[str, tuple[float, float]] | None, which: int
) -> float:
    """A battery's charge (0) / discharge (1) power, within the room its
    phase leaves in this slot (the split must not overload a phase)."""
    own = member.max_charge_w if which == 0 else member.max_discharge_w
    if limits and member.id in limits:
        return min(own, max(limits[member.id][which], 0.0))
    return own


def _share(
    members: Sequence[PackMember],
    stored: list[float],
    power: float,
    hours: float,
    first: Mapping[str, float] | None = None,
    *,
    sequential: bool = False,
    limits: Mapping[str, tuple[float, float]] | None = None,
    phases: tuple[Mapping[str, int | None], Sequence[float], Sequence[float]]
    | None = None,
    night: bool = False,
    peak: bool = False,
    peak_excess: float = 0.0,
) -> tuple[float, list[float]]:
    """Split a pack power over the batteries, each at most what it can (power,
    and the room up to its maximum / the energy above its minimum), in
    proportion to that; the power they give together and their new energy.
    ``first`` (battery id -> W, charging): a periodic full charge goes to its
    own battery first, at its own power (not spread thin over all of them:
    a battery charges less efficiently at low power); the rest as above.
    ``sequential``: charging goes to the emptiest battery first, up to what it
    can take, then the next (not in proportion).
    Discharging: each battery keeps its own night reserve (``night``) and
    its own peak reserve (``peak``); below that only for the grid import
    above the peak limit (``peak_excess``, W), as for the pack."""
    if power > 0:
        caps = [
            min(
                _cap(m, limits, 0), max(m.ceiling_wh - wh, 0.0) / (hours * m.efficiency)
            )
            for m, wh in zip(members, stored, strict=True)
        ]
    elif power < 0:
        lows = [max(m.floor_wh, m.night_floor_wh if night else 0.0) for m in members]
        normal = [
            max(low, m.peak_floor_wh if peak else 0.0)
            for m, low in zip(members, lows, strict=True)
        ]
        caps = [
            min(_cap(m, limits, 1), max(wh - n, 0.0) * m.efficiency / hours)
            for m, wh, n in zip(members, stored, normal, strict=True)
        ]
        if peak and peak_excess > 0 and sum(caps) < -power:
            # Below the peak reserve, only for the import above the peak:
            # each battery down to its night reserve / floor, by what it has.
            deep = [
                min(_cap(m, limits, 1), max(wh - low, 0.0) * m.efficiency / hours) - cap
                for m, wh, low, cap in zip(members, stored, lows, caps, strict=True)
            ]
            deep = [max(d, 0.0) for d in deep]
            room_deep = sum(deep)
            if room_deep > 0:
                # The import above the peak the normal room leaves.
                use = min(
                    room_deep, max(peak_excess - sum(caps), 0.0), -power - sum(caps)
                )
                caps = [
                    c + d * use / room_deep for c, d in zip(caps, deep, strict=True)
                ]
    else:
        return 0.0, stored
    given = [0.0] * len(members)
    left = abs(power)
    if power > 0 and first:
        for k, m in enumerate(members):
            if m.id in first:
                # Its full charge up to 100 % (above its maximum SoC).
                full_cap = min(
                    _cap(m, limits, 0),
                    max(m.capacity_wh - stored[k], 0.0) / (hours * m.efficiency),
                )
                given[k] = min(first[m.id], full_cap, left)
                left -= given[k]
        caps = [max(c - g, 0.0) for c, g in zip(caps, given, strict=True)]
    room = sum(caps)
    if room <= 0 and not any(given):
        return 0.0, stored
    rest = min(left, room) if room > 0 else 0.0
    total = sum(given) + rest
    if power > 0 and sequential and rest > 0:
        # The emptiest first (by state of charge), each up to its cap.
        order = sorted(
            range(len(members)),
            key=lambda k: (
                stored[k] / members[k].capacity_wh if members[k].capacity_wh else 0.0
            ),
        )
        extra = [0.0] * len(members)
        todo = rest
        for k in order:
            extra[k] = min(caps[k], todo)
            todo -= extra[k]
        parts = [own + more for own, more in zip(given, extra, strict=True)]
    else:
        parts = [
            own + (rest * cap / room if room > 0 else 0.0)
            for cap, own in zip(caps, given, strict=True)
        ]
    if phases is not None:
        parts = _fit_phases(members, parts, phases, charging=power > 0)
    total = sum(parts)
    new = [
        wh + part * hours * m.efficiency
        if power > 0
        else wh - part * hours / m.efficiency
        for m, wh, part in zip(members, stored, parts, strict=True)
    ]
    return (total if power > 0 else -total), new


def _fit_phases(
    members: Sequence[PackMember],
    parts: list[float],
    phases: tuple[Mapping[str, int | None], Sequence[float], Sequence[float]],
    *,
    charging: bool,
) -> list[float]:
    """Scale the batteries of a phase down to the room it has (the batteries
    on one phase together, a battery over all phases on each of them)."""
    phase_of, room_c, room_d = phases
    room = room_c if charging else room_d
    count = len(room)
    if not count:
        return parts
    load = [0.0] * count
    for m, part in zip(members, parts, strict=True):
        phase = phase_of.get(m.id)
        if phase is None:
            for p in range(count):
                load[p] += part / count
        elif 0 <= phase < count:
            load[phase] += part
    factor = [
        min(max(room[p], 0.0) / load[p], 1.0) if load[p] > 0 else 1.0
        for p in range(count)
    ]
    out = []
    for m, part in zip(members, parts, strict=True):
        phase = phase_of.get(m.id)
        if phase is None:
            out.append(part * min(factor))
        elif 0 <= phase < count:
            out.append(part * factor[phase])
        else:
            out.append(part)
    return out


def cycles_per_day(plan: BatteryPlan) -> dict[date, float]:
    """Full cycles per local day: energy discharged / capacity."""
    days: dict[date, float] = {}
    if not plan.capacity_kwh:
        return days
    for slot in plan.slots:
        if slot.power_w < 0:
            hours = slot.duration_h
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
        hours = slot.duration_h
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
    # Paired by time (a plan reused from an earlier cycle may start a slot
    # earlier): only the slots both plans have.
    by_start = {
        s.start: (s, c)
        for s, c in zip(b.slots, slot_costs(b, export_factor, cycle_cost), strict=False)
    }
    for slot, cost_a in zip(
        a.slots, slot_costs(a, export_factor, cycle_cost), strict=False
    ):
        if slot.start not in by_start:
            continue
        slot_b, cost_b = by_start[slot.start]
        total += cost_b - cost_a
        stored = a.stored_value(slot.soc) - a.stored_value(slot_b.soc)
        series.append((slot.start, round(total + stored, 4)))
    return series
