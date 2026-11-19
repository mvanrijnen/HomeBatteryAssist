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
degrees at that day of the week and hour)`` (the same for cooling). The
"usual" degrees are what the profile already contains: averaged per day of
the week (Monday .. Sunday, no working days / weekend split) and hour, recent
days counting more (``HALF_LIFE``, as the weekday/hour profile), from the same
outdoor temperature the forecast is compared with (``temp_c``). So only the
*difference* with recent weather is added. The room temperature is a
setting, not a pattern: recent days count more (``ROOM_HALF_LIFE``: a lower
thermostat shows within days). It is learned per hour either for working days
together and the weekend (five times the measurements of one weekday) or per
day of the week (working from home on Thursday and Friday shows): whichever
predicted the last week better from the days before (``_room_means``). Without a temperature forecast for
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
HALF_LIFE = timedelta(days=14)  # as the weekday/hour profile
ROOM_HALF_LIFE = timedelta(days=7)  # room temperature: a setting, follow it soon
WORKDAYS = range(5)  # Monday .. Friday
ROOM_CHECK = timedelta(days=7)  # last week: which room table predicts best
MIN_ROOM_CHECK = 48  # hours with a room temperature needed for that check
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
    # (weekday, local hour) and, as fallback, local hour -> value
    usual_heating: Mapping[Any, float]  # heating degrees
    usual_cooling: Mapping[Any, float]
    gain_c: float = DEFAULT_GAIN_C
    usual_indoor: Mapping[Any, float] = field(default_factory=dict)  # °C
    name: str = ""  # the zone ("" = the house)

    @property
    def active(self) -> bool:
        """Something was learned that changes forecasts."""
        return self.heat_w_per_deg > 0 or self.cool_w_per_deg > 0

    @property
    def models(self) -> tuple[TemperatureModel, ...]:
        """The models it is made of (itself)."""
        return (self,)

    def room(self, weekday: int, hour: int) -> float:
        """The usual room temperature on a day of the week at a local hour."""
        return _usual(self.usual_indoor, weekday, hour, NOMINAL_INDOOR_C)

    @property
    def heating_point(self) -> float:
        """The outdoor temperature below which heating starts (during the day)."""
        return round(self.room_temperature(day=True) - self.gain_c, 1)

    def room_temperature(self, *, day: bool, weekday: int | None = None) -> float:
        """The usual room temperature during the day or at night, of one day
        of the week or of all days."""
        values = [
            v
            for key, v in self.usual_indoor.items()
            if isinstance(key, tuple)
            and (weekday is None or key[0] == weekday)
            and (key[1] in DAY_HOURS) == day
        ] or [NOMINAL_INDOOR_C]
        return round(sum(values) / len(values), 1)

    def effect(self, start: datetime, temp_c: float | None) -> float:
        """Extra W in a slot starting at ``start`` with ``temp_c`` forecast."""
        if temp_c is None or not math.isfinite(temp_c):
            return 0.0
        local = dt_util.as_local(start)
        weekday, hour = local.weekday(), local.hour
        base = self.room(weekday, hour) - self.gain_c
        heat = heating_degrees(temp_c, base) - _usual(
            self.usual_heating, weekday, hour, 0.0
        )
        cool = cooling_degrees(temp_c) - _usual(self.usual_cooling, weekday, hour, 0.0)
        return self.heat_w_per_deg * heat + self.cool_w_per_deg * cool

    def demand(self, start: datetime, temp_c: float | None) -> float | None:
        """The heating/cooling power (W) to expect in that slot itself, not
        the difference with the usual weather (dashboard)."""
        if temp_c is None or not math.isfinite(temp_c) or not self.active:
            return None
        local = dt_util.as_local(start)
        base = self.room(local.weekday(), local.hour) - self.gain_c
        return self.heat_w_per_deg * heating_degrees(
            temp_c, base
        ) + self.cool_w_per_deg * cooling_degrees(temp_c)

    def room_at(self, start: datetime) -> float | None:
        """The learned room temperature in that slot (None without a room
        sensor)."""
        if not self.usual_indoor:
            return None
        local = dt_util.as_local(start)
        return self.room(local.weekday(), local.hour)


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

    def demand(self, start: datetime, temp_c: float | None) -> float | None:
        values = [m.demand(start, temp_c) for m in self.models]
        known = [v for v in values if v is not None]
        return sum(known) if known else None

    def room_at(self, start: datetime) -> float | None:
        rooms = [r for m in self.models if (r := m.room_at(start)) is not None]
        return sum(rooms) / len(rooms) if rooms else None


TemperatureEffect = TemperatureModel | ZoneModels


def _room_table(
    rows: Sequence[_Row], now: datetime, per_weekday: bool
) -> dict[Any, float]:
    """Usual room temperature per (weekday, hour) and per hour, recent days
    counting more; per day of the week, or working days together and the
    weekend."""
    half_life = ROOM_HALF_LIFE.total_seconds()
    means = _Means()
    for row in rows:
        if row.indoor is None:
            continue
        age = max((now - row.start).total_seconds(), 0.0)
        group = row.weekday if per_weekday else (0 if row.weekday in WORKDAYS else 5)
        means.add(
            group, row.hour, row.indoor, row.weight * math.pow(0.5, age / half_life)
        )
    grouped = means.result(1)
    table: dict[Any, float] = {
        k: v for k, v in grouped.items() if not isinstance(k, tuple)
    }
    for key, value in grouped.items():
        if not isinstance(key, tuple):
            continue
        group, hour = key
        days = (group,) if per_weekday else (WORKDAYS if group == 0 else (5, 6))
        for weekday in days:
            table[(weekday, hour)] = value
    return table


def _room_means(rows: Sequence[_Row], now: datetime) -> dict[Any, float]:
    """The room temperature table that fits this house: per day of the week
    only when that predicted the last week clearly better (from the days
    before it) than working days together; else working days together."""
    split = now - ROOM_CHECK
    before = [r for r in rows if r.start < split]
    after = [r for r in rows if r.start >= split and r.indoor is not None]
    if len(after) >= MIN_ROOM_CHECK and before:

        def error(per_weekday: bool) -> float:
            table = _room_table(before, split, per_weekday)
            total = 0.0
            for row in after:
                guess = _usual(table, row.weekday, row.hour, NOMINAL_INDOOR_C)
                total += abs(guess - (row.indoor or 0.0))
            return total / len(after)

        if error(True) < BETTER_FIT * error(False):
            return _room_table(rows, now, True)
    return _room_table(rows, now, False)


def _usual(values: Mapping[Any, float], weekday: int, hour: int, default: float):
    """The value of that day of the week and hour, else of the hour."""
    value = values.get((weekday, hour))
    if value is None:
        value = values.get(hour, default)
    return value


class _Means:
    """Weighted means per (weekday, hour) and per hour."""

    def __init__(self) -> None:
        self._sums: dict[Any, list[float]] = defaultdict(lambda: [0.0, 0.0])

    def add(self, weekday: int, hour: int, value: float, weight: float) -> None:
        for key in ((weekday, hour), hour):
            self._sums[key][0] += weight * value
            self._sums[key][1] += weight

    def result(self, digits: int | None = None) -> dict[Any, float]:
        return {
            k: (round(v[0] / v[1], digits) if digits is not None else v[0] / v[1])
            for k, v in self._sums.items()
            if v[1]
        }


@dataclass(slots=True)
class _Row:
    """One usable record: what the fit needs."""

    start: datetime
    day: Any  # local date
    weekday: int  # local day of the week (Monday 0)
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
                local.weekday(),
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
    half_life = HALF_LIFE.total_seconds()

    def recency(row: _Row) -> float:
        age = max((now - row.start).total_seconds(), 0.0)
        return row.weight * math.pow(0.5, age / half_life)

    usual_indoor = _room_means(rows, now)

    def room(row: _Row) -> float:
        if row.indoor is not None:
            return row.indoor
        return _usual(usual_indoor, row.weekday, row.hour, NOMINAL_INDOOR_C)

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
    usual_heat, usual_cool = _Means(), _Means()
    for row in rows:
        weight = recency(row)
        degrees = heating_degrees(row.reference, room(row) - gain)
        usual_heat.add(row.weekday, row.hour, degrees, weight)
        usual_cool.add(row.weekday, row.hour, cooling_degrees(row.reference), weight)
    return TemperatureModel(
        round(heat, 1),
        round(cool, 1),
        len(days),
        target,
        usual_heat.result(),
        usual_cool.result(),
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
