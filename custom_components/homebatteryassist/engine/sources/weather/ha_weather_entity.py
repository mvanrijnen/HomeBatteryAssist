"""Weather source: a Home Assistant weather entity (Buienradar, Met.no,
OpenWeatherMap, ...).

The temperature now comes from the entity's ``temperature`` attribute; the
forecast from the ``weather.get_forecasts`` action (hourly, or twice daily /
daily when the integration has no hourly forecast). That action only reads.
Results are cached for ``CACHE``. Temperatures in °F are converted to °C.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from .base import WeatherSource, valid_temperature

_LOGGER = logging.getLogger(__name__)

CACHE = timedelta(minutes=30)
KINDS = ("hourly", "twice_daily", "daily")  # first one the entity supports
STEP = {"hourly": 1, "twice_daily": 12, "daily": 24}  # hours one value covers


def _to_celsius(value: object, unit: str | None) -> float | None:
    """``value`` in ``unit`` as a believable °C, or None."""
    if unit == UnitOfTemperature.FAHRENHEIT:
        try:
            value = TemperatureConverter.convert(
                float(value),  # type: ignore[arg-type]
                UnitOfTemperature.FAHRENHEIT,
                UnitOfTemperature.CELSIUS,
            )
        except (TypeError, ValueError):
            return None
    return valid_temperature(value)


def parse_forecast(
    items: list[dict], kind: str, unit: str | None
) -> dict[datetime, float]:
    """Forecast items -> °C per UTC hour (a daily value covers its hours)."""
    out: dict[datetime, float] = {}
    hours = STEP.get(kind, 1)
    for item in items:
        when = dt_util.parse_datetime(str(item.get("datetime", "")))
        temp = _to_celsius(item.get("temperature"), unit)
        if when is None or temp is None:
            continue
        hour = dt_util.as_utc(when).replace(minute=0, second=0, microsecond=0)
        for i in range(hours):
            out.setdefault(hour + timedelta(hours=i), temp)
    return out


class WeatherEntitySource(WeatherSource):
    """One Home Assistant weather entity."""

    key = "weather_entity"
    name = "Home Assistant weather entity"

    def __init__(self, entity_id: str) -> None:
        """Initialize for ``entity_id`` (weather.*)."""
        self.entity_id = entity_id
        self._cache: dict[datetime, float] = {}
        self._read_at: datetime | None = None

    def _unit(self, hass: HomeAssistant) -> str | None:
        state = hass.states.get(self.entity_id)
        return state.attributes.get("temperature_unit") if state else None

    def temperature_now(self, hass: HomeAssistant) -> float | None:
        """The ``temperature`` attribute of the entity."""
        state = hass.states.get(self.entity_id)
        if state is None:
            return None
        return _to_celsius(state.attributes.get("temperature"), self._unit(hass))

    async def async_forecast(self, hass: HomeAssistant) -> dict[datetime, float]:
        """Hourly forecast (cached); empty when the entity gives none."""
        now = dt_util.utcnow()
        if self._read_at is not None and now - self._read_at < CACHE:
            return self._cache
        self._read_at = now
        for kind in KINDS:
            try:
                response = await hass.services.async_call(
                    "weather",
                    "get_forecasts",
                    {"entity_id": self.entity_id, "type": kind},
                    blocking=True,
                    return_response=True,
                )
            except (HomeAssistantError, ValueError) as err:
                _LOGGER.debug("%s: no %s forecast (%s)", self.entity_id, kind, err)
                continue
            items = ((response or {}).get(self.entity_id) or {}).get("forecast") or []
            if parsed := parse_forecast(items, kind, self._unit(hass)):
                self._cache = parsed
                return parsed
        self._cache = {}
        return self._cache
