"""Built-in consumption forecaster: the recency-weighted history profile.

A recency-weighted (half-life 14 days) average per local weekday and hour.
With too little data it falls back step by step:

1. same weekday, same hour  ("weekday_hour")
2. all days, same hour  ("hour")
3. overall average  ("overall")

Every day of the week has its own profile (no working days / weekend split:
with working from home, a Wednesday can differ from a Tuesday).

To make your own variant: copy this file to
``/config/homebatteryassist/forecasters/``, give the class another ``key`` and
``name``, and change the relative imports (``from .base import``) into
``from custom_components.homebatteryassist.engine.forecast.forecasters.base import``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .base import Forecaster, ForecasterInput, ForecasterResult

HALF_LIFE = timedelta(days=14)
MIN_DAYS = 2  # distinct days needed before a profile level is trusted
METHODS = ("weekday_hour", "hour", "overall")


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


class ConsumptionProfile:
    """Recency-weighted averages of the history at several levels."""

    def __init__(self, records: Iterable[Mapping[str, Any]], now: datetime) -> None:
        """Build the profile from the history."""
        self._levels: dict[str, dict[object, _Acc]] = {m: {} for m in METHODS}
        self.days = 0.0
        for record in records:
            if record.get("vacation"):
                continue  # vacation: not the usual consumption
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
            for method, key in (
                ("weekday_hour", (local.weekday(), hour)),
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
        for method, key in (
            ("weekday_hour", (local.weekday(), local.hour)),
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


class ProfileForecaster(Forecaster):
    """The average per weekday and hour, recent days counting more."""

    key = "profile"
    name = "Weekday and hour profile"

    def forecast(self, data: ForecasterInput) -> ForecasterResult:
        profile = ConsumptionProfile(data.history, data.now)
        values: list[float | None] = []
        methods: list[str | None] = []
        for start, _end in data.slots:
            predicted = profile.predict(start)
            values.append(predicted[0] if predicted else None)
            methods.append(predicted[1] if predicted else None)
        return ForecasterResult(values, methods)
