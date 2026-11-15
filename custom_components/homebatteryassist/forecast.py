"""Price and PV forecasts from other integrations, and the planning horizon.

HomeBatteryAssist does not make these forecasts itself:

- Prices are read from the attributes of a sensor entity. There is no Home
  Assistant standard, so the common attribute formats are recognised (lists of
  ``{start, price}``-like dicts, or ``{timestamp: price}`` mappings), as used by
  e.g. Nordpool, ENTSO-e and Frank Energie.
- PV production is read through the Energy dashboard's solar forecast platform
  (``energy.py`` with ``async_get_solar_forecast``), which Forecast.Solar,
  Solcast, Open-Meteo Solar Forecast and others implement.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.loader import IntegrationNotFound, async_get_integration
from homeassistant.util import dt as dt_util

from .const import (
    CONF_PLANNING_HORIZON,
    CONF_PRICE_FORECAST,
    CONF_PV_FORECAST,
    DEFAULT_PLANNING_HORIZON,
    DOMAIN,
    FORECAST_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

ENERGY_PLATFORM = "energy"
SOLAR_FORECAST_METHOD = "async_get_solar_forecast"
PV_PERIOD = timedelta(hours=1)  # solar forecast platforms report Wh per hour

# Attribute names that commonly hold price forecast lists / mappings.
PRICE_ATTRIBUTES = (
    "prices",
    "prices_today",
    "prices_tomorrow",
    "raw_today",
    "raw_tomorrow",
    "today",
    "tomorrow",
    "forecast",
    "data",
)
START_KEYS = (
    "start",
    "start_time",
    "starts_at",
    "startsAt",
    "from",
    "time",
    "datetime",
)
END_KEYS = ("end", "end_time", "ends_at", "endsAt", "till", "until", "to")
PRICE_KEYS = ("price", "value", "total", "electricity_price", "price_per_kwh")


@dataclass(frozen=True, slots=True)
class PricePoint:
    """Price for one period, in the unit of the source sensor."""

    start: datetime
    end: datetime
    price: float


@dataclass(slots=True)
class ForecastData:
    """Snapshot of the forecasts and the resulting planning horizon."""

    prices: list[PricePoint] = field(default_factory=list)
    price_unit: str | None = None
    pv_wh: dict[datetime, float] = field(default_factory=dict)  # per hour start
    price_end: datetime | None = None
    pv_end: datetime | None = None
    horizon_end: datetime | None = None


# ---------------------------------------------------------------------------
# Price parsing


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return dt_util.as_utc(value) if value.tzinfo else None
    if isinstance(value, str):
        parsed = dt_util.parse_datetime(value)
        if parsed is not None and parsed.tzinfo is not None:
            return dt_util.as_utc(parsed)
    return None


def _parse_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(item: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in item:
            return item[key]
    return None


def _raw_points(value: Any) -> list[tuple[datetime, datetime | None, float]]:
    """Extract (start, end or None, price) from one attribute value."""
    points: list[tuple[datetime, datetime | None, float]] = []
    if isinstance(value, Mapping):
        for key, raw_price in value.items():
            start, price = _parse_time(key), _parse_float(raw_price)
            if start is not None and price is not None:
                points.append((start, None, price))
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, Mapping):
                continue
            start = _parse_time(_first(item, START_KEYS))
            price = _parse_float(_first(item, PRICE_KEYS))
            if start is not None and price is not None:
                points.append((start, _parse_time(_first(item, END_KEYS)), price))
    return points


def parse_price_forecast(state: State | None) -> list[PricePoint]:
    """Return the price forecast found in the attributes of ``state``, sorted.

    Periods without an explicit end last until the next period starts; the last
    one gets the length of the period before it (or one hour).
    """
    if state is None:
        return []
    raw: dict[datetime, tuple[datetime | None, float]] = {}
    for attribute in PRICE_ATTRIBUTES:
        for start, end, price in _raw_points(state.attributes.get(attribute)):
            raw.setdefault(start, (end, price))

    starts = sorted(raw)
    points: list[PricePoint] = []
    for index, start in enumerate(starts):
        end, price = raw[start]
        if end is None:
            if index + 1 < len(starts):
                end = starts[index + 1]
            elif index > 0:
                end = start + (start - starts[index - 1])
            else:
                end = start + timedelta(hours=1)
        points.append(PricePoint(start, end, price))
    return points


# ---------------------------------------------------------------------------
# PV forecast (Energy dashboard solar forecast platforms)


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
    """Return the summed solar forecast (Wh per hour) of the given entries."""
    total: dict[datetime, float] = {}
    for entry_id in entry_ids:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            continue
        platform = await _async_solar_forecast_platform(hass, entry.domain)
        if platform is None:
            continue
        try:
            forecast = await getattr(platform, SOLAR_FORECAST_METHOD)(hass, entry_id)
        except Exception:
            _LOGGER.exception("Solar forecast of %s failed", entry.title)
            continue
        for key, wh in ((forecast or {}).get("wh_hours") or {}).items():
            start, value = _parse_time(key), _parse_float(wh)
            if start is not None and value is not None:
                total[start] = total.get(start, 0.0) + value
    return dict(sorted(total.items()))


# ---------------------------------------------------------------------------
# Horizon


def planning_horizon_end(
    now: datetime,
    max_days: int,
    price_end: datetime | None,
    pv_end: datetime | None,
    *,
    price_configured: bool,
    pv_configured: bool,
) -> datetime:
    """Effective planning horizon: the configured maximum, limited by forecasts.

    A configured forecast that has no data limits the horizon to ``now``.
    """
    end = now + timedelta(days=max_days)
    for configured, forecast_end in (
        (price_configured, price_end),
        (pv_configured, pv_end),
    ):
        if configured:
            end = min(end, max(forecast_end or now, now))
    return end


class ForecastCoordinator(DataUpdateCoordinator[ForecastData]):
    """Periodically collects price and PV forecasts."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} forecasts",
            update_interval=FORECAST_UPDATE_INTERVAL,
        )
        options = entry.options
        self.max_days: int = options.get(
            CONF_PLANNING_HORIZON, DEFAULT_PLANNING_HORIZON
        )
        self.price_entity: str | None = options.get(CONF_PRICE_FORECAST) or None
        self.pv_entries: list[str] = list(options.get(CONF_PV_FORECAST) or [])

    async def _async_update_data(self) -> ForecastData:
        now = dt_util.utcnow()
        data = ForecastData()

        if self.price_entity:
            state = self.hass.states.get(self.price_entity)
            data.prices = [p for p in parse_price_forecast(state) if p.end > now]
            data.price_unit = (
                state.attributes.get("unit_of_measurement") if state else None
            )
            data.price_end = data.prices[-1].end if data.prices else None

        if self.pv_entries:
            data.pv_wh = {
                start: wh
                for start, wh in (
                    await async_get_pv_forecast(self.hass, self.pv_entries)
                ).items()
                if start + PV_PERIOD > now
            }
            data.pv_end = max(data.pv_wh) + PV_PERIOD if data.pv_wh else None

        data.horizon_end = planning_horizon_end(
            now,
            self.max_days,
            data.price_end,
            data.pv_end,
            price_configured=self.price_entity is not None,
            pv_configured=bool(self.pv_entries),
        )
        return data
