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

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from ...const import DEFAULT_PHASE_MARGIN, NOMINAL_VOLTAGE, phase_index
from ..inputs.batteries import BatteryConfig


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


def _room(load_w: Sequence[float], limit_w: float, charging: bool) -> list[float]:
    return [max(limit_w - load if charging else limit_w + load, 0.0) for load in load_w]


def max_power(
    devices: Iterable[PhaseDevice],
    load_w: Sequence[float],
    limit_w: float,
    charging: bool,
) -> float:
    """Most power the devices can charge (or discharge) together without overload."""
    devices = list(devices)
    room = _room(load_w, limit_w, charging)
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
    load_w: Sequence[float],
    limit_w: float,
) -> tuple[dict[str, float], list[int]]:
    """Scale battery powers (+ charging) down where a phase would be overloaded.

    Returns the new powers and the indexes of the phases that limited them.
    """
    result = dict(powers)
    limited: set[int] = set()
    devices = [d for d in devices if d.id in result]
    for charging in (True, False):
        room = _room(load_w, limit_w, charging)
        active = [d for d in devices if (result[d.id] > 0) == charging and result[d.id]]
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
            lowest = min(room)
            limited.update(i for i, r in enumerate(room) if r == lowest)
    return {k: round(v, 1) + 0.0 for k, v in result.items()}, sorted(limited)


def overloaded(load_w: Sequence[float], limit_w: float) -> list[int]:
    """Indexes of the phases whose (import or export) power exceeds the limit."""
    return [i for i, load in enumerate(load_w) if abs(load) > limit_w]


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
    charging = {k: v for k, v in result.items() if v > 0}
    total_charge = sum(charging.values())
    if total_charge > 0:
        cut = min(total_charge, need)
        for key, value in charging.items():
            result[key] = value - cut * value / total_charge
        need -= cut
    allowed = set(can_discharge)
    open_ = [d for d in devices if d.id in result and d.id in allowed]
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
