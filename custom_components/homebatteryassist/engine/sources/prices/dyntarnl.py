"""DynTarNL (HACS, mvanrijnen/ha-dyntarNL): Dutch supplier prices plus forecast.

Verified on a real installation. Per config entry the integration has, among
others (recognised by the end of their unique id):

- ``…_electricity_forecast_total_avg_24h``: attribute ``prices`` with
  ``[epoch ms, all-in price, "p"|"f"]`` (published, then forecast up to ~7 days)
  and ``forecast_market`` with the bare market price forecast;
- ``…_electricity_market_market_current``: attribute ``prices`` with the
  published bare market prices (yesterday, today, tomorrow).

- ``…_electricity_feedin_compensation_now`` (export price now, DynTarNL >= 1.2.0):
  attribute ``prices`` with the published export prices (market minus the
  supplier's purchase fee, may be negative); the forecast sensor then has
  ``forecast_export`` with the forecast export prices (only after the last
  published hour; only when DynTarNL's forecasts are on).

Roles: ``import`` (all-in), ``market`` (bare, published + forecast) and
``export``: what exported energy earns on a dynamic contract. Read from the
export price sensor and ``forecast_export`` when there (recognised by the
attribute, not the version); otherwise (DynTarNL < 1.2.0) calculated as the
market price minus the ``purchase_fee`` of the market sensor.
"""

from __future__ import annotations

from dataclasses import replace

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .base import (
    ROLE_EXPORT,
    ROLE_IMPORT,
    ROLE_MARKET,
    PriceData,
    PriceDriver,
    PriceSource,
)
from .price_points import (
    MARKET_ATTRIBUTES,
    PricePoint,
    merge_price_forecasts,
    parse_price_forecast,
)

DOMAIN = "dyntarnl"
FORECAST_SUFFIX = "_electricity_forecast_total_avg_24h"
MARKET_SUFFIX = "_electricity_market_market_current"
EXPORT_SUFFIX = "_electricity_feedin_compensation_now"


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
                frozenset({ROLE_IMPORT, ROLE_MARKET, ROLE_EXPORT}),
                7,
            )
            for entry in hass.config_entries.async_entries(DOMAIN)
            if _entity(hass, entry.entry_id, FORECAST_SUFFIX)
        ]

    async def async_read(
        self, hass: HomeAssistant, source: str, role: str
    ) -> PriceData:
        """All-in prices, bare market prices (published, then forecast) or
        export prices (market minus the purchase fee)."""
        forecast = hass.states.get(_entity(hass, source, FORECAST_SUFFIX) or "")
        unit = forecast.attributes.get(ATTR_UNIT_OF_MEASUREMENT) if forecast else None
        if role in (ROLE_MARKET, ROLE_EXPORT):
            market = hass.states.get(_entity(hass, source, MARKET_SUFFIX) or "")
            points = merge_price_forecasts(
                [
                    parse_price_forecast(market),
                    parse_price_forecast(forecast, MARKET_ATTRIBUTES),
                ]
            )
            if role == ROLE_EXPORT:
                export = hass.states.get(_entity(hass, source, EXPORT_SUFFIX) or "")
                published = export_prices(export, forecast)
                if published is not None:
                    return PriceData(published, unit)
                points = _minus_fee(points, purchase_fee(market))
            return PriceData(points, unit)
        return PriceData(parse_price_forecast(forecast, ("prices",)), unit)

    def watch(self, hass: HomeAssistant, source: str) -> list[str]:
        """New prices arrive as attribute updates of these sensors."""
        return [
            e
            for e in (
                _entity(hass, source, FORECAST_SUFFIX),
                _entity(hass, source, MARKET_SUFFIX),
                _entity(hass, source, EXPORT_SUFFIX),
            )
            if e
        ]


def purchase_fee(state) -> float:
    """The supplier's purchase fee per kWh (0 when unknown or nonsense)."""
    try:
        fee = float(state.attributes.get("purchase_fee")) if state else 0.0
    except (TypeError, ValueError):
        return 0.0
    return fee if 0.0 <= fee < 1.0 else 0.0


def _minus_fee(points: list[PricePoint], fee: float) -> list[PricePoint]:
    return [replace(p, price=round(p.price - fee, 5)) for p in points]


def export_prices(export, forecast) -> list[PricePoint] | None:
    """The export prices of DynTarNL >= 1.2.0: the published ones (attribute
    ``prices`` of the export price sensor), then the forecast ones
    (``forecast_export``) after the last published hour. Negative prices are
    kept (exporting costs money then). ``None`` when the export sensor has no
    ``prices`` (an older DynTarNL, or no data yet): calculate it instead."""
    if export is None or not export.attributes.get("prices"):
        return None
    published = parse_price_forecast(export, ("prices",))
    if not published:
        return None
    last = published[-1].end
    predicted = [
        replace(p, estimated=True)
        for p in parse_price_forecast(forecast, ("forecast_export",))
        if p.start >= last
    ]
    return merge_price_forecasts([published, predicted])
