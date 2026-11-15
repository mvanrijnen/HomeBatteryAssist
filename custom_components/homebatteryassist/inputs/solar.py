"""PV forecast, read from the Energy dashboard's solar forecast platforms.

Integrations such as Forecast.Solar, Solcast and Open-Meteo Solar Forecast
provide ``<domain>/energy.py`` with ``async_get_solar_forecast``, returning
``{"wh_hours": {iso_timestamp: wh}}`` per hour.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.loader import IntegrationNotFound, async_get_integration

from ..const import DOMAIN
from .units import parse_float, parse_time

_LOGGER = logging.getLogger(__name__)

ENERGY_PLATFORM = "energy"
SOLAR_FORECAST_METHOD = "async_get_solar_forecast"
PV_PERIOD = timedelta(hours=1)


async def _async_solar_forecast_platform(hass: HomeAssistant, domain: str) -> Any:
    try:
        integration = await async_get_integration(hass, domain)
    except IntegrationNotFound:
        return None
    if not integration.platforms_exists((ENERGY_PLATFORM,)):
        return None
    try:
        platform = await integration.async_get_platform(ENERGY_PLATFORM)
    except ImportError:
        return None
    return platform if hasattr(platform, SOLAR_FORECAST_METHOD) else None


async def async_solar_forecast_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """Return loaded config entries that provide a solar forecast."""
    entries = []
    for entry in hass.config_entries.async_entries():
        if entry.domain == DOMAIN or entry.state is not ConfigEntryState.LOADED:
            continue
        if await _async_solar_forecast_platform(hass, entry.domain) is not None:
            entries.append(entry)
    return entries


async def async_get_pv_forecast(
    hass: HomeAssistant, entry_ids: Iterable[str]
) -> dict[datetime, float]:
    """Return the summed solar forecast (Wh per hour start) of the given entries."""
    total: dict[datetime, float] = {}
    for entry_id in entry_ids:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            _LOGGER.debug("PV forecast entry %s is not loaded", entry_id)
            continue
        platform = await _async_solar_forecast_platform(hass, entry.domain)
        if platform is None:
            _LOGGER.debug("%s has no solar forecast platform", entry.domain)
            continue
        try:
            forecast = await getattr(platform, SOLAR_FORECAST_METHOD)(hass, entry_id)
        except Exception:
            _LOGGER.exception("Solar forecast of %s failed", entry.title)
            continue
        for key, wh in ((forecast or {}).get("wh_hours") or {}).items():
            start, value = parse_time(key), parse_float(wh)
            if start is not None and value is not None:
                total[start] = total.get(start, 0.0) + value
    return dict(sorted(total.items()))
