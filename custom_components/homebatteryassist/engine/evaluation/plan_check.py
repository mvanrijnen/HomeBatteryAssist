"""Checking the battery plan afterwards: what was planned versus what happened.

For every slot of the history interval (e.g. a quarter of an hour):

- planned: the battery power (+ charge / - discharge) and the expected saving
  that the selected plan had for that slot when it started (lead time 0);
- actual: the battery power derived from the charged / discharged energy
  counters of all batteries (real and virtual) over the slot, and the realised
  value (the batteries' ``value`` counters: discharging saves the price,
  charging costs it).

Per local day this gives the planned saving next to the realised value, and
the average deviation of the battery power. Kept for ``RETENTION`` days in
``.storage/homebatteryassist.<entry_id>.plan_check``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ...const import DOMAIN, VALUE_BASIS
from ..planning.battery_plan import PlanSlot
from ..planning.planners.base import grid_cost as _grid_cost

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
RETENTION = timedelta(days=28)
SAVE_DELAY = 60
WEAR_BASIS = 1  # realised values after wear, like the planned saving


def slot_saving(
    slot: PlanSlot, export_factor: float, cycle_cost: float
) -> float | None:
    """Expected saving of one plan slot compared with no battery."""
    if slot.price is None:
        return None
    hours = (slot.end - slot.start).total_seconds() / 3600
    export = (
        slot.export_price
        if slot.export_price is not None
        else slot.price * export_factor
    )
    without = _grid_cost(slot.grid_w - slot.power_w, hours, slot.price, export)
    with_plan = (
        _grid_cost(slot.grid_w, hours, slot.price, export)
        + abs(slot.power_w) * hours / 1000 * cycle_cost
    )
    return without - with_plan


class PlanVerification:
    """Records the plan per slot and settles it against the batteries' counters."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.plan_check"
        )
        # slot start ISO -> {"end", "plan_w", "plan_saving", "mode"}
        self.planned: dict[str, dict[str, Any]] = {}
        # settled slots: {"start", "end", "plan_w", "actual_w", "plan_saving",
        #                 "value", "mode"}
        self.records: list[dict[str, Any]] = []
        self._snapshot: tuple[str, float, float, float] | None = None

    async def async_load(self) -> None:
        """Load the stored records."""
        data = await self._store.async_load() or {}
        if data.get("value_basis") != VALUE_BASIS or data.get("wear") != WEAR_BASIS:
            data = {}  # realised values of an older basis (net metering / no wear)
        self.records = data.get("records", [])
        self.planned = data.get("planned", {})

    async def async_save(self) -> None:
        """Write to disk now."""
        await self._store.async_save(self._data())

    def _data(self) -> dict[str, Any]:
        return {
            "records": self.records,
            "planned": self.planned,
            "value_basis": VALUE_BASIS,
            "wear": WEAR_BASIS,
        }

    def record_plan(
        self,
        slots: list[PlanSlot],
        mode: str,
        now: datetime,
        export_factor: float,
        cycle_cost: float,
    ) -> None:
        """Remember what the plan says for the slot running now (once per slot)."""
        current = next((s for s in slots if s.start <= now < s.end), None)
        if current is None:
            return
        key = current.start.isoformat()
        if key in self.planned:
            return  # keep what was planned when the slot started
        saving = slot_saving(current, export_factor, cycle_cost)
        self.planned[key] = {
            "end": current.end.isoformat(),
            "plan_w": current.power_w,
            "plan_saving": None if saving is None else round(saving, 5),
            "mode": mode,
        }

    def settle(
        self,
        now: datetime,
        counters: Callable[[], Mapping[str, float]],
        cycle_cost: float = 0.0,
    ) -> None:
        """At a slot boundary: compare the finished slot(s) with the counters.

        ``counters`` gives the totals over all batteries: ``charged_kwh``,
        ``discharged_kwh`` and ``value``. The realised value is counted after
        wear (``cycle_cost`` per kWh charged or discharged), like the planned
        saving.
        """
        totals = counters()
        snapshot = (
            now.isoformat(),
            totals.get("charged_kwh", 0.0),
            totals.get("discharged_kwh", 0.0),
            totals.get("value", 0.0),
        )
        previous, self._snapshot = self._snapshot, snapshot
        if previous is None:
            return
        start = dt_util.parse_datetime(previous[0])
        if start is None:
            return
        hours = (now - start).total_seconds() / 3600
        if hours <= 0:
            return
        # The plan slot(s) that ended between the two snapshots.
        for key in sorted(self.planned):
            entry = self.planned[key]
            slot_end = dt_util.parse_datetime(entry["end"])
            slot_start = dt_util.parse_datetime(key)
            if slot_end is None or slot_start is None or slot_end > now:
                continue
            del self.planned[key]
            if slot_start < start - timedelta(minutes=1):
                continue  # not measured from its start (e.g. after a restart)
            charged = snapshot[1] - previous[1]
            discharged = snapshot[2] - previous[2]
            energy = charged - discharged
            wear = (charged + discharged) * cycle_cost
            self.records.append(
                {
                    "start": key,
                    "end": entry["end"],
                    "plan_w": entry["plan_w"],
                    "actual_w": round(energy * 1000 / hours, 1),
                    "plan_saving": entry["plan_saving"],
                    "value": round(snapshot[3] - previous[3] - wear, 5),
                    "mode": entry["mode"],
                }
            )
        cutoff = (now - RETENTION).isoformat()
        self.records = [r for r in self.records if r["start"] >= cutoff]
        self.planned = {k: v for k, v in self.planned.items() if v["end"] >= cutoff}
        self._store.async_delay_save(self._data, SAVE_DELAY)

    def days(self, count: int = 7) -> list[dict[str, Any]]:
        """Per local day (most recent first): planned saving, realised value,
        average deviation of the battery power, number of slots."""
        by_day: dict[str, dict[str, Any]] = {}
        for record in self.records:
            start = dt_util.parse_datetime(record["start"])
            if start is None:
                continue
            day = dt_util.as_local(start).date().isoformat()
            acc = by_day.setdefault(
                day,
                {"day": day, "planned": 0.0, "realized": 0.0, "dev": 0.0, "slots": 0},
            )
            acc["planned"] += record.get("plan_saving") or 0.0
            acc["realized"] += record.get("value") or 0.0
            acc["dev"] += abs(record["actual_w"] - record["plan_w"])
            acc["slots"] += 1
        result = []
        for day in sorted(by_day, reverse=True)[:count]:
            acc = by_day[day]
            result.append(
                {
                    "day": day,
                    "planned": round(acc["planned"], 2),
                    "realized": round(acc["realized"], 2),
                    "power_deviation_w": round(acc["dev"] / acc["slots"]),
                    "slots": acc["slots"],
                }
            )
        return result
