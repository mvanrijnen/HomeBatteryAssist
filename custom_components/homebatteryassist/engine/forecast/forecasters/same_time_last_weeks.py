"""Built-in consumption forecaster: the same time in the last weeks.

The expected consumption of a slot is the average of the same local weekday
and time in the last ``WEEKS`` weeks (only measured, non-vacation records).
Without such a record the slot has no prediction, and HomeBatteryAssist uses
the profile's prediction for it.

Simple and quick to follow changes in habits; sensitive to one-off days.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.util import dt as dt_util

from .base import Forecaster, ForecasterInput, ForecasterResult

WEEKS = 2


class LastWeeksForecaster(Forecaster):
    """Same weekday and time, last weeks."""

    key = "last_weeks"
    verified = True
    name = "Same time in the last weeks"

    def forecast(self, data: ForecasterInput) -> ForecasterResult:
        # Local (weekday, hour, minute) -> recent values, newest first.
        by_time: dict[tuple[int, int, int], list[tuple[object, float]]] = {}
        cutoff = data.now - timedelta(weeks=WEEKS, days=1)
        for record in data.history:
            if record.get("vacation") or record["coverage"] < 0.5:
                continue
            start = dt_util.parse_datetime(record["start"])
            if start is None or start < cutoff:
                continue
            local = dt_util.as_local(start)
            key = (local.weekday(), local.hour, local.minute)
            by_time.setdefault(key, []).append((local.date(), record["avg_w"]))
        values: list[float | None] = []
        for start, _end in data.slots:
            local = dt_util.as_local(start)
            # Records may be hourly (imported) while slots are shorter.
            found = by_time.get(
                (local.weekday(), local.hour, local.minute)
            ) or by_time.get((local.weekday(), local.hour, 0))
            if not found:
                values.append(None)
                continue
            recent = sorted(found, key=lambda item: item[0], reverse=True)[:WEEKS]
            values.append(round(sum(v for _, v in recent) / len(recent), 1))
        return ForecasterResult(
            values, [self.key if v is not None else None for v in values]
        )
