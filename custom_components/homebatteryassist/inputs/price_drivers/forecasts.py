"""Forecast-only price drivers: multi-day price predictions, no valid tariffs.

These sources predict the (bare) market price days ahead, but are not the
prices you actually pay. They can only be chosen as the *extra price forecast*
next to a real price source; the published tariffs keep coming from that price
source. Before use, a forecast is put on the level of the price source by
``prices.calibrate`` (fitted on the hours both know).

- EpexPredictor (public API, ``epexpredictor.batzill.com``): ~7 days,
  quarter-hourly, bare EPEX; verified from here for region NL.
- stroomprijsprognose.nl (public API, free for private use): 48 hours, NL, DE,
  BE, DK; verified from here for NL.
- Sensors of forecast integrations (Energy Price Forecast EU, WattWanneer,
  Wattcast, EnerPrice): only offered when their attributes hold future prices;
  not verified.

Read-only: the public APIs are only queried (at most every ``REFRESH``).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .actions import points_from
from .base import ROLE_MARKET, PriceData, PriceDriver, PriceSource
from .sensors import SensorAttributeDriver

_LOGGER = logging.getLogger(__name__)

REFRESH = timedelta(hours=1)


class ApiForecastDriver(PriceDriver):
    """Base for forecast drivers that read a public API, per country."""

    countries: tuple[str, ...] = ()
    days_ahead = 2.0

    def __init__(self) -> None:
        """Initialize the cache: country -> (fetched at, data)."""
        self._cache: dict[str, tuple[datetime, PriceData]] = {}

    def find(self, hass: HomeAssistant) -> list[PriceSource]:
        """One source for the country Home Assistant is set to, if supported."""
        country = (hass.config.country or "").upper()
        if country not in self.countries:
            return []
        return [
            PriceSource(
                self.key,
                country,
                f"{self.name} ({country})",
                frozenset({ROLE_MARKET}),
                self.days_ahead,
                forecast_only=True,
            )
        ]

    async def async_read(
        self, hass: HomeAssistant, source: str, role: str
    ) -> PriceData:
        """The forecast, cached for ``REFRESH``."""
        now = dt_util.utcnow()
        cached = self._cache.get(source)
        if cached and now - cached[0] < REFRESH:
            return cached[1]
        try:
            async with asyncio.timeout(20):
                response = await async_get_clientsession(hass).get(self.url(source))
                response.raise_for_status()
                data = self.parse(await response.json(content_type=None))
        except (TimeoutError, ClientError, KeyError, TypeError, ValueError) as err:
            _LOGGER.debug("%s: no forecast: %s", self.name, err)
            return cached[1] if cached else PriceData([])
        self._cache[source] = (now, data)
        return data

    def url(self, source: str) -> str:
        """The API URL for a country."""
        raise NotImplementedError

    def parse(self, data: dict) -> PriceData:
        """The API response -> prices."""
        raise NotImplementedError


class EpexPredictorDriver(ApiForecastDriver):
    """EpexPredictor: bare EPEX price forecast, about 7 days, per quarter."""

    key = "epexpredictor"
    name = "EpexPredictor"
    verified = True
    countries = ("NL", "DE", "AT", "BE", "SE", "DK")
    days_ahead = 7

    def url(self, source: str) -> str:
        """Bare prices (no surcharge, no tax) in EUR per kWh, 7 days."""
        return (
            "https://epexpredictor.batzill.com/prices"
            f"?region={source}&unit=EUR_PER_KWH&hours=168"
        )

    def parse(self, data: dict) -> PriceData:
        """``{"prices": [{"startsAt", "total"}], "knownUntil"}``."""
        points = points_from((p["startsAt"], None, p["total"]) for p in data["prices"])
        return PriceData(points, "EUR/kWh")


class StroomprijsprognoseDriver(ApiForecastDriver):
    """stroomprijsprognose.nl: price forecast for 48 hours (free plan)."""

    key = "stroomprijsprognose"
    name = "stroomprijsprognose.nl"
    verified = True
    countries = ("NL", "DE", "BE", "DK")

    def url(self, source: str) -> str:
        """Hourly series, 48 hours."""
        return (
            "https://stroomprijsprognose.nl/api/v1/home-assistant/summary"
            f"?market={source}&include_series=true&hours=48"
        )

    def parse(self, data: dict) -> PriceData:
        """``series.price``: ``[{"start", "end", "value", "unit"}]``."""
        series = data["series"]["price"]
        points = points_from((p["start"], p.get("end"), p["value"]) for p in series)
        return PriceData(points, "EUR/kWh")


def _forecast_sensor(key: str, name: str, platform: str) -> SensorAttributeDriver:
    driver = SensorAttributeDriver(
        key, name, platform, frozenset({ROLE_MARKET}), days_ahead=5
    )
    driver.forecast_only = True
    return driver


FORECAST_DRIVERS: tuple[PriceDriver, ...] = (
    EpexPredictorDriver(),
    StroomprijsprognoseDriver(),
    _forecast_sensor(
        "energy_price_forecast", "Energy Price Forecast EU", "energy_price_forecast"
    ),
    _forecast_sensor("wattwanneer", "WattWanneer", "wattwanneer"),
    _forecast_sensor("wattcast", "Wattcast", "wattcast"),
    _forecast_sensor("enerprice", "EnerPrice", "enerprice"),
)
