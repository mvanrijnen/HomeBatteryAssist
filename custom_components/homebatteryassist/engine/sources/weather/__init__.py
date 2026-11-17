"""Weather sources: the outdoor temperature now and forecast (optional).

Used by the consumption forecast for houses that heat or cool with
electricity (``engine/forecast/temperature_effect.py``). Built-in:
``ha_weather_entity.py`` (any Home Assistant weather entity). ``template.py``
shows how to write another source; it is never registered.
"""

from __future__ import annotations

from .base import MAX_C, MIN_C, WeatherSource, valid_indoor, valid_temperature
from .ha_weather_entity import WeatherEntitySource

__all__ = [
    "MAX_C",
    "MIN_C",
    "WeatherEntitySource",
    "WeatherSource",
    "valid_indoor",
    "valid_temperature",
]
