"""User adjustments of the consumption forecast.

Set through the actions ``homebatteryassist.adjust_forecast`` and
``homebatteryassist.clear_forecast_adjustments`` (from scripts, automations or
other integrations) or the dashboard (*Expected extra consumption*). An
adjustment covers a period and either multiplies the expected consumption
(``factor``), adds to it (``offset_w``, may be negative), replaces it
(``power_w``) or adds an amount of energy spread evenly over the period
(``energy_kwh``, e.g. 1.5 kWh for the washing machine tomorrow 13:00-15:00).
Energy is either extra, on top of the learned consumption, or *part* of it
(``part``: the learned consumption of that day already holds it, it only
happens at that time): then the same energy is taken from the rest of that
local day, in proportion to its expected consumption (``rebalance_parts``).
Adjustments are persisted and expire after their end. When several overlap:
``power_w`` first, then factors, then offsets and energy.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal, NotRequired, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ...const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
KINDS = ("power_w", "factor", "offset_w", "energy_kwh")
type AdjustmentKind = Literal["power_w", "factor", "offset_w", "energy_kwh"]


class Adjustment(TypedDict):
    """One adjustment of the consumption forecast."""

    id: str
    name: str
    start: str  # ISO 8601, UTC
    end: str
    kind: AdjustmentKind
    value: float
    part: NotRequired[bool]  # energy_kwh: part of the learned consumption


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
            elif kind == "energy_kwh":
                power += energy_w(adjustment) * share
            else:
                power += value * share
    return round(max(power, 0.0), 1), tuple(a["name"] for a, _ in active)


def energy_w(adjustment: Adjustment) -> float:
    """The power (W) that spreads an energy adjustment over its period."""
    a_start, a_end = _span(adjustment)
    hours = (a_end - a_start).total_seconds() / 3600
    return adjustment["value"] * 1000 / hours if hours > 0 else 0.0


type Row = tuple[datetime, datetime, float, tuple[str, ...]]


def rebalance_parts(rows: list[Row], adjustments: Iterable[Adjustment]) -> list[Row]:
    """For energy that is *part* of the learned consumption: take the energy
    added in its period from the rest of the local day it starts on (the
    rows given, outside the period), in proportion to their power, never
    below 0 W.

    ``rows``: (start, end, power W, applied names) after ``apply_adjustments``.
    """
    result = list(rows)
    for adjustment in adjustments:
        if adjustment["kind"] != "energy_kwh" or not adjustment.get("part"):
            continue
        a_start, a_end = _span(adjustment)
        day = dt_util.as_local(a_start).date()
        power_w = energy_w(adjustment)
        added = rest = 0.0
        others: list[int] = []
        for i, (start, end, power, _names) in enumerate(result):
            overlap = (min(end, a_end) - max(start, a_start)).total_seconds() / 3600
            if overlap > 0:
                added += power_w * overlap
            elif dt_util.as_local(start).date() == day:
                others.append(i)
                rest += power * (end - start).total_seconds() / 3600
        take = min(added, rest)  # Wh
        if take <= 0 or rest <= 0:
            continue
        factor = 1 - take / rest
        for i in others:
            start, end, power, names = result[i]
            result[i] = (
                start,
                end,
                round(max(power * factor, 0.0), 1),
                (*names, adjustment["name"]),
            )
    return result


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
        part: bool = False,
        adjustment_id: str | None = None,
    ) -> Adjustment:
        """Add an adjustment (``part``: energy that is part of the learned
        consumption); with the id of an existing one: replace it."""
        adjustment = Adjustment(
            id=adjustment_id or uuid.uuid4().hex[:8],
            name=name or kind,
            start=dt_util.as_utc(start).isoformat(),
            end=dt_util.as_utc(end).isoformat(),
            kind=kind,
            value=float(value),
        )
        if kind == "energy_kwh" and part:
            adjustment["part"] = True
        self.items = [a for a in self.items if a["id"] != adjustment["id"]]
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
