"""The interface of a planner module.

A planner decides per slot how much the batteries should charge (+) or
discharge (-), in W. HomeBatteryAssist keeps the final say: it checks every
requested power against the batteries' power, the phase limits, the minimum
and maximum state of charge and the user's price rules, and cuts it back where
needed (``battery_plan.finalise``). Periodic full charges are inserted after
that. A planner therefore cannot plan anything the batteries or the grid
connection cannot do.

A planner only *advises*: HomeBatteryAssist never controls a battery.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class PlannerSlot:
    """One slot of the planning window (the history interval, e.g. 15 min)."""

    start: datetime
    end: datetime
    hours: float  # length of the slot
    house_w: float  # expected house consumption (average W)
    pv_w: float  # expected PV production (average W, after the safety margin)
    price: float | None  # what a kWh from the grid costs (all-in); None = unknown
    export_price: float | None  # what a kWh to the grid earns
    max_charge_w: float  # most the batteries may charge (power and phase limits)
    max_discharge_w: float  # most the batteries may discharge
    # Night reserve: the stored energy (Wh) not to discharge below in this
    # slot (0 = only the battery floor); ``reserve_due``: the sun comes up
    # after this slot, the reserve should be there at its end (charge from
    # the grid before, when needed and allowed).
    reserve_wh: float = 0.0
    reserve_due: bool = False

    @property
    def net_w(self) -> float:
        """Shortage (+) or surplus (-) of the house without batteries."""
        return self.house_w - self.pv_w


@dataclass(frozen=True, slots=True)
class PackMember:
    """One battery of the pack (for the final check: a full battery takes
    no more charge, an empty one gives nothing, whatever the others can)."""

    capacity_wh: float
    stored_wh: float
    floor_wh: float
    ceiling_wh: float
    efficiency: float  # one way
    max_charge_w: float
    max_discharge_w: float


@dataclass(frozen=True, slots=True)
class PlannerBattery:
    """All batteries together, as one."""

    capacity_wh: float
    stored_wh: float  # now
    floor_wh: float  # lowest allowed (minimum state of charge / reserve)
    ceiling_wh: float  # highest allowed (maximum state of charge)
    efficiency: float  # one way (charging or discharging), e.g. 0.92
    max_charge_w: float  # most the batteries can charge together
    max_discharge_w: float  # most the batteries can discharge together
    # Peak reserve: below this stored energy (Wh) only grid import above the
    # peak limit is discharged for (0 = off; only with a peak limit).
    peak_floor_wh: float = 0.0
    # The batteries apart (empty with one battery).
    members: tuple[PackMember, ...] = ()


@dataclass(frozen=True, slots=True)
class PlannerInput:
    """Everything a planner gets.

    ``rules`` are the user's plan rules (``battery_plan.PlanRules``: reserve,
    minimum discharge price, maximum charge price, ...); HomeBatteryAssist
    enforces the price rules afterwards anyway. ``target(start)`` gives the
    fixed action of manual / time slot settings for a slot, if any.
    ``forced`` = extra charge power (W) per slot start that must happen (the
    periodic full charges); ``finalise`` adds it to what the planner asks.
    """

    now: datetime
    slots: list[PlannerSlot]
    battery: PlannerBattery
    rules: Any
    cycle_cost: float = 0.0  # wear per kWh through the battery (price unit)
    max_cycles_per_day: float = 0.0  # 0 = no limit
    peak_w: float = 0.0  # grid import to stay below (all phases), 0 = off
    target: Callable[[datetime], Any] | None = None
    forced: Mapping[datetime, float] = field(default_factory=dict)
    priced: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "priced", all(s.price is not None for s in self.slots))


@dataclass(slots=True)
class PlannerResult:
    """What a planner returns: the requested power per slot (W, + charging),
    optionally a reason per slot (shown in the explanation) and the strategy
    it actually used (e.g. arbitrage falls back to nom without prices)."""

    powers: list[float]
    reasons: list[str | None] | None = None
    strategy: str | None = None


class Planner:
    """Base class of a planner module.

    Subclasses set ``key`` (unique, lowercase), ``name`` (shown to the user)
    and implement ``plan``. ``plan`` runs outside the event loop; it must not
    do I/O and should finish within a second.
    """

    key: str = ""
    name: str = ""
    description: str = ""
    # Tested on a real setup; until then every place where it is chosen
    # says "not tested". Own modules too: set True only after testing.
    verified: bool = False

    def plan(self, data: PlannerInput) -> PlannerResult | list[float]:
        """Requested battery power per slot of ``data.slots``, in W
        (+ charging / - discharging). Missing values count as 0 (idle)."""
        raise NotImplementedError


def may_discharge(rules: Any, price: float | None) -> bool:
    """Discharging is allowed at this price (the minimum discharge price)."""
    threshold = getattr(rules, "min_discharge_price", None)
    return threshold is None or price is None or price >= threshold


def discharge_room(data: PlannerInput, slot: PlannerSlot, stored: float) -> float:
    """The most a slot may discharge (W) with ``stored`` Wh in the batteries:
    down to the battery floor and the slot's night reserve; below the peak
    reserve only for the grid import above the peak limit."""
    battery = data.battery
    eff = battery.efficiency
    floor = max(battery.floor_wh, slot.reserve_wh)
    normal = max(floor, battery.peak_floor_wh) if data.peak_w > 0 else floor
    room = max(stored - normal, 0.0) * eff / slot.hours
    if normal > floor:
        deep = max(min(stored, normal) - floor, 0.0) * eff / slot.hours
        room += min(deep, max(slot.net_w - data.peak_w - room, 0.0))
    return room


def grid_cost(grid_w: float, hours: float, price: float, export_price: float) -> float:
    """Cost of a grid exchange (+ import at the price, - export at the export price)."""
    kwh = grid_w * hours / 1000
    return kwh * price if kwh >= 0 else kwh * export_price
