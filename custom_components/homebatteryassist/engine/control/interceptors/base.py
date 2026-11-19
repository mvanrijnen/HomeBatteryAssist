"""The interface of an interceptor (a module kind).

An interceptor is the last say of the user before commands go to the
batteries: every control step (every second) it gets HomeBatteryAssist's
proposal per battery, with everything needed to judge it, and decides per
battery: approve, limit (less power in the same direction), reject (0 W,
HomeBatteryAssist keeps control) or release (back to the battery's own
control). It intercepts: it can never ask more than proposed nor turn
charging into discharging (HomeBatteryAssist cuts that back).

HomeBatteryAssist's own final check always comes after it and overrules it:
power and phase limits, state of charge, watchdog and releasing. A final
interceptor can hold back or limit, never push anything unsafe through. It must be
quick (no I/O) and only decide; it never talks to a device itself.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

APPROVE = "approve"
LIMIT = "limit"
REJECT = "reject"
RELEASE = "release"
Action = Literal["approve", "limit", "reject", "release"]


@dataclass(frozen=True, slots=True)
class BatteryProposal:
    """One battery and what HomeBatteryAssist proposes for it now."""

    id: str
    name: str
    phase: str  # "l1".."l3", or "none" (all phases / unknown)
    soc: float | None  # %
    power_w: float | None  # now, + charging / - discharging
    temperature_c: float | None
    capacity_kwh: float
    max_charge_w: float
    max_discharge_w: float
    min_soc: float
    max_soc: float
    virtual: bool
    full_charge: bool  # a forced full charge is running
    proposed_w: float  # + charge / - discharge
    reason: (
        str  # "plan", "zero_on_meter", "full_charge", "phase_relief", "peak_shaving"
    )
    # Lowest state of charge for discharging now: ``min_soc`` raised by the
    # reserves in force (reserve, night reserve; the peak reserve except for
    # peak shaving). None = ``min_soc``.
    floor_soc: float | None = None


@dataclass(frozen=True, slots=True)
class PriceSlot:
    """A coming slot of the plan: prices and what the plan does."""

    start: datetime
    end: datetime
    price: float | None  # what a kWh costs (after the tariff)
    export_price: float | None  # what an exported kWh earns
    planned_w: float  # the plan for all batteries, + charge / - discharge


@dataclass(frozen=True, slots=True)
class InterceptInput:
    """Everything an interceptor gets every control step."""

    now: datetime
    mode: str  # chosen plan mode (nom, arbitrage, ...)
    batteries: Sequence[BatteryProposal]
    grid_w: float | None  # net, + import / - export
    phase_w: Sequence[float]  # net per phase, + import / - export
    phase_limit_w: float  # per phase (main fuse with margin)
    house_w: float | None
    pv_w: float | None
    excluded_w: float | None
    spike_w: float  # part of the consumption that is a random short peak
    slots: Sequence[PriceSlot]  # now and the coming hours of the plan


@dataclass(frozen=True, slots=True)
class Decision:
    """The decision for one battery (only for the ones you change)."""

    battery_id: str
    action: Action = APPROVE
    power_w: float | None = None  # with LIMIT: at most this (same direction)
    reason: str = ""  # shown in Why when something changes


@dataclass(frozen=True, slots=True)
class InterceptResult:
    """The decisions; batteries without a decision are approved.

    ``redistribute``: what a rejected or limited battery does not do may be
    taken over by the approved ones, up to their own proposal's limits
    (HomeBatteryAssist's choice, within the batteries' limits).
    """

    decisions: Sequence[Decision] = field(default_factory=tuple)
    redistribute: bool = True


class Interceptor:
    """Base class of an interceptor."""

    key: str = ""
    name: str = ""
    # Tested on a real setup; until then every place where it is chosen
    # says "not tested". Own modules too: set True only after testing.
    verified: bool = False

    def intercept(self, data: InterceptInput) -> InterceptResult:
        """Decide per battery; quick, no I/O."""
        raise NotImplementedError
