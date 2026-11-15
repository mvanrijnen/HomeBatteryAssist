"""Distributing a requested battery power over several batteries.

Converters lose relatively more at low power, so a request is spread over as
few batteries as possible, but over as many as needed:

- each battery that is used runs at least at ``min_power_w`` (if possible);
- enough batteries are used to deliver the requested power;
- discharging uses the fullest batteries first, charging the emptiest, which
  keeps the batteries balanced;
- the power is shared equally; what a battery cannot take (power limit) goes
  to the others.

Used for virtual batteries now, and for real batteries once HomeBatteryAssist
controls them.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_MIN_BATTERY_POWER = 300  # W


@dataclass(frozen=True, slots=True)
class Candidate:
    """A battery that may take part: its id, state of charge and limits."""

    id: str
    soc: float
    min_soc: float
    max_soc: float
    max_charge_w: float
    max_discharge_w: float


def distribute(
    target_w: float, batteries: Sequence[Candidate], min_power_w: float
) -> dict[str, float]:
    """Split ``target_w`` (+ charging / - discharging) over the batteries."""
    result = {b.id: 0.0 for b in batteries}
    if not target_w or not batteries:
        return result
    charging = target_w > 0
    if charging:
        usable = sorted(
            (b for b in batteries if b.soc < b.max_soc), key=lambda b: b.soc
        )
    else:
        usable = sorted(
            (b for b in batteries if b.soc > b.min_soc), key=lambda b: -b.soc
        )
    if not usable:
        return result

    def cap(b: Candidate) -> float:
        return b.max_charge_w if charging else b.max_discharge_w

    demand = abs(target_w)
    # Enough batteries for the power ...
    needed, total = 0, 0.0
    for b in usable:
        if total >= demand:
            break
        needed += 1
        total += cap(b)
    # ... but no more than keeps each one at or above the minimum power.
    by_minimum = (
        max(1, math.floor(demand / min_power_w)) if min_power_w > 0 else len(usable)
    )
    count = max(needed, min(by_minimum, len(usable)))
    chosen = usable[:count]

    # Equal shares; pass on what a battery cannot take.
    remaining = demand
    open_ = list(chosen)
    while open_ and remaining > 1e-9:
        share = remaining / len(open_)
        still_open = []
        for b in open_:
            take = min(share, cap(b) - abs(result[b.id]))
            result[b.id] += take if charging else -take
            remaining -= take
            if cap(b) - abs(result[b.id]) > 1e-9:
                still_open.append(b)
        if len(still_open) == len(open_):
            break  # everyone took the full share
        open_ = still_open
    return {k: round(v, 1) + 0.0 for k, v in result.items()}
