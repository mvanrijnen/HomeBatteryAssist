"""Distributing a requested battery power over several batteries.

Converters lose relatively more at low power, so a request is spread over as
few batteries as possible, but over as many as needed:

- each battery that is used runs at least at ``min_power_w`` (if possible);
- enough batteries are used to deliver the requested power;
- discharging uses the fullest batteries first, charging the emptiest, which
  keeps the batteries balanced; ``Distributor`` keeps the batteries it uses
  (no flapping) and only re-checks the balance every interval;
- the power is shared equally; what a battery cannot take (power limit) goes
  to the others.

Used for virtual batteries now, and for real batteries once HomeBatteryAssist
controls them.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

DEFAULT_MIN_BATTERY_POWER = 300  # W
BALANCE_TOLERANCE = 2.0  # % state of charge before switching batteries


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
    target_w: float,
    batteries: Sequence[Candidate],
    min_power_w: float,
    keep: Sequence[str] = (),
    sequential: bool = False,
) -> dict[str, float]:
    """Split ``target_w`` (+ charging / - discharging) over the batteries.

    ``keep``: ids of batteries to use first (if they can), e.g. the ones in use.
    ``sequential`` (charging): one after the other, the emptiest first, each
    at its full power before the next takes the rest.
    """
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
    kept = [b for i in keep for b in usable if b.id == i]
    usable = kept + [b for b in usable if b not in kept]

    def cap(b: Candidate) -> float:
        return b.max_charge_w if charging else b.max_discharge_w

    demand = abs(target_w)
    if charging and sequential:
        for b in usable:
            take = min(cap(b), demand)
            result[b.id] = take
            demand -= take
            if demand <= 1e-9:
                break
        return {k: round(v, 1) + 0.0 for k, v in result.items()}
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


class Distributor:
    """Keeps using the same batteries; re-checks the balance every interval.

    Switching happens only when needed (a battery is full/empty, more or fewer
    batteries are needed, the direction changes), or at a balance check when
    another battery is more than ``BALANCE_TOLERANCE`` fuller (discharging) or
    emptier (charging) than one in use.
    """

    def __init__(self, interval: timedelta) -> None:
        """Initialize."""
        self.interval = interval
        self.active: list[str] = []
        self._charging: bool | None = None
        self._checked: datetime | None = None

    def distribute(
        self,
        target_w: float,
        batteries: Sequence[Candidate],
        min_power_w: float,
        now: datetime,
        sequential: bool = False,
    ) -> tuple[dict[str, float], tuple[str, str] | None]:
        """Split the power; also return (new id, replaced id) on a balance switch."""
        if not target_w:
            self.active = []
            return {b.id: 0.0 for b in batteries}, None
        charging = target_w > 0
        if charging != self._charging:
            self.active, self._charging, self._checked = [], charging, now
        keep = list(self.active)
        switch = None
        if keep and self._checked is not None and now - self._checked >= self.interval:
            self._checked = now
            switch = self._balance_switch(keep, batteries, charging)
            if switch:
                new, old = switch
                keep = [new] + [i for i in keep if i != old]
        result = distribute(target_w, batteries, min_power_w, keep, sequential)
        self.active = [i for i in keep if result.get(i)] + [
            i for i, v in result.items() if v and i not in keep
        ]
        if self._checked is None:
            self._checked = now
        return result, switch

    @staticmethod
    def _balance_switch(
        keep: list[str], batteries: Sequence[Candidate], charging: bool
    ) -> tuple[str, str] | None:
        by_id = {b.id: b for b in batteries}
        in_use = [by_id[i] for i in keep if i in by_id]
        others = [
            b
            for b in batteries
            if b.id not in keep
            and (b.soc < b.max_soc if charging else b.soc > b.min_soc)
        ]
        if not in_use or not others:
            return None
        if charging:
            best = min(others, key=lambda b: b.soc)
            worst = max(in_use, key=lambda b: b.soc)
            better = best.soc < worst.soc - BALANCE_TOLERANCE
        else:
            best = max(others, key=lambda b: b.soc)
            worst = min(in_use, key=lambda b: b.soc)
            better = best.soc > worst.soc + BALANCE_TOLERANCE
        return (best.id, worst.id) if better else None


def one_direction(
    powers: Mapping[str, float], *priority: Iterable[str]
) -> dict[str, float]:
    """Never one battery charging while another discharges (power + charging).

    That only moves energy from one battery into the other, with the losses
    of both. ``priority``: groups of battery ids whose power stands, most
    important first (protection of a phase or the peak, then a full charge):
    the first group with power sets the direction and every battery against
    it stops. Without such a group the net stands: the direction of the sum
    stays, the batteries against it stop, and those with it together give
    the sum (the grid sees the same).
    """
    out = {k: float(v) for k, v in powers.items()}
    if not any(p > 0 for p in out.values()) or not any(p < 0 for p in out.values()):
        return out
    for group in priority:
        members = [i for i in group if out.get(i, 0.0)]
        if not members:
            continue
        # Both ways inside the group (e.g. one phase importing too much,
        # another exporting too much): the larger need sets the direction.
        sign = math.copysign(1.0, sum(out[i] for i in members) or out[members[0]])
        return {k: (0.0 if p * sign < 0 else p) for k, p in out.items()}
    total = sum(out.values())
    same = sum(p for p in out.values() if p * total > 0)
    factor = total / same if same else 0.0
    return {k: (p * factor if p * total > 0 else 0.0) for k, p in out.items()}
