"""Periodic forecast cycle.

Every cycle runs in a fixed order:

1. read the forecast inputs (prices, PV) from other integrations;
2. determine the planning window: how far ahead we can calculate;
3. calculate everything else only within that window.

Refreshes every ``FORECAST_UPDATE_INTERVAL`` and when the price sensor changes
(new day-ahead prices). Changes of what limits the window are explained in the
decision log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_PLANNING_HORIZON,
    CONF_PRICE_FORECAST,
    CONF_PV_FORECAST,
    DEFAULT_PLANNING_HORIZON,
    DOMAIN,
    FORECAST_UPDATE_INTERVAL,
)
from ..explain import DecisionLog
from ..inputs.prices import PricePoint, parse_price_forecast
from ..inputs.solar import PV_PERIOD, async_get_pv_forecast
from .horizon import HorizonLimit, PlanningWindow, planning_horizon

_LOGGER = logging.getLogger(__name__)

EVENT_FORECAST_UPDATED = f"{DOMAIN}_forecast_updated"


@dataclass(slots=True)
class ForecastData:
    """Result of one forecast cycle; all series are limited to ``window``."""

    window: PlanningWindow
    prices: list[PricePoint] = field(default_factory=list)
    price_unit: str | None = None
    pv_wh: dict[datetime, float] = field(default_factory=dict)  # per hour start
    # How far the inputs reach (may be beyond the window).
    price_end: datetime | None = None
    pv_end: datetime | None = None


class ForecastCoordinator(DataUpdateCoordinator[ForecastData]):
    """Collects price and PV forecasts and determines the planning horizon."""

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, decisions: DecisionLog
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} forecasts",
            update_interval=FORECAST_UPDATE_INTERVAL,
        )
        self._decisions = decisions
        options = entry.options
        self.max_days: int = options.get(
            CONF_PLANNING_HORIZON, DEFAULT_PLANNING_HORIZON
        )
        self.price_entity: str | None = options.get(CONF_PRICE_FORECAST) or None
        self.pv_entries: list[str] = list(options.get(CONF_PV_FORECAST) or [])
        self._last_limit: HorizonLimit | None = None

    async def _async_update_data(self) -> ForecastData:
        now = dt_util.utcnow()

        # 1. Inputs
        prices, price_unit = self._read_prices(now)
        pv_wh = await self._async_read_pv(now)
        price_end = prices[-1].end if prices else None
        pv_end = max(pv_wh) + PV_PERIOD if pv_wh else None

        # 2. How far ahead can we calculate?
        window = planning_horizon(
            now,
            self.max_days,
            price_end,
            pv_end,
            price_configured=self.price_entity is not None,
            pv_configured=bool(self.pv_entries),
        )
        self._explain_window(window)

        # 3. Everything else only within the window.
        prices = [p for p in prices if window.overlaps(p.start, p.end)]
        pv_wh = {
            start: wh
            for start, wh in pv_wh.items()
            if window.overlaps(start, start + PV_PERIOD)
        }

        _LOGGER.debug(
            "Inputs: prices until %s, PV until %s -> window %s - %s (%.1f h, %s); "
            "%d price points and %d PV hours in window",
            price_end,
            pv_end,
            window.start,
            window.end,
            window.hours,
            window.limited_by,
            len(prices),
            len(pv_wh),
        )
        data = ForecastData(window, prices, price_unit, pv_wh, price_end, pv_end)
        self.hass.bus.async_fire(EVENT_FORECAST_UPDATED, summarise(data))
        return data

    def summary(self) -> dict[str, Any]:
        """Short description of the latest result (action response, event)."""
        return summarise(self.data)

    def _read_prices(self, now: datetime) -> tuple[list[PricePoint], str | None]:
        if not self.price_entity:
            return [], None
        state = self.hass.states.get(self.price_entity)
        prices = [p for p in parse_price_forecast(state) if p.end > now]
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) if state else None
        return prices, unit

    async def _async_read_pv(self, now: datetime) -> dict[datetime, float]:
        if not self.pv_entries:
            return {}
        forecast = await async_get_pv_forecast(self.hass, self.pv_entries)
        return {start: wh for start, wh in forecast.items() if start + PV_PERIOD > now}

    def _explain_window(self, window: PlanningWindow) -> None:
        """Log in the decision log when the limiting factor changes."""
        if window.limited_by == self._last_limit:
            return
        self._last_limit = window.limited_by
        self._decisions.async_log(
            "planning",
            f"horizon_{window.limited_by}",
            end=window.end,
            hours=round(window.hours),
            days=self.max_days,
            entity=self.price_entity or "",
        )


def summarise(data: ForecastData) -> dict[str, Any]:
    """JSON-friendly summary of a forecast cycle."""
    window = data.window
    return {
        "window_start": window.start.isoformat(),
        "window_end": window.end.isoformat(),
        "hours_ahead": round(window.hours, 1),
        "limited_by": window.limited_by.value,
        "price_points": len(data.prices),
        "pv_hours": len(data.pv_wh),
    }
