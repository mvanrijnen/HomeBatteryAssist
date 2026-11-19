"""Time slots and the manual mode: fixed battery actions instead of optimising.

A time slot (subentry ``time_slot``) says what the batteries do on certain
days between two clock times (local time): charge or discharge at a power,
optionally until a state of charge is reached, or stay idle. A slot whose end
is before its start runs past midnight (the day is the day it starts).

- mode ``time_slots``: inside a slot its action, outside zero on the meter;
- mode ``manual``: always the configured power (+ charge / - discharge).

As everything else, this is a plan (advice); only virtual batteries carry it
out.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from homeassistant.util import dt as dt_util

ACTION_CHARGE = "charge"
ACTION_DISCHARGE = "discharge"
ACTION_IDLE = "idle"
ACTIONS = (ACTION_CHARGE, ACTION_DISCHARGE, ACTION_IDLE)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True, slots=True)
class Target:
    """What the batteries should do in a period."""

    power_w: float  # + charge / - discharge (0 = idle)
    soc_limit: float | None  # charge up to / discharge down to this % (None: limits)
    reason: str  # shown in the plan and its explanation


@dataclass(frozen=True, slots=True)
class TimeSlot:
    """A configured time slot."""

    name: str
    start: time
    end: time
    days: frozenset[int]  # 0 = Monday
    action: str
    power_w: float
    soc: float | None

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> TimeSlot:
        """Build from subentry data."""
        soc = data.get("soc")
        return cls(
            name=data["name"],
            start=_time(data["start"]),
            end=_time(data["end"]),
            days=frozenset(WEEKDAYS.index(d) for d in data.get("days") or WEEKDAYS),
            action=data["action"],
            power_w=float(data.get("power", 0) or 0),
            soc=float(soc) if soc not in (None, "") else None,
        )

    def active(self, when: datetime) -> bool:
        """True if the slot runs at ``when``."""
        local = dt_util.as_local(when)
        now = local.time()
        if self.start == self.end:  # e.g. 00:00-00:00: the whole day
            return local.weekday() in self.days
        if self.start < self.end:
            return local.weekday() in self.days and self.start <= now < self.end
        # Past midnight: the part after midnight belongs to the previous day.
        if now >= self.start:
            return local.weekday() in self.days
        return now < self.end and (local.weekday() - 1) % 7 in self.days

    def target(self) -> Target:
        """The action as a target."""
        power = {
            ACTION_CHARGE: abs(self.power_w),
            ACTION_DISCHARGE: -abs(self.power_w),
        }.get(self.action, 0.0)
        return Target(power, self.soc, self.name)


def _time(value: Any) -> time:
    if isinstance(value, time):
        return value
    parsed = dt_util.parse_time(str(value))
    if parsed is None:
        raise ValueError(f"invalid time: {value}")
    return parsed


def slot_target(slots: Iterable[TimeSlot], when: datetime) -> Target | None:
    """The target of the first slot active at ``when``, if any."""
    return next((s.target() for s in slots if s.active(when)), None)
