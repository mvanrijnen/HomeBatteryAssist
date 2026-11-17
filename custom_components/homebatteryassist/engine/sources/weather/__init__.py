"""Weather source modules: the outdoor temperature now and forecast (optional).

Used by the consumption forecast for houses that heat or cool with
electricity (``engine/forecast/temperature_effect.py``). Built-in:

- ``weather_entity`` (``ha_weather_entity.py``): any Home Assistant weather
  entity (Buienradar, Met.no, OpenWeatherMap, ...);
- ``knmi`` (``knmi_integration.py``): the KNMI integration (golles/ha-knmi),
  its weather entity found by itself;
- ``weerlive`` (``weerlive_api.py``): the Weerlive API directly, with an
  API key;
- ``open_meteo`` / ``open_meteo_knmi`` (``open_meteo.py``): Open-Meteo
  directly, no key needed (best model / the KNMI models).

Own sources are Python files in ``/config/homebatteryassist/weather_sources/``
(see ``template.py``), keyed ``custom_<key>``. HomeBatteryAssist checks every
forecast (``checked_forecast``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

from ...own_modules import async_load_modules, load_modules_from
from .base import (
    MAX_C,
    MIN_C,
    WeatherSettings,
    WeatherSource,
    checked_forecast,
    combine,
    daily_curve,
    valid_indoor,
    valid_temperature,
)
from .ha_weather_entity import WeatherEntitySource
from .knmi_integration import KnmiWeatherSource
from .open_meteo import OpenMeteoKnmiSource, OpenMeteoWeatherSource
from .weerlive_api import WeerliveWeatherSource

_LOGGER = logging.getLogger(__name__)

KIND = "weather_sources"
DEFAULT_WEATHER_SOURCE = WeatherEntitySource.key
BUILTIN: dict[str, type[WeatherSource]] = {
    c.key: c
    for c in (
        WeatherEntitySource,
        KnmiWeatherSource,
        WeerliveWeatherSource,
        OpenMeteoWeatherSource,
        OpenMeteoKnmiSource,
    )
}

__all__ = [
    "BUILTIN",
    "DEFAULT_WEATHER_SOURCE",
    "MAX_C",
    "MIN_C",
    "KnmiWeatherSource",
    "OpenMeteoKnmiSource",
    "OpenMeteoWeatherSource",
    "WeatherEntitySource",
    "WeatherSettings",
    "WeatherSource",
    "WeerliveWeatherSource",
    "async_load_user_weather_sources",
    "checked_forecast",
    "combine",
    "create_weather_source",
    "daily_curve",
    "load_weather_sources_from",
    "valid_indoor",
    "valid_temperature",
]


def _usable(found: dict[str, WeatherSource]) -> dict[str, type[WeatherSource]]:
    return {
        k: type(s)
        for k, s in found.items()
        if type(s).async_forecast is not WeatherSource.async_forecast
    }


def load_weather_sources_from(folder: Path) -> dict[str, type[WeatherSource]]:
    """Weather sources defined in the Python files of ``folder`` (blocking)."""
    return _usable(load_modules_from(folder, WeatherSource, KIND))


async def async_load_user_weather_sources(
    hass: HomeAssistant,
) -> dict[str, type[WeatherSource]]:
    """The user's own sources from ``/config/homebatteryassist/weather_sources``."""
    return _usable(await async_load_modules(hass, KIND, WeatherSource))


def create_weather_source(
    key: str | None,
    own: dict[str, type[WeatherSource]],
    settings: WeatherSettings,
) -> WeatherSource | None:
    """The chosen source with the user's settings; ``None`` when it is not
    set up (a weather entity source without an entity, Weerlive without a
    key) or gone (an own module removed: logged)."""
    key = key or DEFAULT_WEATHER_SOURCE
    cls = BUILTIN.get(key) or own.get(key)
    if cls is None:
        _LOGGER.warning("Weather source %s not found; no weather used", key)
        return None
    if cls is WeatherEntitySource and not settings.entity_id:
        return None
    if cls is WeerliveWeatherSource and not settings.api_key:
        return None
    try:
        return cls(settings)
    except Exception:  # an own module may fail in any way
        _LOGGER.exception("Weather source %s could not be created", key)
        return None
