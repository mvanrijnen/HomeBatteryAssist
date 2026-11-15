"""Periodic forecast cycle.

Every cycle runs in a fixed order:

1. read the forecast inputs (prices, PV) from other integrations;
2. determine the planning window: how far ahead we can calculate;
3. check earlier predictions against what really happened (consumption, PV,
   prices) and update the running accuracy;
4. calculate everything else only within the window, with the learned (or
   user-set) corrections: prices, PV and the house consumption forecast;
5. remember the raw predictions, to check them later.

Refreshes every configured forecast interval (5/15/30/60 min, default 15), on
the recalculate action/button, and when the price sensor changes
(new day-ahead prices). Changes of what limits the window are explained in the
decision log.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_FORECAST_INTERVAL,
    CONF_PLANNING_HORIZON,
    CONF_PRICE_FORECAST,
    CONF_PV_FORECAST,
    DEFAULT_FORECAST_INTERVAL,
    DEFAULT_PLANNING_HORIZON,
    DOMAIN,
)
from ..explain import DecisionLog
from ..history.consumption import ConsumptionHistory
from ..inputs.prices import PricePoint, parse_price_forecast
from ..inputs.solar import PV_PERIOD, async_get_pv_forecast
from .accuracy import KINDS, ForecastAccuracy
from .adjustments import AdjustmentStore
from .consumption import ForecastSlot, forecast_consumption
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
    # Expected PV production in the current hour (average W), if forecast.
    pv_now_w: float | None = None
    # Expected house consumption per slot (history interval) within the window.
    consumption: list[ForecastSlot] = field(default_factory=list)

    @property
    def consumption_method(self) -> str | None:
        """Most used forecast method in the window."""
        methods = Counter(slot.method for slot in self.consumption)
        return methods.most_common(1)[0][0] if methods else None

    def consumption_at(self, when: datetime) -> ForecastSlot | None:
        """The forecast slot containing ``when``."""
        return next((s for s in self.consumption if s.start <= when < s.end), None)


class ForecastCoordinator(DataUpdateCoordinator[ForecastData]):
    """Collects price and PV forecasts and determines the planning horizon."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        decisions: DecisionLog,
        history: ConsumptionHistory,
        adjustments: AdjustmentStore,
        accuracy: ForecastAccuracy,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} forecasts",
            update_interval=timedelta(
                minutes=entry.options.get(
                    CONF_FORECAST_INTERVAL, DEFAULT_FORECAST_INTERVAL
                )
            ),
        )
        self._decisions = decisions
        self.history = history
        self.adjustments = adjustments
        self.accuracy = accuracy
        self._last_method: str | None = None
        self._last_corrections: dict[str, str] = {}
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
        hour = now.replace(minute=0, second=0, microsecond=0)
        pv_now_w = pv_wh.get(hour) if self.pv_entries else None

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

        # 3. Check earlier predictions; update the running accuracy.
        accuracy = self.accuracy
        accuracy.evaluate_consumption(self.history.records)
        accuracy.evaluate_pv(self.history.records)
        accuracy.evaluate_prices(
            {p.start.isoformat(): p.price for p in prices if not p.estimated}
        )
        accuracy.prune(now)
        accuracy.refresh_stats(now)
        self._explain_corrections(now)

        # 5 (inputs). Remember the raw predictions of prices and PV.
        accuracy.record(
            "price", [(p.start, p.end, p.price) for p in prices if p.estimated], now
        )
        accuracy.record(
            "pv", [(start, start + PV_PERIOD, wh) for start, wh in pv_wh.items()], now
        )

        # 4. Everything else only within the window, corrected.
        prices = [
            PricePoint(
                p.start,
                p.end,
                round(accuracy.correct("price", p.price, p.start, now), 5),
                p.estimated,
            )
            if p.estimated
            else p
            for p in prices
            if window.overlaps(p.start, p.end)
        ]
        pv_wh = {
            start: round(accuracy.correct("pv", wh, start, now), 1)
            for start, wh in pv_wh.items()
            if window.overlaps(start, start + PV_PERIOD)
        }
        if self.pv_entries:
            pv_now_w = pv_wh.get(hour)

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
        self.adjustments.prune(now)
        consumption = forecast_consumption(
            self.history.records,
            window,
            timedelta(minutes=self.history.minutes),
            self.adjustments.items,
            now,
            lambda value, start: accuracy.correct("consumption", value, start, now),
        )
        data = ForecastData(
            window, prices, price_unit, pv_wh, price_end, pv_end, pv_now_w, consumption
        )
        self._explain_method(data)

        # 5. Remember the raw consumption predictions.
        accuracy.record(
            "consumption", [(s.start, s.end, s.raw) for s in consumption], now
        )
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

    def _explain_corrections(self, now: datetime) -> None:
        """Explain when the correction of a forecast changes noticeably."""
        for kind in KINDS:
            mode = self.accuracy.mode(kind, now)
            stats = self.accuracy.headline(kind)
            correction = self.accuracy.correction_for(kind, "6-24h", now)
            if (
                mode == "off"
                or correction is None
                or stats is None
                or (mode == "learned" and stats.strength < 1)
            ):
                text = "none"
            elif kind == "pv":
                text = f"x{correction:.2f}"
            elif kind == "price":
                text = f"{correction:+.3f}"
            else:
                text = f"{round(correction / 10) * 10:+.0f} W"
            if self._last_corrections.get(kind) == text:
                continue
            first = kind not in self._last_corrections
            self._last_corrections[kind] = text
            if first and text == "none":
                continue  # nothing to explain at start-up
            self._decisions.async_log(
                "forecast",
                f"correction_{kind}" if text != "none" else "correction_none",
                kind=kind,
                mode=mode,
                correction=text,
                samples=stats.samples if stats else 0,
            )

    def _explain_method(self, data: ForecastData) -> None:
        """Explain on which history the consumption forecast is based."""
        method = data.consumption_method or "none"
        if method == self._last_method:
            return
        self._last_method = method
        self._decisions.async_log(
            "forecast",
            f"consumption_method_{method}",
            days=round(
                sum(r["minutes"] * r["coverage"] for r in self.history.records) / 1440
            ),
        )

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
        "price_points_estimated": sum(p.estimated for p in data.prices),
        "pv_hours": len(data.pv_wh),
        "consumption_slots": len(data.consumption),
        "consumption_kwh": round(
            sum(
                s.power_w * (s.end - s.start).total_seconds() / 3_600_000
                for s in data.consumption
            ),
            2,
        ),
        "consumption_method": data.consumption_method,
    }
