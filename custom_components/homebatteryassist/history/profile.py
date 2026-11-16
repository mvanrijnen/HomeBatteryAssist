"""Analyses of the consumption history: hourly series and average day profile."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from .consumption import ConsumptionRecord

WEEKEND = (5, 6)  # Saturday, Sunday


def _weighted(record: ConsumptionRecord) -> tuple[datetime, float, float]:
    start = dt_util.parse_datetime(record["start"])
    assert start is not None
    return start, record["avg_w"], record["minutes"] * record["coverage"]


def hourly_series(
    records: Iterable[ConsumptionRecord], since: datetime
) -> list[tuple[datetime, float, float, float | None, float | None]]:
    """Per clock hour from ``since``: house, excluded devices, PV and battery (W).

    PV / battery are None for hours without such measurements.
    """
    hours: dict[datetime, list[float]] = {}
    for record in records:
        start, avg, weight = _weighted(record)
        if start < since or weight <= 0:
            continue
        hour = start.replace(minute=0, second=0, microsecond=0)
        # house, excluded, weight, pv sum, pv weight, battery sum, battery weight
        acc = hours.setdefault(hour, [0.0] * 7)
        acc[0] += avg * weight
        acc[1] += record.get("excluded_w", 0.0) * weight
        acc[2] += weight
        if "pv_w" in record:
            acc[3] += record["pv_w"] * weight
            acc[4] += weight
        if "battery_w" in record:
            acc[5] += record["battery_w"] * weight
            acc[6] += weight
    return [
        (
            hour,
            round(a[0] / a[2], 1),
            round(a[1] / a[2], 1),
            round(a[3] / a[4], 1) if a[4] else None,
            round(a[5] / a[6], 1) if a[6] else None,
        )
        for hour, a in sorted(hours.items())
        if a[2]
    ]


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


def week_profiles(
    records: Iterable[ConsumptionRecord],
) -> list[dict[str, object]]:
    """The average day per local calendar week (Monday-Sunday), oldest first:
    ``start``/``end`` (dates), ``days`` (measured days) and weekday/weekend
    profiles as in ``day_profile``."""
    weeks: dict[str, list[ConsumptionRecord]] = {}
    for record in records:
        start, _avg, weight = _weighted(record)
        if weight <= 0:
            continue
        local = dt_util.as_local(start).date()
        monday = local - timedelta(days=local.weekday())
        weeks.setdefault(monday.isoformat(), []).append(record)
    return [
        {
            "start": monday,
            "end": (
                datetime.fromisoformat(monday).date() + timedelta(days=6)
            ).isoformat(),
            "days": days_covered(group),
            **day_profile(group),
        }
        for monday, group in sorted(weeks.items())
    ]


def days_covered(records: Iterable[ConsumptionRecord]) -> float:
    """How many days of measured consumption the history holds."""
    return round(sum(r["minutes"] * r["coverage"] for r in records) / (24 * 60), 1)
