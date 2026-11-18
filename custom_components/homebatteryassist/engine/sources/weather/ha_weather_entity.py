"""Weather source: a Home Assistant weather entity (Buienradar, Met.no,
OpenWeatherMap, KNMI, ...).

The temperature now comes from the entity's ``temperature`` attribute; the
forecast from the ``weather.get_forecasts`` action: the hourly forecast
(often only 24 to 48 hours), then the daily one as a daily curve (minimum
early morning, maximum mid afternoon) so it reaches as far as the planning;
twice daily when there is no daily forecast. That action only reads. Results
are cached for ``CACHE``. Temperatures in °F are converted to °C.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from .base import (
    WeatherSettings,
    WeatherSource,
    combine,
    daily_curve,
    valid_temperature,
)

_LOGGER = logging.getLogger(__name__)

CACHE = timedelta(minutes=30)
KINDS = ("hourly", "daily", "twice_daily")
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


def parse_days(items: list[dict], unit: str | None) -> dict[date, tuple[float, float]]:
    """Daily items -> (minimum, maximum) per local day; without ``templow``
    the day's temperature counts for both."""
    days: dict[date, tuple[float, float]] = {}
    for item in items:
        when = dt_util.parse_datetime(str(item.get("datetime", "")))
        high = _to_celsius(item.get("temperature"), unit)
        if when is None or high is None:
            continue
        low = _to_celsius(item.get("templow"), unit)
        days.setdefault(
            dt_util.as_local(when).date(), (low if low is not None else high, high)
        )
    return days


class WeatherEntitySource(WeatherSource):
    """One Home Assistant weather entity (``settings.entity_id``)."""

    key = "weather_entity"
    verified = False
    name = "Home Assistant weather entity"

    def __init__(self, settings: WeatherSettings | str | None = None) -> None:
        """Initialize; a plain entity id is accepted too."""
        if isinstance(settings, str):
            settings = WeatherSettings(entity_id=settings)
        super().__init__(settings)
        self._cache: dict[datetime, float] = {}
        self._read_at: datetime | None = None

    @property
    def entity_id(self) -> str | None:
        """The weather entity read."""
        return self.settings.entity_id

    def describe(self) -> str:
        """The entity id."""
        return self.entity_id or "-"

    def _entity(self, hass: HomeAssistant) -> str | None:
        """The entity to read (subclasses may find one themselves)."""
        return self.entity_id

    def _unit(self, hass: HomeAssistant, entity_id: str) -> str | None:
        state = hass.states.get(entity_id)
        return state.attributes.get("temperature_unit") if state else None

    def temperature_now(self, hass: HomeAssistant) -> float | None:
        """The ``temperature`` attribute of the entity."""
        entity_id = self._entity(hass)
        state = hass.states.get(entity_id) if entity_id else None
        if state is None:
            return None
        return _to_celsius(
            state.attributes.get("temperature"), self._unit(hass, entity_id)
        )

    async def _async_items(
        self, hass: HomeAssistant, entity_id: str, kind: str
    ) -> list[dict]:
        try:
            response = await hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity_id, "type": kind},
                blocking=True,
                return_response=True,
            )
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.debug("%s: no %s forecast (%s)", entity_id, kind, err)
            return []
        return ((response or {}).get(entity_id) or {}).get("forecast") or []

    async def async_forecast(self, hass: HomeAssistant) -> dict[datetime, float]:
        """Hourly, then daily (cached); empty when the entity gives none."""
        now = dt_util.utcnow()
        if self._read_at is not None and now - self._read_at < CACHE:
            return self._cache
        self._read_at = now
        entity_id = self._entity(hass)
        if not entity_id:
            self._cache = {}
            return self._cache
        unit = self._unit(hass, entity_id)
        hourly = parse_forecast(
            await self._async_items(hass, entity_id, "hourly"), "hourly", unit
        )
        daily = daily_curve(
            parse_days(await self._async_items(hass, entity_id, "daily"), unit)
        )
        if not daily:
            daily = parse_forecast(
                await self._async_items(hass, entity_id, "twice_daily"),
                "twice_daily",
                unit,
            )
        self._cache = combine(hourly, daily)
        return self._cache
