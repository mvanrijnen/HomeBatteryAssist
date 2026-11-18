"""Built-in PV forecast source: the Energy dashboard's solar forecast platforms.

Integrations such as Forecast.Solar, Solcast and Open-Meteo Solar Forecast
provide ``<domain>/energy.py`` with ``async_get_solar_forecast``; every loaded
config entry of such an integration is one forecast.
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import HomeAssistant

from .base import PvForecastOption, PvForecastSource
from .energy_dashboard_platform import (
    async_get_pv_forecast,
    async_solar_forecast_entries,
)


class EnergyPlatformSource(PvForecastSource):
    """Solar forecasts of other integrations (Energy dashboard)."""

    key = "energy"
    verified = True
    name = "Solar forecast integrations"

    async def async_find(self, hass: HomeAssistant) -> list[PvForecastOption]:
        return [
            PvForecastOption(entry.entry_id, entry.title)
            for entry in await async_solar_forecast_entries(hass)
        ]

    async def async_read(
        self, hass: HomeAssistant, option_id: str
    ) -> dict[datetime, float]:
        return await async_get_pv_forecast(hass, [option_id])
