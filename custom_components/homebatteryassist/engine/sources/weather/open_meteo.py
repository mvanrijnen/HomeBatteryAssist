"""Weather source: Open-Meteo (open-meteo.com), read directly.

A forecast per hour for up to 16 days, for any place, without an
integration in between. Free for non-commercial use without an API key
(10,000 requests per day; data CC BY 4.0: "Weather data by Open-Meteo.com");
with a key (commercial plan) the customer host is used. This source asks
once per ``CACHE`` (48 times a day).

``GET https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..
&current=temperature_2m&hourly=temperature_2m&forecast_days=7&timezone=GMT
&timeformat=unixtime[&models=..]``. The place is ``lat,lon`` from the
settings, by default the home location of Home Assistant rounded to 2
decimals (about 1 km). Answer: ``current.temperature_2m`` and
``hourly.time`` / ``hourly.temperature_2m`` (Unix seconds, °C); an error is
``{"error": true, "reason": ...}``.

``OpenMeteoWeatherSource`` uses Open-Meteo's best model for the place;
``OpenMeteoKnmiSource`` the KNMI models (HARMONIE, then ECMWF further ahead:
``knmi_seamless``). Verified against the live API. Read only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .base import WeatherSource, valid_temperature

_LOGGER = logging.getLogger(__name__)

URL = "https://api.open-meteo.com/v1/forecast"
CUSTOMER_URL = "https://customer-api.open-meteo.com/v1/forecast"
CACHE = timedelta(minutes=30)
RETRY = timedelta(minutes=10)
TIMEOUT = aiohttp.ClientTimeout(total=20)
FORECAST_DAYS = 7  # the longest planning horizon
ATTRIBUTION = "Weather data by Open-Meteo.com"


def parse_location(text: str | None) -> tuple[float, float] | None:
    """``"lat,lon"`` as numbers, or None."""
    try:
        lat, lon = (float(x) for x in str(text).split(","))
    except (TypeError, ValueError):
        return None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def parse_open_meteo(payload: object) -> tuple[float | None, dict[datetime, float]]:
    """(temperature now, °C per UTC hour) from an Open-Meteo answer."""
    if not isinstance(payload, dict):
        return None, {}
    current = payload.get("current") or {}
    now = (
        valid_temperature(current.get("temperature_2m"))
        if isinstance(current, dict)
        else None
    )
    hourly = payload.get("hourly") or {}
    out: dict[datetime, float] = {}
    if isinstance(hourly, dict):
        for stamp, temp in zip(
            hourly.get("time") or [], hourly.get("temperature_2m") or [], strict=False
        ):
            celsius = valid_temperature(temp)
            try:
                when = datetime.fromtimestamp(int(stamp), tz=dt_util.UTC)
            except (TypeError, ValueError, OverflowError, OSError):
                continue
            if celsius is not None:
                out[when.replace(minute=0, second=0, microsecond=0)] = celsius
    return now, out


class OpenMeteoWeatherSource(WeatherSource):
    """Open-Meteo for the user's place (best model)."""

    key = "open_meteo"
    name = "Open-Meteo (direct)"
    model: str | None = None  # Open-Meteo's ``models`` parameter

    def __init__(self, settings=None) -> None:
        """Initialize."""
        super().__init__(settings)
        self._now: float | None = None
        self._cache: dict[datetime, float] = {}
        self._read_at: datetime | None = None
        self._failed = False
        self.error: str | None = None

    def coordinates(self, hass: HomeAssistant) -> tuple[float, float] | None:
        """The place: ``lat,lon`` from the settings, else home (2 decimals)."""
        if self.settings.location:
            return parse_location(self.settings.location)
        return round(hass.config.latitude, 2), round(hass.config.longitude, 2)

    def describe(self) -> str:
        """Place and state."""
        state = self.error or ("ok" if self._cache else "not read yet")
        return f"{self.name} ({self.settings.location or 'home'}): {state}"

    def temperature_now(self, hass: HomeAssistant) -> float | None:
        """The temperature of the last answer."""
        return self._now

    async def async_forecast(self, hass: HomeAssistant) -> dict[datetime, float]:
        """The forecast (cached; the last good one while requests fail)."""
        now = dt_util.utcnow()
        wait = RETRY if self._failed else CACHE
        if self._read_at is not None and now - self._read_at < wait:
            return self._cache
        self._read_at = now
        place = self.coordinates(hass)
        if place is None:
            self.error = "place is not 'latitude,longitude'"
            return self._cache
        params: dict[str, str | int | float] = {
            "latitude": place[0],
            "longitude": place[1],
            "current": "temperature_2m",
            "hourly": "temperature_2m",
            "forecast_days": FORECAST_DAYS,
            "timezone": "GMT",
            "timeformat": "unixtime",
        }
        if self.model:
            params["models"] = self.model
        url = URL
        if self.settings.api_key:
            url, params["apikey"] = CUSTOMER_URL, self.settings.api_key
        try:
            session = async_get_clientsession(hass)
            async with session.get(url, params=params, timeout=TIMEOUT) as response:
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            self._failed = True
            self.error = f"request failed ({type(err).__name__})"
            _LOGGER.debug("Open-Meteo: %s", err)
            return self._cache
        temperature, forecast = parse_open_meteo(payload)
        if not forecast:
            self._failed = True
            reason = payload.get("reason") if isinstance(payload, dict) else None
            self.error = str(reason)[:200] if reason else "no forecast in the answer"
            return self._cache
        self._failed = False
        self.error = None
        self._now = temperature
        self._cache = forecast
        return forecast


class OpenMeteoKnmiSource(OpenMeteoWeatherSource):
    """Open-Meteo with the KNMI models (HARMONIE, then ECMWF)."""

    key = "open_meteo_knmi"
    name = "Open-Meteo, KNMI model (direct)"
    model = "knmi_seamless"
