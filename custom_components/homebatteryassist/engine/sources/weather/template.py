"""Template for another weather source — an example, never registered.

Copy it, give ``key`` and ``name`` a value and fill in both methods. Only
read: a web service, a file, another integration's data.
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import HomeAssistant

from .base import WeatherSource, valid_temperature


class TemplateWeatherSource(WeatherSource):
    """Example weather source."""

    key = "template"
    name = "Template"

    def temperature_now(self, hass: HomeAssistant) -> float | None:
        """The outdoor temperature now, e.g. from a sensor."""
        state = hass.states.get("sensor.outdoor_temperature")
        return valid_temperature(state.state) if state else None

    async def async_forecast(self, hass: HomeAssistant) -> dict[datetime, float]:
        """°C per UTC clock hour start, e.g. read from a web service."""
        return {}
