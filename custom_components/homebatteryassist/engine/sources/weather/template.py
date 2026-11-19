"""Template for another weather source — an example, never registered.

Copy it to ``/config/homebatteryassist/weather_sources/<name>.py``, give
``key`` and ``name`` a value and fill in both methods. ``self.settings``
holds what the user set up (``entity_id``, ``api_key``, ``location``). Only
read: a web service, a file, another integration's data. The helpers
``daily_curve`` and ``combine`` turn daily minimum / maximum temperatures
into hourly values after an hourly forecast.
"""

from __future__ import annotations

from datetime import date, datetime

from homeassistant.core import HomeAssistant

# Own modules import from the integration with an absolute import:
from custom_components.homebatteryassist.engine.sources.weather.base import (
    WeatherSource,
    combine,
    daily_curve,
    valid_temperature,
)


class TemplateWeatherSource(WeatherSource):
    """Example weather source: an outdoor sensor plus fixed day values."""

    key = "template"
    name = "Template"

    def temperature_now(self, hass: HomeAssistant) -> float | None:
        """The outdoor temperature now, e.g. from a sensor."""
        state = hass.states.get("sensor.outdoor_temperature")
        return valid_temperature(state.state) if state else None

    async def async_forecast(self, hass: HomeAssistant) -> dict[datetime, float]:
        """°C per UTC clock hour start, e.g. read from a web service."""
        hourly: dict[datetime, float] = {}  # e.g. the next 24 hours
        days: dict[date, tuple[float, float]] = {}  # (minimum, maximum) per day
        return combine(hourly, daily_curve(days))
