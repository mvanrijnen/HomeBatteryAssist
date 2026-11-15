"""Limits of the grid connection per phase (main fuse), for batteries.

A battery on a phase adds its charging power to the import on that phase, and
its discharging power to the export. The current on a phase may not exceed the
connection's maximum current (e.g. 3x25A), minus a safety margin:

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

from ..const import NOMINAL_VOLTAGE, phase_index
from ..inputs.batteries import BatteryConfig

PHASE_MARGIN = 0.9  # use at most 90 % of the fuse rating


def phase_limit_w(max_current: float) -> float:
    """Maximum power per phase, including the safety margin."""
    return max_current * NOMINAL_VOLTAGE * PHASE_MARGIN


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
