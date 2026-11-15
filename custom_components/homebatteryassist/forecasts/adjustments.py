"""User adjustments of the consumption forecast.

Set through the actions ``homebatteryassist.adjust_forecast`` and
``homebatteryassist.clear_forecast_adjustments`` (from scripts, automations or
other integrations). An adjustment covers a period and either multiplies the
expected consumption (``factor``), adds to it (``offset_w``, may be negative)
or replaces it (``power_w``). Adjustments are persisted and expire after their
end. When several overlap: ``power_w`` first, then factors, then offsets.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
KINDS = ("power_w", "factor", "offset_w")
type AdjustmentKind = Literal["power_w", "factor", "offset_w"]


class Adjustment(TypedDict):
    """One adjustment of the consumption forecast."""

    id: str
    name: str
    start: str  # ISO 8601, UTC
    end: str
    kind: AdjustmentKind
    value: float


def _span(adjustment: Adjustment) -> tuple[datetime, datetime]:
    start = dt_util.parse_datetime(adjustment["start"])
    end = dt_util.parse_datetime(adjustment["end"])
    assert start is not None and end is not None
    return start, end


def apply_adjustments(
    base: float, start: datetime, end: datetime, adjustments: Iterable[Adjustment]
) -> tuple[float, tuple[str, ...]]:
    """Apply the adjustments overlapping ``[start, end)`` to ``base`` (W).

    A partly overlapping adjustment is weighted by the overlapping fraction.
    """
    length = (end - start).total_seconds()
    active: list[tuple[Adjustment, float]] = []
    for adjustment in adjustments:
        a_start, a_end = _span(adjustment)
        overlap = (min(end, a_end) - max(start, a_start)).total_seconds()
        if overlap > 0 and length > 0:
            active.append((adjustment, overlap / length))
    if not active:
        return base, ()

    power = base
    for kind in KINDS:
        for adjustment, share in active:
            if adjustment["kind"] != kind:
                continue
            value = adjustment["value"]
            if kind == "power_w":
                power = power * (1 - share) + value * share
            elif kind == "factor":
                power *= 1 + (value - 1) * share
            else:
                power += value * share
    return round(max(power, 0.0), 1), tuple(a["name"] for a, _ in active)


class AdjustmentStore:
    """Persisted list of adjustments."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.adjustments"
        )
        self.items: list[Adjustment] = []

    async def async_load(self) -> None:
        """Load stored adjustments."""
        if (data := await self._store.async_load()) is not None:
            self.items = data.get("adjustments", [])
        self.prune(dt_util.utcnow())

    async def async_save(self) -> None:
        """Write to disk."""
        await self._store.async_save({"adjustments": self.items})

    def prune(self, now: datetime) -> None:
        """Drop expired adjustments."""
        self.items = [a for a in self.items if _span(a)[1] > now]

    async def async_add(
        self,
        name: str | None,
        start: datetime,
        end: datetime,
        kind: AdjustmentKind,
        value: float,
    ) -> Adjustment:
        """Add an adjustment."""
        adjustment = Adjustment(
            id=uuid.uuid4().hex[:8],
            name=name or kind,
            start=dt_util.as_utc(start).isoformat(),
            end=dt_util.as_utc(end).isoformat(),
            kind=kind,
            value=float(value),
        )
        self.items.append(adjustment)
        await self.async_save()
        _LOGGER.debug("Added forecast adjustment %s", adjustment)
        return adjustment

    async def async_clear(
        self, ids: Iterable[str] = (), names: Iterable[str] = ()
    ) -> int:
        """Remove adjustments by id or name; nothing given = all. Returns the count."""
        ids, names = set(ids), set(names)
        before = len(self.items)
        if ids or names:
            self.items = [
                a for a in self.items if a["id"] not in ids and a["name"] not in names
            ]
        else:
            self.items = []
        await self.async_save()
        return before - len(self.items)
