"""The effect of the outdoor temperature on the consumption (optional).

Houses that heat or cool with electricity (heat pump, airco) use more on a
cold (or hot) day. A weekday/hour profile follows a sudden cold spell only
after days; this step adds what the temperature forecast says, as soon as it
says it.

Learned from the history (records with ``temp_c``, the outdoor temperature):
per day, the average consumption against the average *heating degrees*
(``HEATING_BASE_C`` minus the temperature, when colder) and *cooling degrees*
(the temperature minus ``COOLING_BASE_C``, when warmer). The slopes (W per
degree) come from a least-squares fit over the days; days instead of hours
keep the daily rhythm (cooking, sleeping) out of it. With a heating/cooling
meter (``heating_w``), that power is fitted instead of the whole house: a
cleaner signal.

Applied per slot: ``value + heat * (forecast heating degrees - usual heating
degrees at that hour lately)`` (the same for cooling). The "usual" degrees are
what the profile already contains (the last ``RECENT_DAYS``), so only the
*difference* with recent weather is added. Without a temperature forecast for
a slot, or without enough history, nothing changes.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

HEATING_BASE_C = 16.0  # colder than this: heating
COOLING_BASE_C = 22.0  # warmer than this: cooling
MIN_DAYS = 7  # days with temperature and consumption needed to learn
MIN_SPREAD = 1.0  # degrees: the days must differ this much to learn a slope
MIN_COVERAGE = 0.8  # a day must be measured (and have a temperature) this much
RECENT_DAYS = 7  # the weather the profile already contains
MAX_SLOPE_W = 2000.0  # W per degree: anything more is not believed


def heating_degrees(temp_c: float) -> float:
    """Degrees below the heating base (0 when warmer)."""
    return max(HEATING_BASE_C - temp_c, 0.0)


def cooling_degrees(temp_c: float) -> float:
    """Degrees above the cooling base (0 when colder)."""
    return max(temp_c - COOLING_BASE_C, 0.0)


@dataclass(frozen=True, slots=True)
class TemperatureModel:
    """What was learned: W per heating / cooling degree, and the usual degrees
    per local hour lately (what the profile already contains)."""

    heat_w_per_deg: float
    cool_w_per_deg: float
    days: int
    target: str  # "heating_w" (meter) or "avg_w" (whole house)
    usual_heating: Mapping[int, float]  # local hour -> heating degrees
    usual_cooling: Mapping[int, float]

    @property
    def active(self) -> bool:
        """Something was learned that changes forecasts."""
        return self.heat_w_per_deg > 0 or self.cool_w_per_deg > 0

    def effect(self, start: datetime, temp_c: float | None) -> float:
        """Extra W in a slot starting at ``start`` with ``temp_c`` forecast."""
        if temp_c is None or not math.isfinite(temp_c):
            return 0.0
        hour = dt_util.as_local(start).hour
        heat = heating_degrees(temp_c) - self.usual_heating.get(hour, 0.0)
        cool = cooling_degrees(temp_c) - self.usual_cooling.get(hour, 0.0)
        return self.heat_w_per_deg * heat + self.cool_w_per_deg * cool


def _usable(record: Mapping[str, Any]) -> bool:
    return (
        record.get("temp_c") is not None
        and not record.get("vacation")
        and float(record.get("coverage", 0)) > 0
    )


def fit_temperature(
    records: Sequence[Mapping[str, Any]], now: datetime
) -> TemperatureModel | None:
    """Learn the temperature effect from ``records`` (None: not enough)."""
    use = [r for r in records if _usable(r)]
    if not use:
        return None
    target = "heating_w" if any("heating_w" in r for r in use) else "avg_w"
    # Per local day: time-weighted means of the target and the degrees.
    sums: dict[Any, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0.0])
    usual: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    recent = now - timedelta(days=RECENT_DAYS)
    for record in use:
        start = dt_util.parse_datetime(str(record["start"]))
        if start is None:
            continue
        weight = float(record["minutes"]) * float(record["coverage"])
        temp = float(record["temp_c"])
        local = dt_util.as_local(start)
        day = sums[local.date()]
        day[0] += weight * float(record.get(target, 0.0) or 0.0)
        day[1] += weight * heating_degrees(temp)
        day[2] += weight * cooling_degrees(temp)
        day[3] += weight
        if start >= recent:
            hour = usual[local.hour]
            hour[0] += weight * heating_degrees(temp)
            hour[1] += weight * cooling_degrees(temp)
            hour[2] += weight
    days = [
        (s[0] / s[3], s[1] / s[3], s[2] / s[3])
        for s in sums.values()
        if s[3] >= MIN_COVERAGE * 1440
    ]
    if len(days) < MIN_DAYS:
        return None
    heat, cool = _slopes(days)
    return TemperatureModel(
        round(heat, 1),
        round(cool, 1),
        len(days),
        target,
        {h: v[0] / v[2] for h, v in usual.items() if v[2]},
        {h: v[1] / v[2] for h, v in usual.items() if v[2]},
    )


def _slopes(days: list[tuple[float, float, float]]) -> tuple[float, float]:
    """Least squares ``y = a + h·hd + c·cd``; a variable that hardly varies is
    left out. Slopes are never negative (colder never means less heating)."""
    n = len(days)
    my = sum(d[0] for d in days) / n
    mh = sum(d[1] for d in days) / n
    mc = sum(d[2] for d in days) / n
    shh = sum((d[1] - mh) ** 2 for d in days)
    scc = sum((d[2] - mc) ** 2 for d in days)
    shc = sum((d[1] - mh) * (d[2] - mc) for d in days)
    shy = sum((d[1] - mh) * (d[0] - my) for d in days)
    scy = sum((d[2] - mc) * (d[0] - my) for d in days)
    spread = MIN_SPREAD**2 * n / 4  # variance of a spread of MIN_SPREAD degrees
    use_h, use_c = shh >= spread, scc >= spread
    h = c = 0.0
    if use_h and use_c and (det := shh * scc - shc * shc) > 1e-9:
        h = (shy * scc - scy * shc) / det
        c = (scy * shh - shy * shc) / det
    elif use_h:
        h = shy / shh
    elif use_c:
        c = scy / scc
    clamp = lambda v: min(max(v, 0.0), MAX_SLOPE_W)  # noqa: E731
    return clamp(h), clamp(c)


def slot_temperatures(
    slots: Sequence[tuple[datetime, datetime]], hourly: Mapping[datetime, float]
) -> list[float | None]:
    """The forecast temperature per slot: the value of the hour the slot's
    middle falls in (None beyond the forecast)."""
    out: list[float | None] = []
    for start, end in slots:
        middle = dt_util.as_utc(start + (end - start) / 2)
        hour = middle.replace(minute=0, second=0, microsecond=0)
        out.append(hourly.get(hour))
    return out
