"""Weather source: the KNMI integration (HACS, golles/ha-knmi).

Weather data of the KNMI via Weerlive.nl, as a Home Assistant weather entity
with an hourly forecast (24 hours) and a daily one (5 days, minimum and
maximum). Verified on a real installation.

Reads that entity like any weather entity (``weather.get_forecasts``, read
only); this source finds it by itself: the chosen weather entity when it
belongs to the KNMI integration, otherwise the first KNMI weather entity.
The KNMI integration polls Weerlive with its own API key; HomeBatteryAssist
adds no requests of its own.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .ha_weather_entity import WeatherEntitySource

PLATFORM = "knmi"


def knmi_entities(hass: HomeAssistant) -> list[str]:
    """The weather entities of the KNMI integration."""
    registry = er.async_get(hass)
    return sorted(
        e.entity_id
        for e in registry.entities.values()
        if e.platform == PLATFORM and e.domain == "weather" and not e.disabled
    )


class KnmiWeatherSource(WeatherEntitySource):
    """The weather entity of the KNMI integration."""

    key = "knmi"
    name = "KNMI (integration)"

    def __init__(self, settings=None) -> None:
        """Initialize."""
        super().__init__(settings)
        self._found: str | None = None

    def _entity(self, hass: HomeAssistant) -> str | None:
        found = knmi_entities(hass)
        chosen = self.settings.entity_id
        self._found = chosen if chosen in found else (found[0] if found else None)
        return self._found

    def describe(self) -> str:
        """The KNMI weather entity found."""
        return self._found or "KNMI: no weather entity found"
