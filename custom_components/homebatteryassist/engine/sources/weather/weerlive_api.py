"""Weather source: the Weerlive API (weerlive.nl), read directly.

KNMI weather data for a place in the Netherlands, without an integration in
between. Needs a free API key (register on weerlive.nl); at most 300
requests per day, for private and hobby use, with the source mentioned
("KNMI Weergegevens via Weerlive.nl"). This source asks once per ``CACHE``
(48 times a day); an integration using the same key (e.g. KNMI) counts
against the same limit.

``GET https://weerlive.nl/api/weerlive_api_v2.php?key=<key>&locatie=<place>``
(place: a name or ``lat,lon``; by default the home location of Home
Assistant, rounded to 2 decimals, about 1 km). Answer:

- ``liveweer[0].temp``: the temperature now (°C);
- ``uur_verw``: the next 24 hours, ``timestamp`` (Unix) and ``temp``;
- ``wk_verw``: 5 days, ``dag`` (``dd-mm-yyyy``), ``min_temp``, ``max_temp``;
- ``api[0].rest_verz``: requests left today.

Verified against the live API. Read only.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .base import WeatherSource, combine, daily_curve, valid_temperature

_LOGGER = logging.getLogger(__name__)

URL = "https://weerlive.nl/api/weerlive_api_v2.php"
CACHE = timedelta(minutes=30)
RETRY = timedelta(minutes=10)  # after a failed request
TIMEOUT = aiohttp.ClientTimeout(total=20)
ATTRIBUTION = "KNMI Weergegevens via Weerlive.nl"


def parse_weerlive(payload: object) -> tuple[float | None, dict[datetime, float]]:
    """(temperature now, °C per UTC hour) from a Weerlive answer."""
    if not isinstance(payload, dict):
        return None, {}
    live = payload.get("liveweer") or [{}]
    now = valid_temperature(live[0].get("temp")) if isinstance(live[0], dict) else None
    hourly: dict[datetime, float] = {}
    for item in payload.get("uur_verw") or []:
        if not isinstance(item, dict):
            continue
        temp = valid_temperature(item.get("temp"))
        try:
            when = datetime.fromtimestamp(int(item["timestamp"]), tz=dt_util.UTC)
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            continue
        if temp is not None:
            hourly[when.replace(minute=0, second=0, microsecond=0)] = temp
    days: dict[date, tuple[float, float]] = {}
    for item in payload.get("wk_verw") or []:
        if not isinstance(item, dict):
            continue
        try:
            day = datetime.strptime(str(item.get("dag")), "%d-%m-%Y").date()
        except ValueError:
            continue
        low = valid_temperature(item.get("min_temp"))
        high = valid_temperature(item.get("max_temp"))
        if low is not None and high is not None:
            days[day] = (low, high)
    return now, combine(hourly, daily_curve(days))


def weerlive_error(payload: object) -> str | None:
    """Weerlive's own error text (``liveweer[0].fout``), e.g. a wrong key."""
    if isinstance(payload, dict):
        live = payload.get("liveweer") or [{}]
        if isinstance(live[0], dict) and live[0].get("fout"):
            return str(live[0]["fout"])[:200]
    return None


class WeerliveWeatherSource(WeatherSource):
    """The Weerlive API with the user's key and place."""

    key = "weerlive"
    name = "Weerlive (KNMI, direct)"

    def __init__(self, settings=None) -> None:
        """Initialize."""
        super().__init__(settings)
        self._now: float | None = None
        self._cache: dict[datetime, float] = {}
        self._read_at: datetime | None = None
        self._failed = False
        self.requests_left: int | None = None
        self.error: str | None = None

    def location(self, hass: HomeAssistant) -> str:
        """The place asked for: the setting, else home (2 decimals)."""
        if self.settings.location:
            return self.settings.location.strip()
        return f"{hass.config.latitude:.2f},{hass.config.longitude:.2f}"

    def describe(self) -> str:
        """Place and state (never the key)."""
        state = self.error or (
            f"{self.requests_left} requests left today"
            if self.requests_left is not None
            else "not read yet"
        )
        return f"Weerlive ({self.settings.location or 'home'}): {state}"

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
        if not self.settings.api_key:
            self.error = "no API key"
            return self._cache
        try:
            session = async_get_clientsession(hass)
            async with session.get(
                URL,
                params={"key": self.settings.api_key, "locatie": self.location(hass)},
                timeout=TIMEOUT,
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            self._failed = True
            self.error = f"request failed ({type(err).__name__})"
            _LOGGER.debug("Weerlive: %s", err)
            return self._cache
        temperature, forecast = parse_weerlive(payload)
        api = (payload.get("api") or [{}])[0] if isinstance(payload, dict) else {}
        try:
            self.requests_left = int(api.get("rest_verz"))
        except (TypeError, ValueError, AttributeError):
            self.requests_left = None
        if not forecast:
            # e.g. a wrong key: {"liveweer": [{"fout": "Vraag eerst een API-key op ..."}]}
            self._failed = True
            self.error = weerlive_error(payload) or "no forecast in the answer"
            return self._cache
        self._failed = False
        self.error = None
        self._now = temperature
        self._cache = forecast
        return forecast
