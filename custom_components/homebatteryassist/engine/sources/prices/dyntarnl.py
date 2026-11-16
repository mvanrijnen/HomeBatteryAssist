"""DynTarNL (HACS, mvanrijnen/ha-dyntarNL): Dutch supplier prices plus forecast.

Verified on a real installation. Per config entry the integration has, among
others (recognised by the end of their unique id):

- ``…_electricity_forecast_total_avg_24h``: attribute ``prices`` with
  ``[epoch ms, all-in price, "p"|"f"]`` (published, then forecast up to ~7 days)
  and ``forecast_market`` with the bare market price forecast;
- ``…_electricity_market_market_current``: attribute ``prices`` with the
  published bare market prices (yesterday, today, tomorrow).

Roles: ``import`` (all-in) and ``market`` (bare, published + forecast).
"""

from __future__ import annotations

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .base import ROLE_IMPORT, ROLE_MARKET, PriceData, PriceDriver, PriceSource
from .points import (
    MARKET_ATTRIBUTES,
    merge_price_forecasts,
    parse_price_forecast,
)

DOMAIN = "dyntarnl"
FORECAST_SUFFIX = "_electricity_forecast_total_avg_24h"
MARKET_SUFFIX = "_electricity_market_market_current"


def _entity(hass: HomeAssistant, entry_id: str, suffix: str) -> str | None:
    registry = er.async_get(hass)
    return next(
        (
            e.entity_id
            for e in er.async_entries_for_config_entry(registry, entry_id)
            if e.domain == "sensor" and e.unique_id.endswith(suffix)
        ),
        None,
    )


class DynTarNLDriver(PriceDriver):
    """All-in and bare market prices of DynTarNL, with its multi-day forecast."""

    key = DOMAIN
    name = "DynTarNL"
    verified = True

    def find(self, hass: HomeAssistant) -> list[PriceSource]:
        """One source per DynTarNL entry that has the forecast sensor."""
        return [
            PriceSource(
                self.key,
                entry.entry_id,
                f"{self.name}: {entry.title}",
                frozenset({ROLE_IMPORT, ROLE_MARKET}),
                7,
            )
            for entry in hass.config_entries.async_entries(DOMAIN)
            if _entity(hass, entry.entry_id, FORECAST_SUFFIX)
        ]

    async def async_read(
        self, hass: HomeAssistant, source: str, role: str
    ) -> PriceData:
        """All-in prices, or bare market prices (published, then forecast)."""
        forecast = hass.states.get(_entity(hass, source, FORECAST_SUFFIX) or "")
        unit = forecast.attributes.get(ATTR_UNIT_OF_MEASUREMENT) if forecast else None
        if role == ROLE_MARKET:
            market = hass.states.get(_entity(hass, source, MARKET_SUFFIX) or "")
            return PriceData(
                merge_price_forecasts(
                    [
                        parse_price_forecast(market),
                        parse_price_forecast(forecast, MARKET_ATTRIBUTES),
                    ]
                ),
                unit,
            )
        return PriceData(parse_price_forecast(forecast, ("prices",)), unit)

    def watch(self, hass: HomeAssistant, source: str) -> list[str]:
        """New prices arrive as attribute updates of these sensors."""
        return [
            e
            for e in (
                _entity(hass, source, FORECAST_SUFFIX),
                _entity(hass, source, MARKET_SUFFIX),
            )
            if e
        ]
