"""Limits of the grid connection per phase (main fuse), for batteries.

A battery on a phase adds its charging power to the import on that phase, and
its discharging power to the export. The current on a phase may not exceed the
connection's maximum current (e.g. 3x25A), minus a safety margin (option
``phase_margin``, % of the fuse rating, the same for all phases):

    load_p + charge_p    <= limit
    discharge_p - load_p <= limit

with ``load_p`` the expected (plan) or measured (simulation) grid power on the
phase without these batteries, + import / - export. A battery without a phase
(a three-phase converter) is spread evenly over all phases; on a 1-phase
connection every battery is on that phase.

Used by the battery plan (per slot) and by the simulation of virtual batteries
(live, on the measured phase power). Later also for controlling real batteries.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from ...const import DEFAULT_PHASE_MARGIN, NOMINAL_VOLTAGE, phase_index
from ..measure.battery_monitor import BatteryConfig


def phase_limit_w(max_current: float, margin: float = DEFAULT_PHASE_MARGIN) -> float:
    """Maximum power per phase, keeping ``margin`` % of the fuse rating free."""
    return max_current * NOMINAL_VOLTAGE * (1 - margin / 100)


@dataclass(frozen=True, slots=True)
class PhaseDevice:
    """A battery as far as the phase limits are concerned."""

    id: str
    phase: int | None  # None = spread over all phases
    max_charge_w: float
    max_discharge_w: float

    @classmethod
    def from_config(cls, config: BatteryConfig, phases: int) -> PhaseDevice:
        """Build from a battery's configuration."""
        return cls(
            config.id,
            phase_index(config.phase, phases),
            config.max_charge_w,
            config.max_discharge_w,
        )


# Meters that round the current to whole amps are up to half an amp off.
ROUNDING_W = 0.5 * NOMINAL_VOLTAGE


@dataclass(frozen=True, slots=True)
class PhaseLoad:
    """What is known of a phase's load without the batteries, in current
    terms (current x 230 V): the most the current can be (``current_w``,
    >= 0) and the range the active power is in (``active_lo_w`` ..
    ``active_hi_w``, signed, + import). Exact when known exactly; a range
    when a measurement leaves room (a current rounded to whole amps, active
    power without a measured voltage). The final check works from the worst
    case in that range."""

    current_w: float
    active_lo_w: float
    active_hi_w: float


def _bounds(
    load_w: Sequence[float | PhaseLoad], active_w: Sequence[float] | None
) -> list[PhaseLoad]:
    """Every phase as a ``PhaseLoad``: one given as it is; a plain load
    (current as power, signed) with ``active_w`` (the active power in the
    same terms) or, without it, all active."""
    out = []
    for i, load in enumerate(load_w):
        if isinstance(load, PhaseLoad):
            out.append(load)
            continue
        p = active_w[i] if active_w is not None and i < len(active_w) else load
        out.append(PhaseLoad(max(abs(load), abs(p)), p, p))
    return out


def _room(
    load_w: Sequence[float | PhaseLoad],
    limit_w: float,
    charging: bool,
    active_w: Sequence[float] | None = None,
) -> list[float]:
    """Room per phase for charging (more import) or discharging: the most
    active power the batteries may add (or take off) so the current stays
    within the limit, in the worst case of what is known (``PhaseLoad``).

    A battery only changes the active power P; the reactive part Q stays.
    With current I (as power), Q^2 = I^2 - P^2 and after adding x the
    current is sqrt(I^2 + 2Px + x^2): at most the limit L while
    x <= sqrt(L^2 - I^2 + P^2) - P (charging; the highest P and I are the
    worst) or -x <= sqrt(L^2 - I^2 + P^2) + P (discharging; the lowest P)."""
    rooms = []
    for phase in _bounds(load_w, active_w):
        p = phase.active_hi_w if charging else phase.active_lo_w
        current = max(phase.current_w, abs(phase.active_lo_w), abs(phase.active_hi_w))
        root = math.sqrt(max(limit_w * limit_w - current * current + p * p, 0.0))
        room = root - p if charging else root + p
        # Never NaN (a NaN room would let everything through).
        rooms.append(max(room, 0.0) if math.isfinite(room) else 0.0)
    return rooms


def max_power(
    devices: Iterable[PhaseDevice],
    load_w: Sequence[float | PhaseLoad],
    limit_w: float,
    charging: bool,
    active_w: Sequence[float] | None = None,
) -> float:
    """Most power the devices can charge (or discharge) together without
    overload (``active_w``: see ``_room``)."""
    devices = list(devices)
    room = _room(load_w, limit_w, charging, active_w)
    total = 0.0

    def cap(d: PhaseDevice) -> float:
        return d.max_charge_w if charging else d.max_discharge_w

    for index in range(len(room)):
        take = min(sum(cap(d) for d in devices if d.phase == index), room[index])
        room[index] -= take
        total += take
    if spread := sum(cap(d) for d in devices if d.phase is None):
        total += min(spread, len(room) * min(room, default=0.0))
    return total


def cap_powers(
    powers: Mapping[str, float],
    devices: Iterable[PhaseDevice],
    load_w: Sequence[float | PhaseLoad],
    limit_w: float,
    active_w: Sequence[float] | None = None,
) -> tuple[dict[str, float], list[int]]:
    """Scale battery powers (+ charging) down where a phase would be overloaded
    (``load_w`` / ``active_w``: see ``_room``). The final check: it only
    lowers powers, never raises or turns them. Charging and discharging are
    checked apart, each as if the other did not help (the current is
    convex in the added power, so every mix in between is within too).
    A battery on a phase this connection does not have counts in full on
    the fullest phase (never as spread: that would count a third of it).
    A power that is not a number stops.

    Returns the new powers and the indexes of the phases that limited them.
    """
    result = {k: (float(v) if math.isfinite(v) else 0.0) for k, v in powers.items()}
    limited: set[int] = set()
    count = len(load_w)
    devices = [d for d in devices if d.id in result]
    for charging in (True, False):
        room = _room(load_w, limit_w, charging, active_w)
        if not room:
            # No phase known: nothing can be checked, so nothing runs.
            return dict.fromkeys(result, 0.0), []
        fullest = room.index(min(room))
        active = [
            d if d.phase is None or 0 <= d.phase < count else replace(d, phase=fullest)
            for d in devices
            if (result[d.id] > 0) == charging and result[d.id]
        ]
        for index in range(len(room)):
            on_phase = [d for d in active if d.phase == index]
            total = sum(abs(result[d.id]) for d in on_phase)
            if total > room[index] + 0.5:
                for d in on_phase:
                    result[d.id] *= room[index] / total
                limited.add(index)
            room[index] -= min(total, room[index])
        spread = [d for d in active if d.phase is None]
        total = sum(abs(result[d.id]) for d in spread)
        allowed = len(room) * min(room, default=0.0)
        if total > allowed + 0.5:
            for d in spread:
                result[d.id] *= allowed / total
            lowest = min(room, default=0.0)
            limited.update(i for i, r in enumerate(room) if r == lowest)
    return {k: round(v, 1) + 0.0 for k, v in result.items()}, sorted(limited)


def overloaded(load_w: Sequence[float], limit_w: float) -> list[int]:
    """Indexes of the phases whose (import or export) power exceeds the limit."""
    return [i for i, load in enumerate(load_w) if abs(load) > limit_w]


def active_relief_loads(
    load_w: Sequence[float], active_w: Sequence[float], limit_w: float
) -> list[float]:
    """The phase loads for ``relieve`` so that it takes off enough *active*
    power. ``load_w`` is the current as power (current x 230 V, signed),
    ``active_w`` the active power in the same terms. A battery only changes
    the active power; with a reactive part Q the current falls less than the
    power: to bring hypot(P, Q) down to the limit, P must go to
    sqrt(limit^2 - Q^2). An overloaded phase gets the load for which
    ``load - limit`` is that active power (all of it when Q alone exceeds the
    limit); other phases are unchanged."""
    result = list(load_w)
    for i, load in enumerate(load_w):
        if abs(load) <= limit_w or i >= len(active_w):
            continue
        p = abs(active_w[i])
        if abs(load) - p < ROUNDING_W:
            continue  # within the rounding of a meter's current: no reactive part
        q2 = max(load * load - p * p, 0.0)
        target = math.sqrt(max(limit_w * limit_w - q2, 0.0))
        need = max(p - target, abs(load) - limit_w)
        result[i] = math.copysign(limit_w + need, load)
    return result


def relieve(
    powers: Mapping[str, float],
    devices: Iterable[PhaseDevice],
    load_w: Sequence[float],
    limit_w: float,
    can_discharge: Iterable[str],
    can_charge: Iterable[str],
) -> tuple[dict[str, float], dict[int, float]]:
    """Let batteries take load off an overloaded phase (peak shaving per phase).

    ``load_w`` is the grid power per phase without these batteries. On a phase
    that imports more than the limit, its batteries discharge (and stop
    charging) to bring it back to the limit; on a phase that exports more
    (e.g. much solar power), they charge. Batteries on the phase go first,
    batteries spread over all phases count for a share. This overrides what the
    plan wanted for those batteries.

    Returns the new powers and, per relieved phase, the power taken off it.
    """
    result = dict(powers)
    devices = [d for d in devices if d.id in result]
    discharge_ok, charge_ok = set(can_discharge), set(can_charge)
    count = len(load_w)
    relieved: dict[int, float] = {}
    for index in overloaded(load_w, limit_w):
        discharging = load_w[index] > 0
        need = abs(load_w[index]) - limit_w
        allowed = discharge_ok if discharging else charge_ok
        sign = -1.0 if discharging else 1.0
        taken = 0.0
        groups = (
            ([d for d in devices if d.phase == index and d.id in allowed], 1),
            ([d for d in devices if d.phase is None and d.id in allowed], count),
        )
        for group, factor in groups:
            for d in group:
                # Power in the wrong direction stops; power in the right one counts.
                result[d.id] = max(result[d.id] * sign, 0.0) * sign
                taken += abs(result[d.id]) / factor
            open_ = list(group)
            while open_ and need - taken > 0.5:
                share = (need - taken) * factor / len(open_)
                still_open = []
                for d in open_:
                    cap = d.max_discharge_w if discharging else d.max_charge_w
                    take = min(share, cap - abs(result[d.id]))
                    if take <= 0:
                        continue
                    result[d.id] += sign * take
                    taken += take / factor
                    if cap - abs(result[d.id]) > 0.5:
                        still_open.append(d)
                if len(still_open) == len(open_):
                    break  # everyone took the full share
                open_ = still_open
        if taken > 0.5:
            relieved[index] = round(min(taken, need), 1)
    return {k: round(v, 1) + 0.0 for k, v in result.items()}, relieved


def shave_peak(
    powers: Mapping[str, float],
    devices: Iterable[PhaseDevice],
    grid_w: float,
    peak_w: float,
    can_discharge: Iterable[str],
    keep: Iterable[str] = (),
) -> tuple[dict[str, float], float]:
    """Keep the total grid import (all phases) at or below ``peak_w``.

    ``grid_w`` is the measured grid power without these batteries. Charging is
    reduced first; then batteries that can discharge take over the rest.
    Returns the new powers and how much power was shaved off.
    """
    result = dict(powers)
    if peak_w <= 0:
        return result, 0.0
    excess = grid_w + sum(result.values()) - peak_w
    if excess <= 0.5:
        return result, 0.0
    need = excess
    # A battery charging to relieve an exporting phase keeps that charge.
    kept = set(keep)
    charging = {k: v for k, v in result.items() if v > 0 and k not in kept}
    total_charge = sum(charging.values())
    if total_charge > 0:
        cut = min(total_charge, need)
        for key, value in charging.items():
            result[key] = value - cut * value / total_charge
        need -= cut
    allowed = set(can_discharge)
    # A battery relieving an exporting phase is never turned to discharging.
    open_ = [
        d for d in devices if d.id in result and d.id in allowed and d.id not in kept
    ]
    while open_ and need > 0.5:
        share = need / len(open_)
        still_open = []
        for d in open_:
            take = min(share, d.max_discharge_w + min(result[d.id], 0.0))
            if take <= 0:
                continue
            result[d.id] -= take
            need -= take
            if d.max_discharge_w + result[d.id] > 0.5:
                still_open.append(d)
        if len(still_open) == len(open_):
            break
        open_ = still_open
    return {k: round(v, 1) + 0.0 for k, v in result.items()}, round(excess - need, 1)
