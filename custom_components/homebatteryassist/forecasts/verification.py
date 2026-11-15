"""Checking the consumption forecast afterwards against what really happened.

For every slot the forecast keeps two predictions:

- ``latest``: the last prediction made before the slot started;
- ``day_ahead``: the last prediction made at least ``DAY_AHEAD`` before it.

Once the slot has been measured (an own history record, not an imported one,
with enough coverage), predictions and measurement are compared. Results are
kept for ``RETENTION`` and summarised as mean absolute error, bias and MAPE.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ..const import DOMAIN
from ..history.consumption import ConsumptionRecord
from .consumption import ForecastSlot

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY = 60
DAY_AHEAD = timedelta(hours=12)
RETENTION = timedelta(days=28)
MIN_COVERAGE = 0.8
SUMMARY_PERIOD = timedelta(days=7)


class Prediction(TypedDict, total=False):
    """Predictions for one slot, keyed by slot start."""

    latest: float
    day_ahead: float


class Result(TypedDict):
    """A measured slot compared with its predictions."""

    start: str
    actual: float
    latest: float | None
    day_ahead: float | None


def _summary(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    if not pairs:
        return {"samples": 0, "mae_w": None, "bias_w": None, "mape": None}
    errors = [p - a for p, a in pairs]
    relevant = [(p, a) for p, a in pairs if a >= 50]  # avoid dividing by ~0 W
    mape = (
        round(sum(abs(p - a) / a for p, a in relevant) / len(relevant) * 100, 1)
        if relevant
        else None
    )
    return {
        "samples": len(pairs),
        "mae_w": round(sum(abs(e) for e in errors) / len(errors), 1),
        "bias_w": round(sum(errors) / len(errors), 1),  # + = forecast too high
        "mape": mape,
    }


class ForecastVerification:
    """Keeps predictions per slot and compares them with measurements."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.verification"
        )
        self.predictions: dict[str, Prediction] = {}
        self.results: list[Result] = []

    async def async_load(self) -> None:
        """Load stored predictions and results."""
        if (data := await self._store.async_load()) is not None:
            self.predictions = data.get("predictions", {})
            self.results = data.get("results", [])

    async def async_save(self) -> None:
        """Write to disk now."""
        await self._store.async_save(self._data())

    def record(self, slots: Iterable[ForecastSlot], now: datetime) -> None:
        """Remember the predictions of the latest forecast for future slots."""
        for slot in slots:
            if slot.start <= now:
                continue  # already started: too late to count as a prediction
            prediction = self.predictions.setdefault(slot.start.isoformat(), {})
            prediction["latest"] = slot.power_w
            if slot.start - now >= DAY_AHEAD:
                prediction["day_ahead"] = slot.power_w
        self._store.async_delay_save(self._data, SAVE_DELAY)

    def evaluate(self, records: Iterable[ConsumptionRecord], now: datetime) -> int:
        """Compare measured slots with their predictions; returns how many."""
        measured = {
            r["start"]: r
            for r in records
            if r.get("source") != "import" and r["coverage"] >= MIN_COVERAGE
        }
        count = 0
        for start in list(self.predictions):
            record = measured.get(start)
            if record is None:
                continue
            prediction = self.predictions.pop(start)
            self.results.append(
                Result(
                    start=start,
                    actual=record["avg_w"],
                    latest=prediction.get("latest"),
                    day_ahead=prediction.get("day_ahead"),
                )
            )
            count += 1
        cutoff = (now - RETENTION).isoformat()
        self.results = [r for r in self.results if r["start"] >= cutoff]
        # Predictions for slots that were never measured are dropped after a day.
        stale = (now - timedelta(days=1)).isoformat()
        self.predictions = {k: v for k, v in self.predictions.items() if k >= stale}
        if count:
            self._store.async_delay_save(self._data, SAVE_DELAY)
            _LOGGER.debug("Verified %d forecast slots", count)
        return count

    def summary(
        self, now: datetime, period: timedelta = SUMMARY_PERIOD
    ) -> dict[str, Any]:
        """Accuracy over ``period``: latest and day-ahead predictions."""
        since = (now - period).isoformat()
        recent = [r for r in self.results if r["start"] >= since]
        return {
            "period_days": period.days,
            "latest": _summary(
                [(r["latest"], r["actual"]) for r in recent if r["latest"] is not None]
            ),
            "day_ahead": _summary(
                [
                    (r["day_ahead"], r["actual"])
                    for r in recent
                    if r["day_ahead"] is not None
                ]
            ),
        }

    def _data(self) -> dict[str, Any]:
        return {"predictions": self.predictions, "results": self.results}
