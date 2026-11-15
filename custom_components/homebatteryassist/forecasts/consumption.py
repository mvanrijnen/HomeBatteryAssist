"""House consumption forecast per slot of the planning window.

Based on the consumption history (excluded devices such as an EV charger are
not part of it): a recency-weighted average per local weekday and hour. With
too little data it falls back step by step:

1. same weekday, same hour  ("weekday_hour")
2. weekdays or weekend, same hour  ("daytype_hour")
3. all days, same hour  ("hour")
4. overall average  ("overall")

Per slot: profile (``base_w``) -> learned or manual correction (``accuracy``)
-> user adjustments (``adjustments``, applied last because they are intent).
``raw_w`` (profile + adjustments, without correction) is what accuracy learns
from. Like every forward calculation, it only calculates within the planning
window.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from ..history.consumption import ConsumptionRecord
from .adjustments import Adjustment, apply_adjustments
from .horizon import PlanningWindow

HALF_LIFE = timedelta(days=14)
MIN_DAYS = 2  # distinct days needed before a profile level is trusted
WEEKEND = (5, 6)
METHODS = ("weekday_hour", "daytype_hour", "hour", "overall")


@dataclass(slots=True)
class _Acc:
    total: float = 0.0
    weight: float = 0.0
    days: set = field(default_factory=set)

    def add(self, value: float, weight: float, day: object) -> None:
        self.total += value * weight
        self.weight += weight
        self.days.add(day)

    @property
    def mean(self) -> float | None:
        return self.total / self.weight if self.weight else None


@dataclass(frozen=True, slots=True)
class ForecastSlot:
    """Expected house consumption in one slot."""

    start: datetime
    end: datetime
    power_w: float  # final: corrected profile + adjustments
    base_w: float  # from the history profile
    method: str
    adjustments: tuple[str, ...] = ()  # names of applied adjustments
    raw_w: float | None = None  # profile + adjustments, without correction

    @property
    def raw(self) -> float:
        """The uncorrected prediction (learning input)."""
        return self.raw_w if self.raw_w is not None else self.power_w


class ConsumptionProfile:
    """Recency-weighted averages of the history at several levels."""

    def __init__(self, records: Iterable[ConsumptionRecord], now: datetime) -> None:
        """Build the profile from the history."""
        self._levels: dict[str, dict[object, _Acc]] = {m: {} for m in METHODS}
        self.days = 0.0
        for record in records:
            start = dt_util.parse_datetime(record["start"])
            if start is None:
                continue
            weight = record["minutes"] * record["coverage"]
            if weight <= 0:
                continue
            self.days += weight / 1440
            age = max((now - start).total_seconds(), 0.0)
            weight *= math.pow(0.5, age / HALF_LIFE.total_seconds())
            local = dt_util.as_local(start)
            day, hour = local.date(), local.hour
            daytype = "weekend" if local.weekday() in WEEKEND else "weekday"
            for method, key in (
                ("weekday_hour", (local.weekday(), hour)),
                ("daytype_hour", (daytype, hour)),
                ("hour", hour),
                ("overall", None),
            ):
                self._levels[method].setdefault(key, _Acc()).add(
                    record["avg_w"], weight, day
                )

    @property
    def empty(self) -> bool:
        """True without any history."""
        return not self._levels["overall"]

    def predict(self, when: datetime) -> tuple[float, str] | None:
        """Expected power (W) at ``when`` and the method used, or None."""
        local = dt_util.as_local(when)
        daytype = "weekend" if local.weekday() in WEEKEND else "weekday"
        for method, key in (
            ("weekday_hour", (local.weekday(), local.hour)),
            ("daytype_hour", (daytype, local.hour)),
            ("hour", local.hour),
            ("overall", None),
        ):
            acc = self._levels[method].get(key)
            if (
                acc
                and acc.mean is not None
                and (method == "overall" or len(acc.days) >= MIN_DAYS)
            ):
                return round(acc.mean, 1), method
        return None


def forecast_consumption(
    records: Iterable[ConsumptionRecord],
    window: PlanningWindow,
    step: timedelta,
    adjustments: Iterable[Adjustment] = (),
    now: datetime | None = None,
    correct: Callable[[float, datetime], float] | None = None,
) -> list[ForecastSlot]:
    """Expected consumption per slot of ``window`` (empty without history).

    ``correct(value, slot_start)`` applies the accuracy correction.
    """
    if window.is_empty:
        return []
    profile = ConsumptionProfile(records, now or window.start)
    if profile.empty:
        return []
    adjustments = list(adjustments)
    slots: list[ForecastSlot] = []
    for start, end in window.slots(step):
        predicted = profile.predict(start)
        if predicted is None:
            continue
        base, method = predicted
        raw, applied = apply_adjustments(base, start, end, adjustments)
        corrected = round(correct(base, start), 1) if correct else base
        power, _ = apply_adjustments(corrected, start, end, adjustments)
        slots.append(ForecastSlot(start, end, power, base, method, applied, raw))
    return slots
