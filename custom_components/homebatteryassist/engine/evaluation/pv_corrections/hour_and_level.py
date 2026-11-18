"""Built-in PV correction: per lead time, hour of the day and level.

On top of the factor per lead time (``lead_time.py``) it learns two typical
deviations of PV forecasts:

- **per hour of the day** (local): shade in the morning, a roof facing west,
  a forecast that is early or late — one factor per lead time averages that
  away;
- **per level**: how much the forecast promises at that hour compared with
  the most it promised at that hour lately (about a clear sky). Forecasts are
  often relatively further off on dull days than on sunny ones; three bands
  (``LEVELS``) each get a factor.

Both are energy ratios (measured / forecast after the lead time factor) over
the last weeks, recent days counting more (``HALF_LIFE``), pulled towards 1
while there are few days (``HOUR_DAYS`` / ``LEVEL_DAYS`` for half strength).
The combined factor stays within ``FACTOR_RANGE``. Without history it is the
same as the correction per lead time.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .base import PvCorrectionInput, PvCorrector

HALF_LIFE = timedelta(days=14)
LEVELS = (0.35, 0.7)  # upper limits of "dull" and "mixed"; above: "sunny"
LEVEL_NAMES = ("dull", "mixed", "sunny")
HOUR_DAYS = 5.0  # days at an hour for half strength
LEVEL_DAYS = 10.0  # days in a level band for half strength
FACTOR_RANGE = (0.3, 2.0)
MIN_WH = 20.0  # hours with less (forecast and measured) teach nothing


def _level(wh: float, reference: float) -> int:
    ratio = wh / reference if reference > 0 else 1.0
    return next((i for i, limit in enumerate(LEVELS) if ratio < limit), len(LEVELS))


def _shrunk(ratio: float, days: float, half: float) -> float:
    return 1.0 + (ratio - 1.0) * days / (days + half)


class HourAndLevelCorrector(PvCorrector):
    """A factor per lead time x per hour of the day x per level."""

    key = "hour_and_level"
    verified = True
    name = "Per lead time, hour and level"

    def __init__(self) -> None:
        self.hours: dict[int, float] = {}
        self.levels: dict[str, float] = {}

    def details(self) -> dict[str, Any]:
        return {
            "hours": {h: round(f, 3) for h, f in sorted(self.hours.items())},
            "levels": {k: round(f, 3) for k, f in self.levels.items()},
        }

    def correct(self, data: PvCorrectionInput) -> Sequence[float | None]:
        # The most forecast per local hour: about a clear sky at that hour.
        reference: dict[int, float] = defaultdict(float)
        rows = []  # (local hour, weight, actual, [(raw, lead-corrected)], day)
        for result in data.results:
            local = dt_util.as_local(result.start)
            preds = [
                (p, p * data.bucket_factors.get(b, 1.0))
                for b, p in result.predictions.items()
            ]
            for raw, _ in preds:
                reference[local.hour] = max(reference[local.hour], raw)
            if result.actual < MIN_WH and all(p < MIN_WH for p, _ in preds):
                continue
            age = max((data.now - result.start).total_seconds(), 0.0)
            weight = math.pow(0.5, age / HALF_LIFE.total_seconds())
            rows.append((local.hour, weight, result.actual, preds, local.date()))
        for start, wh in data.slots:
            hour = dt_util.as_local(start).hour
            reference[hour] = max(reference[hour], wh)

        # Per hour of the day.
        sums: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
        days: dict[int, set] = defaultdict(set)
        for hour, weight, actual, preds, day in rows:
            for _, base in preds:
                sums[hour][0] += weight * actual
                sums[hour][1] += weight * base
            days[hour].add(day)
        self.hours = {
            h: _shrunk(s[0] / s[1], len(days[h]), HOUR_DAYS)
            for h, s in sums.items()
            if s[1] > 0
        }
        # Per level, after the hour factor.
        level_sums: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
        level_days: dict[int, set] = defaultdict(set)
        for hour, weight, actual, preds, day in rows:
            for raw, base in preds:
                band = _level(raw, reference[hour])
                level_sums[band][0] += weight * actual
                level_sums[band][1] += weight * base * self.hours.get(hour, 1.0)
                level_days[band].add(day)
        level_factor = {
            band: _shrunk(s[0] / s[1], len(level_days[band]), LEVEL_DAYS)
            for band, s in level_sums.items()
            if s[1] > 0
        }
        self.levels = {LEVEL_NAMES[b]: f for b, f in sorted(level_factor.items())}

        low, high = FACTOR_RANGE
        out: list[float | None] = []
        for start, wh in data.slots:
            hour = dt_util.as_local(start).hour
            factor = self.hours.get(hour, 1.0) * level_factor.get(
                _level(wh, reference[hour]), 1.0
            )
            factor = min(max(factor, low), high)
            out.append(wh * data.lead_factor(start) * factor)
        return out
