"""Analyses of the consumption history: hourly series and average day profile."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from homeassistant.util import dt as dt_util

from .consumption import ConsumptionRecord

WEEKEND = (5, 6)  # Saturday, Sunday


def _weighted(record: ConsumptionRecord) -> tuple[datetime, float, float]:
    start = dt_util.parse_datetime(record["start"])
    assert start is not None
    return start, record["avg_w"], record["minutes"] * record["coverage"]


def hourly_series(
    records: Iterable[ConsumptionRecord], since: datetime
) -> list[tuple[datetime, float]]:
    """Average consumption (W) per clock hour from ``since``, weighted by coverage."""
    hours: dict[datetime, list[float]] = {}
    for record in records:
        start, avg, weight = _weighted(record)
        if start < since or weight <= 0:
            continue
        hour = start.replace(minute=0, second=0, microsecond=0)
        acc = hours.setdefault(hour, [0.0, 0.0])
        acc[0] += avg * weight
        acc[1] += weight
    return [(hour, round(s / w, 1)) for hour, (s, w) in sorted(hours.items()) if w]


def day_profile(
    records: Iterable[ConsumptionRecord],
) -> dict[str, list[float | None]]:
    """Average consumption (W) per local hour of the day, weekdays vs weekend."""
    sums = {
        "weekday": [[0.0, 0.0] for _ in range(24)],
        "weekend": [[0.0, 0.0] for _ in range(24)],
    }
    for record in records:
        start, avg, weight = _weighted(record)
        if weight <= 0:
            continue
        # Hourly records cover one local hour; finer records fall in one hour.
        local = dt_util.as_local(start)
        kind = "weekend" if local.weekday() in WEEKEND else "weekday"
        acc = sums[kind][local.hour]
        acc[0] += avg * weight
        acc[1] += weight
    return {
        kind: [round(s / w, 1) if w else None for s, w in hours]
        for kind, hours in sums.items()
    }


def days_covered(records: Iterable[ConsumptionRecord]) -> float:
    """How many days of measured consumption the history holds."""
    return round(sum(r["minutes"] * r["coverage"] for r in records) / (24 * 60), 1)
