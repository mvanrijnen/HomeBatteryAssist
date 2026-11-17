"""The effect of the temperature on the consumption (optional).

Houses that heat or cool with electricity (heat pump, airco) use more on a
cold (or hot) day. A weekday/hour profile follows a sudden cold spell only
after days; this step adds what the temperature forecast says, as soon as it
says it.

Learned from the history: per day, the average consumption against the
average *heating degrees* (how far the outdoor temperature is below the
heating point) and *cooling degrees* (how far it is above ``COOLING_BASE_C``).
The slopes (W per degree) come from a least-squares fit over the days; days
instead of hours keep the daily rhythm (cooking, sleeping) out of it.

The heating point is the room temperature minus what the house warms itself
(people, appliances, sun): ``room - gain``. The room temperature is
``NOMINAL_INDOOR_C`` unless an indoor sensor measures it; the gain is learned
(the value in ``GAIN_STEPS`` that fits the days best, ``DEFAULT_GAIN_C``
unless another fits clearly better). An indoor sensor so also tells the
desired room temperature per hour (e.g. lower at night), which is used for
the forecast.

What is fitted:

- **zones** (heating/cooling devices, e.g. an airco per room): each zone's
  own power against its own indoor and outdoor sensor (when it has them);
  the effects of the zones add up;
- otherwise the **house**: the heating/cooling power of all devices together
  (``heating_w``) or, without such a device, the whole house (``avg_w``).

Applied per slot: ``value + heat * (forecast heating degrees - usual heating
degrees at that hour lately)`` (the same for cooling). The "usual" degrees are
what the profile already contains (the last ``RECENT_DAYS``, from the same
outdoor temperature the forecast is compared with: ``temp_c``), so only the
*difference* with recent weather is added. Without a temperature forecast for
a slot, or without enough history, nothing changes.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from ..sources.weather import valid_indoor

NOMINAL_INDOOR_C = 20.0  # room temperature without an indoor sensor
DEFAULT_GAIN_C = 4.0  # heating from 16 °C outside at 20 °C inside
GAIN_STEPS = tuple(x / 2 for x in range(0, 17))  # 0 .. 8 °C
BETTER_FIT = 0.9  # another gain must leave at most this much of the error
COOLING_BASE_C = 22.0  # warmer than this: cooling
HEATING_BASE_C = NOMINAL_INDOOR_C - DEFAULT_GAIN_C
MIN_DAYS = 7  # days with temperature and consumption needed to learn
MIN_SPREAD = 1.0  # degrees: the days must differ this much to learn a slope
MIN_COVERAGE = 0.8  # a day must be measured (and have a temperature) this much
RECENT_DAYS = 7  # the weather the profile already contains
MAX_SLOPE_W = 2000.0  # W per degree: anything more is not believed
DAY_HOURS = range(7, 23)  # "during the day" for the room temperature


def heating_degrees(temp_c: float, base_c: float = HEATING_BASE_C) -> float:
    """Degrees below the heating point (0 when warmer)."""
    return max(base_c - temp_c, 0.0)


def cooling_degrees(temp_c: float) -> float:
    """Degrees above the cooling base (0 when colder)."""
    return max(temp_c - COOLING_BASE_C, 0.0)


@dataclass(frozen=True, slots=True)
class TemperatureModel:
    """What was learned for the house or one zone: W per heating / cooling
    degree, the gain, and the usual degrees and room temperature per local
    hour lately."""

    heat_w_per_deg: float
    cool_w_per_deg: float
    days: int
    target: str  # "heating_w" (meters), "avg_w" (whole house) or "zone"
    usual_heating: Mapping[int, float]  # local hour -> heating degrees
    usual_cooling: Mapping[int, float]
    gain_c: float = DEFAULT_GAIN_C
    usual_indoor: Mapping[int, float] = field(default_factory=dict)
    name: str = ""  # the zone ("" = the house)

    @property
    def active(self) -> bool:
        """Something was learned that changes forecasts."""
        return self.heat_w_per_deg > 0 or self.cool_w_per_deg > 0

    @property
    def models(self) -> tuple[TemperatureModel, ...]:
        """The models it is made of (itself)."""
        return (self,)

    def room(self, hour: int) -> float:
        """The usual room temperature at a local hour."""
        return self.usual_indoor.get(hour, NOMINAL_INDOOR_C)

    @property
    def heating_point(self) -> float:
        """The outdoor temperature below which heating starts (during the day)."""
        return round(self.room_temperature(day=True) - self.gain_c, 1)

    def room_temperature(self, *, day: bool) -> float:
        """The usual room temperature during the day or at night."""
        hours = [
            v for h, v in self.usual_indoor.items() if (h in DAY_HOURS) == day
        ] or [NOMINAL_INDOOR_C]
        return round(sum(hours) / len(hours), 1)

    def effect(self, start: datetime, temp_c: float | None) -> float:
        """Extra W in a slot starting at ``start`` with ``temp_c`` forecast."""
        if temp_c is None or not math.isfinite(temp_c):
            return 0.0
        hour = dt_util.as_local(start).hour
        base = self.room(hour) - self.gain_c
        heat = heating_degrees(temp_c, base) - self.usual_heating.get(hour, 0.0)
        cool = cooling_degrees(temp_c) - self.usual_cooling.get(hour, 0.0)
        return self.heat_w_per_deg * heat + self.cool_w_per_deg * cool


@dataclass(frozen=True, slots=True)
class ZoneModels:
    """The zones together: their effects add up."""

    models: tuple[TemperatureModel, ...]

    @property
    def active(self) -> bool:
        return any(m.active for m in self.models)

    @property
    def days(self) -> int:
        return min(m.days for m in self.models)

    def effect(self, start: datetime, temp_c: float | None) -> float:
        return sum(m.effect(start, temp_c) for m in self.models)


TemperatureEffect = TemperatureModel | ZoneModels


@dataclass(slots=True)
class _Row:
    """One usable record: what the fit needs."""

    start: datetime
    day: Any  # local date
    hour: int  # local hour
    weight: float
    value: float  # the fitted power
    outdoor: float  # outdoor temperature for the fit
    reference: float  # outdoor temperature the forecast is compared with
    indoor: float | None


def _rows(
    records: Sequence[Mapping[str, Any]], zone: str | None, target: str
) -> list[_Row]:
    rows = []
    for record in records:
        if record.get("vacation") or float(record.get("coverage", 0) or 0) <= 0:
            continue
        reference = record.get("temp_c")
        if zone is None:
            if reference is None or (target == "heating_w" and target not in record):
                continue
            value, outdoor, indoor = record.get(target), reference, None
        else:
            data = (record.get("zones") or {}).get(zone)
            if not isinstance(data, Mapping) or data.get("w") is None:
                continue
            value = data["w"]
            outdoor = data.get("out", reference)
            indoor = valid_indoor(data.get("in"))
            if outdoor is None:
                continue
            if reference is None:
                reference = outdoor
        start = dt_util.parse_datetime(str(record["start"]))
        if start is None:
            continue
        local = dt_util.as_local(start)
        rows.append(
            _Row(
                start,
                local.date(),
                local.hour,
                float(record["minutes"]) * float(record["coverage"]),
                float(value or 0.0),
                float(outdoor),
                float(reference),
                indoor,
            )
        )
    return rows


def fit_temperature(
    records: Sequence[Mapping[str, Any]],
    now: datetime,
    zone: str | None = None,
    name: str = "",
) -> TemperatureModel | None:
    """Learn the temperature effect of the house (``zone`` None) or of one
    zone from ``records`` (None: not enough)."""
    if zone is None:
        target = "heating_w" if any("heating_w" in r for r in records) else "avg_w"
    else:
        target = "zone"
    rows = _rows(records, zone, target)
    if not rows:
        return None
    recent = now - timedelta(days=RECENT_DAYS)
    indoor: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for row in rows:
        if row.indoor is not None and row.start >= recent:
            indoor[row.hour][0] += row.weight * row.indoor
            indoor[row.hour][1] += row.weight
    usual_indoor = {h: round(v[0] / v[1], 1) for h, v in indoor.items() if v[1]}

    def room(row: _Row) -> float:
        if row.indoor is not None:
            return row.indoor
        return usual_indoor.get(row.hour, NOMINAL_INDOOR_C)

    def days_for(gain: float) -> list[tuple[float, float, float]]:
        sums: dict[Any, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
        for row in rows:
            day = sums[row.day]
            day[0] += row.weight * row.value
            day[1] += row.weight * heating_degrees(row.outdoor, room(row) - gain)
            day[2] += row.weight * cooling_degrees(row.outdoor)
            day[3] += row.weight
        return [
            (s[0] / s[3], s[1] / s[3], s[2] / s[3])
            for s in sums.values()
            if s[3] >= MIN_COVERAGE * 1440
        ]

    days = days_for(DEFAULT_GAIN_C)
    if len(days) < MIN_DAYS:
        return None
    gain = DEFAULT_GAIN_C
    heat, cool, error = _slopes(days)
    if heat > 0:
        for candidate in GAIN_STEPS:
            h, c, e = _slopes(days_for(candidate))
            if h > 0 and e < BETTER_FIT * error:
                gain, heat, cool, error = candidate, h, c, e
    usual: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for row in rows:
        if row.start >= recent:
            hour = usual[row.hour]
            hour[0] += row.weight * heating_degrees(row.reference, room(row) - gain)
            hour[1] += row.weight * cooling_degrees(row.reference)
            hour[2] += row.weight
    return TemperatureModel(
        round(heat, 1),
        round(cool, 1),
        len(days),
        target,
        {h: v[0] / v[2] for h, v in usual.items() if v[2]},
        {h: v[1] / v[2] for h, v in usual.items() if v[2]},
        gain,
        usual_indoor,
        name,
    )


def fit_effect(
    records: Sequence[Mapping[str, Any]],
    now: datetime,
    zones: Mapping[str, str] | None = None,
) -> TemperatureEffect | None:
    """The temperature effect: the zones (id -> name) when every zone has
    learned enough, otherwise the house."""
    if zones:
        models = [fit_temperature(records, now, z, n) for z, n in zones.items()]
        if all(m is not None for m in models):
            return ZoneModels(tuple(m for m in models if m is not None))
    return fit_temperature(records, now)


def _slopes(days: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """Least squares ``y = a + h·hd + c·cd``; a variable that hardly varies is
    left out. Slopes are never negative (colder never means less heating).
    Also returns the squared error of the fit."""
    n = len(days)
    if not n:
        return 0.0, 0.0, math.inf
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
    h, c = (min(max(v, 0.0), MAX_SLOPE_W) for v in (h, c))
    a = my - h * mh - c * mc
    error = sum((d[0] - a - h * d[1] - c * d[2]) ** 2 for d in days)
    return h, c, error


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
