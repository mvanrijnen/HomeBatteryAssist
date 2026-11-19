"""Built-in consumption forecaster: the same time in the last weeks.

The expected consumption of a slot is the average of the same local weekday
and time in the last ``WEEKS`` weeks (only measured, non-vacation records).
Every record that overlaps the slot's time of day counts, by its overlap and
measured part (5-minute records in a 15-minute slot, an hourly imported
record for a quarter). Without such a record the slot has no prediction, and
HomeBatteryAssist uses the profile's prediction for it.

It also tells the outdoor temperatures of those records
(``reference_temps``), so the temperature step adds only the difference
between the forecast and the weather of those very weeks.

Simple and quick to follow changes in habits; sensitive to one-off days.
"""

from __future__ import annotations

from datetime import date, timedelta

from homeassistant.util import dt as dt_util

from .base import Forecaster, ForecasterInput, ForecasterResult

WEEKS = 2

type _Part = tuple[
    int, int, float, float, float | None
]  # from, to (min), weight, W, °C


class LastWeeksForecaster(Forecaster):
    """Same weekday and time, last weeks."""

    key = "last_weeks"
    verified = True
    name = "Same time in the last weeks"

    def forecast(self, data: ForecasterInput) -> ForecasterResult:
        # Local date -> parts of that day (minutes from local midnight).
        days: dict[date, list[_Part]] = {}
        cutoff = data.now - timedelta(weeks=WEEKS, days=1)
        for record in data.history:
            coverage = float(record.get("coverage", 0) or 0)
            if record.get("vacation") or coverage < 0.5:
                continue
            start = dt_util.parse_datetime(str(record["start"]))
            if start is None or start < cutoff:
                continue
            local = dt_util.as_local(start)
            begin = local.hour * 60 + local.minute
            minutes = int(record.get("minutes") or data.interval.total_seconds() // 60)
            temp = record.get("temp_c")
            days.setdefault(local.date(), []).append(
                (
                    begin,
                    begin + minutes,
                    coverage,
                    float(record["avg_w"]),
                    float(temp) if temp is not None else None,
                )
            )
        values: list[float | None] = []
        references: list[list[float] | None] = []
        for start, end in data.slots:
            local = dt_util.as_local(start)
            begin = local.hour * 60 + local.minute
            finish = begin + max(int((end - start).total_seconds() // 60), 1)
            found: list[tuple[float, list[float] | None]] = []
            for day in sorted(days, reverse=True):
                if day.weekday() != local.weekday() or day >= local.date():
                    continue
                total = weight = 0.0
                temps: list[float] | None = []
                for lo, hi, coverage, watts, temp in days[day]:
                    overlap = min(hi, finish) - max(lo, begin)
                    if overlap <= 0:
                        continue
                    w = overlap * coverage
                    total += w * watts
                    weight += w
                    if temp is None:
                        temps = None
                    elif temps is not None:
                        temps.append(temp)
                if weight > 0:
                    found.append((total / weight, temps or None))
                if len(found) == WEEKS:
                    break
            if not found:
                values.append(None)
                references.append(None)
                continue
            values.append(round(sum(v for v, _ in found) / len(found), 1))
            temps_all = [t for _, ts in found if ts for t in ts]
            references.append(
                temps_all if all(ts for _, ts in found) and temps_all else None
            )
        return ForecasterResult(
            values,
            [self.key if v is not None else None for v in values],
            references,
        )
