"""The interface of a weather source (a module kind).

A weather source reads the outdoor temperature now and its forecast per
clock hour (UTC hour start -> °C). It gets the user's ``WeatherSettings``
(weather entity, API key, location). HomeBatteryAssist keeps the final say
(``checked_forecast``): values outside ``MIN_C``..``MAX_C`` or not finite are
dropped. A source only reads; it never controls anything.

Helpers for sources: ``daily_curve`` turns daily minimum / maximum
temperatures into hourly values (lowest early morning, highest mid
afternoon) and ``combine`` fills the hours after an hourly forecast with it,
so the forecast reaches as far as the planning (up to 7 days).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

MIN_C = -60.0
MAX_C = 60.0
INDOOR_MIN_C = 5.0  # believable room temperatures
INDOOR_MAX_C = 35.0


def valid_temperature(value: object) -> float | None:
    """``value`` as °C if it is a believable outdoor temperature."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and MIN_C <= number <= MAX_C else None


def valid_indoor(value: object) -> float | None:
    """``value`` as °C if it is a believable room temperature."""
    number = valid_temperature(value)
    if number is None or not INDOOR_MIN_C <= number <= INDOOR_MAX_C:
        return None
    return number


# The daily curve: coldest at this local hour, warmest at that one.
COLDEST_HOUR = 5
WARMEST_HOUR = 15
HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class WeatherSettings:
    """What the user set up for the weather (all optional)."""

    entity_id: str | None = None  # weather.* (weather entity, KNMI)
    api_key: str | None = None  # e.g. Weerlive
    location: str | None = None  # "lat,lon" or a place; None = home


def checked_forecast(value: object) -> dict[datetime, float]:
    """The final check on a source's forecast: aware datetimes on the hour
    (as UTC) with believable °C; anything else is dropped."""
    if not isinstance(value, Mapping):
        return {}
    out: dict[datetime, float] = {}
    for when, temp in value.items():
        celsius = valid_temperature(temp)
        if not isinstance(when, datetime) or when.tzinfo is None or celsius is None:
            continue
        out[dt_util.as_utc(when).replace(minute=0, second=0, microsecond=0)] = celsius
    return out


def daily_curve(days: Mapping[date, tuple[float, float]]) -> dict[datetime, float]:
    """Hourly °C (UTC hour start) from (minimum, maximum) per local day.

    Lowest at ``COLDEST_HOUR``, highest at ``WARMEST_HOUR``, a smooth
    (cosine) course in between and on to the next day's minimum. Covers the
    whole local days given.
    """
    anchors: list[tuple[datetime, float]] = []
    for day in sorted(days):
        low, high = days[day]
        low, high = min(low, high), max(low, high)
        for hour, value in ((COLDEST_HOUR, low), (WARMEST_HOUR, high)):
            local = datetime.combine(day, time(hour), dt_util.get_default_time_zone())
            anchors.append((dt_util.as_utc(local), value))
    if not anchors:
        return {}
    out: dict[datetime, float] = {}
    first = dt_util.as_utc(
        datetime.combine(min(days), time(0), dt_util.get_default_time_zone())
    )
    last = dt_util.as_utc(
        datetime.combine(
            max(days) + timedelta(days=1), time(0), dt_util.get_default_time_zone()
        )
    )
    when, index = first, 0
    while when < last:
        while index + 1 < len(anchors) and anchors[index + 1][0] <= when:
            index += 1
        start, a = anchors[index]
        if when <= start or index + 1 >= len(anchors):
            value = a  # before the first / after the last anchor: hold
        else:
            end, b = anchors[index + 1]
            share = (when - start) / (end - start)
            value = a + (b - a) * (1 - math.cos(math.pi * share)) / 2
        out[when] = round(value, 1)
        when += HOUR
    return out


def combine(
    hourly: Mapping[datetime, float], daily: Mapping[datetime, float]
) -> dict[datetime, float]:
    """The hourly forecast, and after its last hour the daily curve."""
    out = dict(hourly)
    end = max(hourly) if hourly else None
    for when, value in daily.items():
        if end is None or when > end:
            out.setdefault(when, value)
    return dict(sorted(out.items()))


class WeatherSource:
    """Base class of a weather source.

    Made once per (re)load with the user's ``settings``; ``describe`` says
    what it reads (diagnostics, *Why*).
    """

    key: str = ""
    name: str = ""
    # Tested on a real setup; until then every place where it is chosen
    # says "not tested". Own modules too: set True only after testing.
    verified: bool = False

    def __init__(self, settings: WeatherSettings | None = None) -> None:
        """Initialize with the user's weather settings."""
        self.settings = settings or WeatherSettings()

    def describe(self) -> str:
        """What this source reads, e.g. the entity id."""
        return self.name or self.key

    def temperature_now(self, hass: HomeAssistant) -> float | None:
        """The outdoor temperature now (°C), or None."""
        raise NotImplementedError

    async def async_forecast(self, hass: HomeAssistant) -> dict[datetime, float]:
        """Forecast temperature (°C) per UTC clock hour start."""
        raise NotImplementedError
