"""Running accuracy of the forecasts, and corrections learned from it.

For three kinds of forecast, every slot keeps the prediction per *lead time*
bucket (how long before the slot it was made):

- ``consumption``: our own house consumption forecast, checked against the
  measured consumption (own history records);
- ``pv``: the PV forecast (Wh per hour), checked against the measured PV
  production (``pv_w`` in the history);
- ``price``: estimated (forecast) prices, checked against the price that is
  published later for the same period.

Results are kept for ``RETENTION`` and summarised per bucket with exponential
weights (half-life ``HALF_LIFE``): a running mean absolute error, bias and
MAPE. From those, a correction per bucket is derived:

- consumption: additive (minus the bias, W);
- pv: a factor (measured / predicted energy), clamped to ``PV_FACTOR_RANGE``;
- price: additive (minus the bias), only for estimated prices.

Corrections grow with the number of samples (``MIN_SAMPLES`` for full
strength). Learning always uses the *raw* predictions, so a correction never
feeds back on itself.

Users (scripts, automations) control the correction per kind through the
actions ``set_forecast_correction`` (mode ``learned``, ``off`` or ``manual``
with an own value, optionally per bucket and for a limited time) and
``reset_forecast_accuracy`` (forget what was learned).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ...const import DOMAIN
from ..history.consumption_history import ConsumptionRecord
from .pv_corrections.base import PvResult

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY = 60
RETENTION = timedelta(days=28)
HALF_LIFE = timedelta(days=7)
MIN_COVERAGE = 0.8

type Kind = Literal["consumption", "pv", "price"]
KINDS: tuple[Kind, ...] = ("consumption", "pv", "price")
# Extra kinds "consumption@<forecaster key>": every consumption forecaster's
# own predictions, to compare forecasters (no corrections are learned for them).
FORECASTER_KIND = "consumption@"
# Extra kinds "pv@<correction key>": every PV correction's corrected forecast,
# to compare the corrections.
PV_CORRECTOR_KIND = "pv@"
type Mode = Literal["learned", "off", "manual"]
MODES: tuple[Mode, ...] = ("learned", "off", "manual")
ALL_BUCKETS = "all"

# (key, from hours, to hours) before the start of the slot
BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0-1h", 0, 1),
    ("1-6h", 1, 6),
    ("6-24h", 6, 24),
    ("1-2d", 24, 48),
    ("2-3d", 48, 72),
    ("3-5d", 72, 120),
    ("5d+", 120, math.inf),
)
BUCKET_KEYS = tuple(key for key, _, _ in BUCKETS)

MIN_SAMPLES: dict[Kind, int] = {"consumption": 96, "pv": 24, "price": 48}
PV_FACTOR_RANGE = (0.5, 1.5)
PV_MIN_WH = 20.0  # night hours (both ~0) say nothing about PV accuracy
MAPE_MIN = 50.0  # W / Wh: below this, relative errors are meaningless


def bucket_for(lead: timedelta) -> str | None:
    """The lead time bucket of a prediction made ``lead`` before its slot."""
    hours = lead.total_seconds() / 3600
    if hours < 0:
        return None
    return next(key for key, low, high in BUCKETS if low <= hours < high)


@dataclass(frozen=True, slots=True)
class BucketStats:
    """Running (exponentially weighted) accuracy of one lead time bucket."""

    samples: int
    mae: float | None
    bias: float | None  # + = forecast too high
    mape: float | None
    ratio: float | None  # measured / predicted (sum), for PV
    correction: float | None  # additive (consumption, price) or factor (pv)
    strength: float  # 0..1, grows with the number of samples


class ForecastAccuracy:
    """Keeps predictions per slot and lead bucket; compares and corrects."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.accuracy"
        )
        # kind -> slot start ISO -> {"end": ISO, bucket: raw prediction}
        self.predictions: dict[str, dict[str, dict[str, Any]]] = {k: {} for k in KINDS}
        # kind -> [{"start", "actual", "pred": {bucket: value}}]
        self.results: dict[str, list[dict[str, Any]]] = {k: [] for k in KINDS}
        self._stats: dict[str, dict[str, BucketStats]] = {}
        # kind -> {"mode": Mode, "manual": {bucket|"all": value}, "until": ISO|None}
        self.settings: dict[str, dict[str, Any]] = {
            k: _default_setting() for k in KINDS
        }
        self.kinds: list[str] = list(KINDS)

    def track(self, kind: str) -> None:
        """Also keep predictions and results of ``kind`` (a forecaster)."""
        if kind not in self.kinds:
            self.kinds.append(kind)
            self.predictions.setdefault(kind, {})
            self.results.setdefault(kind, [])
            self.settings.setdefault(kind, _default_setting())

    def pv_correctors(self) -> dict[str, dict[str, Any]]:
        """Accuracy per PV correction (key -> summary per bucket)."""
        return {
            kind.removeprefix(PV_CORRECTOR_KIND): self.summary(kind)
            for kind in self.kinds
            if kind.startswith(PV_CORRECTOR_KIND)
        }

    def pv_results(self) -> list[PvResult]:
        """The settled PV hours: measured and raw predicted Wh per lead time."""
        out = []
        for result in self.results["pv"]:
            start = dt_util.parse_datetime(result["start"])
            if start is not None:
                out.append(PvResult(start, result["actual"], dict(result["pred"])))
        return out

    def bucket_factors(self, now: datetime) -> dict[str, float]:
        """The PV factor per lead time bucket in use now (1.0 = none)."""
        return {
            bucket: (self.correction_for("pv", bucket, now) or 1.0)
            for bucket in BUCKET_KEYS
        }

    def lead_factor(self, start: datetime, now: datetime) -> float:
        """The PV factor for a slot starting at ``start`` (1.0 = none)."""
        lead = max(start - now, timedelta(0))
        return self.correction_for("pv", bucket_for(lead), now) or 1.0

    def forecasters(self) -> dict[str, dict[str, Any]]:
        """Accuracy per consumption forecaster (key -> summary per bucket)."""
        return {
            kind.removeprefix(FORECASTER_KIND): self.summary(kind)
            for kind in self.kinds
            if kind.startswith(FORECASTER_KIND)
        }

    async def async_load(self) -> None:
        """Load stored predictions and results."""
        if (data := await self._store.async_load()) is not None:
            for kind in data.get("predictions", {}) | data.get("results", {}):
                if kind.startswith((FORECASTER_KIND, PV_CORRECTOR_KIND)):
                    self.track(kind)
            for kind in self.kinds:
                self.predictions[kind] = data.get("predictions", {}).get(kind, {})
                self.results[kind] = data.get("results", {}).get(kind, [])
                self.settings[kind] = (
                    data.get("settings", {}).get(kind) or _default_setting()
                )
        self.refresh_stats(dt_util.utcnow())

    async def async_save(self) -> None:
        """Write to disk now."""
        await self._store.async_save(self._data())

    # -- recording ---------------------------------------------------------------

    def record(
        self,
        kind: Kind,
        slots: Iterable[tuple[datetime, datetime, float]],
        now: datetime,
    ) -> None:
        """Remember raw predictions (start, end, value) for future slots."""
        bucket_slots = self.predictions[kind]
        for start, end, value in slots:
            bucket = bucket_for(start - now)
            if bucket is None:
                continue  # already started
            entry = bucket_slots.setdefault(start.isoformat(), {"end": end.isoformat()})
            entry[bucket] = round(value, 4)
        self._store.async_delay_save(self._data, SAVE_DELAY)

    def _settle(self, kind: Kind, actuals: Mapping[str, float]) -> int:
        """Move predictions with a known actual value to the results."""
        count = 0
        pending = self.predictions[kind]
        for start in [s for s in pending if s in actuals]:
            entry = pending.pop(start)
            pred = {k: v for k, v in entry.items() if k in BUCKET_KEYS}
            if pred:
                self.results[kind].append(
                    {"start": start, "actual": round(actuals[start], 4), "pred": pred}
                )
                count += 1
        return count

    def evaluate_consumption(self, records: Iterable[ConsumptionRecord]) -> int:
        """Compare with measured house consumption (own, well covered records)."""
        actuals = {
            r["start"]: r["avg_w"]
            for r in records
            if r.get("source") != "import" and r["coverage"] >= MIN_COVERAGE
        }
        count = self._settle("consumption", actuals)
        for kind in self.kinds:
            if kind.startswith(FORECASTER_KIND):
                self._settle(kind, actuals)
        return count

    def evaluate_pv(self, records: Iterable[ConsumptionRecord]) -> int:
        """Compare with measured PV energy per hour (Wh) from the history."""
        hours: dict[str, list[float]] = {}  # hour ISO -> [energy Wh, minutes]
        for r in records:
            if "pv_w" not in r:
                continue
            start = dt_util.parse_datetime(r["start"])
            if start is None:
                continue
            hour = start.replace(minute=0, second=0, microsecond=0).isoformat()
            measured = r["minutes"] * r["coverage"]
            acc = hours.setdefault(hour, [0.0, 0.0])
            acc[0] += r["pv_w"] * measured / 60
            acc[1] += measured
        # Only hours that are over (recorded up to their end), so a short
        # interval does not settle an hour before its last records.
        latest = max(
            (
                start + timedelta(minutes=r["minutes"])
                for r in records
                if (start := dt_util.parse_datetime(r["start"])) is not None
            ),
            default=None,
        )
        actuals = {
            # scale up for missing minutes, only when well covered
            hour: energy * 60 / minutes
            for hour, (energy, minutes) in hours.items()
            if minutes >= 60 * MIN_COVERAGE
            and latest is not None
            and (h := dt_util.parse_datetime(hour)) is not None
            and latest >= h + timedelta(hours=1)
        }
        # Skip night hours: nothing to learn from 0 vs 0.
        pending = self.predictions["pv"]
        night = [
            hour
            for hour in pending
            if hour in actuals
            and actuals[hour] < PV_MIN_WH
            and all(v < PV_MIN_WH for k, v in pending[hour].items() if k in BUCKET_KEYS)
        ]
        corrections = [k for k in self.kinds if k.startswith(PV_CORRECTOR_KIND)]
        for hour in night:
            for kind in ("pv", *corrections):
                self.predictions[kind].pop(hour, None)
            actuals.pop(hour)
        for kind in corrections:
            self._settle(kind, actuals)
        return self._settle("pv", actuals)

    def evaluate_prices(self, published: Mapping[str, float]) -> int:
        """Compare estimated prices with prices published later (start ISO -> price)."""
        return self._settle("price", published)

    def prune(self, now: datetime) -> None:
        """Drop old results and predictions that will never be settled."""
        cutoff = (now - RETENTION).isoformat()
        stale = (now - timedelta(days=2)).isoformat()
        for kind in self.kinds:
            self.results[kind] = [r for r in self.results[kind] if r["start"] >= cutoff]
            self.predictions[kind] = {
                start: entry
                for start, entry in self.predictions[kind].items()
                if entry["end"] >= stale
            }
        self._store.async_delay_save(self._data, SAVE_DELAY)

    # -- statistics and corrections --------------------------------------------

    def refresh_stats(self, now: datetime) -> None:
        """Recalculate the running statistics per kind and bucket."""
        self._stats = {kind: self._kind_stats(kind, now) for kind in self.kinds}

    def _kind_stats(self, kind: Kind, now: datetime) -> dict[str, BucketStats]:
        sums: dict[str, list[float]] = {}
        for result in self.results[kind]:
            start = dt_util.parse_datetime(result["start"])
            if start is None:
                continue
            weight = math.pow(
                0.5, max((now - start).total_seconds(), 0) / HALF_LIFE.total_seconds()
            )
            actual = result["actual"]
            for bucket, pred in result["pred"].items():
                # [n, w, w*err, w*|err|, w*|err|/actual (mape), w for mape, w*actual, w*pred]
                acc = sums.setdefault(bucket, [0.0] * 8)
                error = pred - actual
                acc[0] += 1
                acc[1] += weight
                acc[2] += weight * error
                acc[3] += weight * abs(error)
                if actual and (abs(actual) >= MAPE_MIN or kind == "price"):
                    acc[4] += weight * abs(error) / abs(actual)
                    acc[5] += weight
                acc[6] += weight * actual
                acc[7] += weight * pred
        stats: dict[str, BucketStats] = {}
        for bucket in BUCKET_KEYS:
            acc = sums.get(bucket)
            if not acc or not acc[1]:
                stats[bucket] = BucketStats(0, None, None, None, None, None, 0.0)
                continue
            n, w = int(acc[0]), acc[1]
            bias = acc[2] / w
            ratio = acc[6] / acc[7] if acc[7] else None
            strength = min(n / MIN_SAMPLES.get(kind, MIN_SAMPLES["consumption"]), 1.0)
            if kind == "pv":
                low, high = PV_FACTOR_RANGE
                factor = min(max(ratio, low), high) if ratio is not None else 1.0
                correction = 1 + (factor - 1) * strength
            else:
                correction = -bias * strength
            stats[bucket] = BucketStats(
                samples=n,
                mae=acc[3] / w,
                bias=bias,
                mape=acc[4] / acc[5] * 100 if acc[5] else None,
                ratio=ratio,
                correction=correction,
                strength=strength,
            )
        return stats

    def stats(self, kind: Kind) -> dict[str, BucketStats]:
        """Running statistics of ``kind`` per bucket."""
        return self._stats.get(kind, {})

    # -- user control ----------------------------------------------------------

    def set_mode(
        self,
        kind: Kind,
        mode: Mode,
        value: float | None = None,
        bucket: str = ALL_BUCKETS,
        until: datetime | None = None,
    ) -> None:
        """Set how ``kind`` is corrected (by a user, script or automation)."""
        setting = self.settings[kind]
        setting["mode"] = mode
        setting["until"] = until.isoformat() if until else None
        if mode == "manual":
            if bucket == ALL_BUCKETS:
                setting["manual"] = {}
            default = 1.0 if kind == "pv" else 0.0
            setting["manual"][bucket] = float(value if value is not None else default)
        else:
            setting["manual"] = {}
        self._store.async_delay_save(self._data, 1)

    def reset(self, kind: Kind) -> None:
        """Forget what was learned for ``kind``."""
        self.results[kind] = []
        self.predictions[kind] = {}
        self._stats[kind] = self._kind_stats(kind, dt_util.utcnow())
        self._store.async_delay_save(self._data, 1)

    def mode(self, kind: Kind, now: datetime) -> Mode:
        """Current mode; a temporary mode falls back to ``learned`` after it ends."""
        setting = self.settings[kind]
        until = (
            dt_util.parse_datetime(setting["until"]) if setting.get("until") else None
        )
        if until is not None and now >= until:
            self.settings[kind] = _default_setting()
            self._store.async_delay_save(self._data, SAVE_DELAY)
        return self.settings[kind]["mode"]

    def correction_for(
        self, kind: Kind, bucket: str | None, now: datetime
    ) -> float | None:
        """The correction used for ``bucket``: manual, learned or none."""
        mode = self.mode(kind, now)
        if bucket is None or mode == "off":
            return None
        if mode == "manual":
            manual = self.settings[kind]["manual"]
            return manual.get(bucket, manual.get(ALL_BUCKETS))
        stats = self._stats.get(kind, {}).get(bucket)
        return stats.correction if stats else None

    def correct(
        self, kind: Kind, value: float, start: datetime, now: datetime
    ) -> float:
        """Apply the correction for the lead time of ``start`` to ``value``."""
        # A slot that already started counts as the shortest lead time.
        lead = max(start - now, timedelta(0))
        correction = self.correction_for(kind, bucket_for(lead), now)
        if correction is None:
            return value
        if kind == "pv":
            return max(value * correction, 0.0)
        # Never change a value by more than half of its size.
        limit = abs(value) * 0.5
        corrected = value + max(-limit, min(limit, correction))
        return max(corrected, 0.0) if kind == "consumption" else corrected

    def summary(self, kind: Kind) -> dict[str, Any]:
        """JSON-friendly statistics per bucket (sensors, dashboard, diagnostics)."""
        digits = 4 if kind == "price" else 1
        return {
            bucket: {
                "samples": s.samples,
                "mae": round(s.mae, digits) if s.mae is not None else None,
                "bias": round(s.bias, digits) if s.bias is not None else None,
                "mape": round(s.mape, 1) if s.mape is not None else None,
                "correction": (
                    round(s.correction, 3 if kind == "pv" else digits)
                    if s.correction is not None
                    else None
                ),
                "strength": round(s.strength, 2),
            }
            for bucket, s in self.stats(kind).items()
        }

    def headline(self, kind: Kind) -> BucketStats | None:
        """The most informative bucket: the shortest lead time with samples."""
        return next((s for s in self.stats(kind).values() if s.samples), None)

    def _data(self) -> dict[str, Any]:
        return {
            "predictions": self.predictions,
            "results": self.results,
            "settings": self.settings,
        }


def _default_setting() -> dict[str, Any]:
    return {"mode": "learned", "manual": {}, "until": None}
