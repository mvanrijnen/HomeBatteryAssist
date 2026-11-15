"""Periodic collection of the price and PV forecast inputs.

Refreshes every ``FORECAST_UPDATE_INTERVAL`` and when the price sensor changes
(new day-ahead prices). Determines the planning horizon and explains changes of
what limits it in the decision log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

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
from .horizon import Horizon, HorizonLimit, planning_horizon

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ForecastData:
    """Snapshot of the forecast inputs and the resulting planning horizon."""

    horizon: Horizon
    prices: list[PricePoint] = field(default_factory=list)
    price_unit: str | None = None
    pv_wh: dict[datetime, float] = field(default_factory=dict)  # per hour start
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
        prices: list[PricePoint] = []
        price_unit: str | None = None
        pv_wh: dict[datetime, float] = {}

        if self.price_entity:
            state = self.hass.states.get(self.price_entity)
            prices = [p for p in parse_price_forecast(state) if p.end > now]
            price_unit = (
                state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) if state else None
            )
        if self.pv_entries:
            pv_wh = {
                start: wh
                for start, wh in (
                    await async_get_pv_forecast(self.hass, self.pv_entries)
                ).items()
                if start + PV_PERIOD > now
            }

        price_end = prices[-1].end if prices else None
        pv_end = max(pv_wh) + PV_PERIOD if pv_wh else None
        horizon = planning_horizon(
            now,
            self.max_days,
            price_end,
            pv_end,
            price_configured=self.price_entity is not None,
            pv_configured=bool(self.pv_entries),
        )
        _LOGGER.debug(
            "Forecasts: %d price points until %s, %d PV hours until %s -> horizon %s (%s)",
            len(prices),
            price_end,
            len(pv_wh),
            pv_end,
            horizon.end,
            horizon.limited_by,
        )
        self._explain_horizon(horizon)
        return ForecastData(horizon, prices, price_unit, pv_wh, price_end, pv_end)

    def _explain_horizon(self, horizon: Horizon) -> None:
        """Log in the decision log when the limiting factor changes."""
        if horizon.limited_by == self._last_limit:
            return
        self._last_limit = horizon.limited_by
        self._decisions.async_log(
            "planning",
            f"horizon_{horizon.limited_by}",
            end=horizon.end,
            days=self.max_days,
            entity=self.price_entity or "",
        )
