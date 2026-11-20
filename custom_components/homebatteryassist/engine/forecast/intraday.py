"""Correction within the day: when the house uses clearly more (or less)
today than forecast so far, the rest of today counts on that too.

The measured consumption since local midnight (intervals with enough
coverage) is compared with what the forecast would have said for those same
intervals (made from the history before today, corrected as usual). The
ratio moves the rest of today's forecast, gradually: nothing before
``START_HOUR``, fully from ``FULL_HOUR``, and never more than ``MAX_SHIFT``.
Only today's slots change; tomorrow starts from the normal forecast again.
What accuracy learns from (``raw_w``) is not changed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

from homeassistant.util import dt as dt_util

START_HOUR = 3  # local: before this too little of the day is known
FULL_HOUR = 12  # local: from here the full shift applies
MAX_SHIFT = 0.30  # at most 30 % more or less
MIN_COVERAGE = 0.75  # an interval counts when measured this much of the time
MIN_PREDICTED_WH = 500.0  # too little expected so far to compare with


@dataclass(frozen=True, slots=True)
class IntradayCorrection:
    """The shift for the rest of ``day`` (local date)."""

    day: date
    factor: float  # multiplies today's remaining slots
    ratio: float  # measured / predicted so far
    weight: float  # 0..1 by the time of day
    measured_wh: float
    predicted_wh: float

    def applies(self, start: datetime) -> bool:
        """True for a slot of the same local day."""
        return dt_util.as_local(start).date() == self.day

    def as_dict(self) -> dict[str, float | str]:
        """JSON-friendly (diagnostics)."""
        return {
            "day": self.day.isoformat(),
            "factor": round(self.factor, 3),
            "ratio": round(self.ratio, 3),
            "weight": round(self.weight, 2),
            "measured_kwh": round(self.measured_wh / 1000, 2),
            "predicted_kwh": round(self.predicted_wh / 1000, 2),
        }


def weight_at(local: datetime) -> float:
    """How much of the shift applies at this local time (0..1)."""
    hours = local.hour + local.minute / 60
    if hours < START_HOUR:
        return 0.0
    if hours >= FULL_HOUR:
        return 1.0
    return (hours - START_HOUR) / (FULL_HOUR - START_HOUR)


def measured_today(
    records: Iterable[Mapping], midnight: datetime, now: datetime
) -> dict[datetime, float]:
    """Measured average house power (W) per interval start of today that
    ended before ``now`` and has enough coverage."""
    result: dict[datetime, float] = {}
    for record in records:
        start = dt_util.parse_datetime(str(record.get("start", "")))
        if start is None or start < midnight or record.get("vacation"):
            continue
        minutes = float(record.get("minutes", 0) or 0)
        if start.timestamp() + minutes * 60 > now.timestamp():
            continue
        if float(record.get("coverage", 0) or 0) < MIN_COVERAGE:
            continue
        try:
            result[start] = float(record["avg_w"])
        except (KeyError, TypeError, ValueError):
            continue
    return result


def intraday_correction(
    measured: Mapping[datetime, float],
    predicted: Mapping[datetime, float],
    hours: float,
    now: datetime,
) -> IntradayCorrection | None:
    """The shift from the intervals both measured and predicted (``hours``
    per interval), or None when there is too little to go on."""
    local = dt_util.as_local(now)
    weight = weight_at(local)
    common = [s for s in measured if s in predicted]
    if weight <= 0 or not common:
        return None
    measured_wh = sum(measured[s] for s in common) * hours
    predicted_wh = sum(predicted[s] for s in common) * hours
    if predicted_wh < MIN_PREDICTED_WH:
        return None
    ratio = measured_wh / predicted_wh
    shift = max(-MAX_SHIFT, min(MAX_SHIFT, ratio - 1)) * weight
    return IntradayCorrection(
        local.date(), 1 + shift, ratio, weight, measured_wh, predicted_wh
    )
