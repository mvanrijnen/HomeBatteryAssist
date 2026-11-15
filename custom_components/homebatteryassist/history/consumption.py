"""Recording of house consumption per fixed interval, as basis for forecasting."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, TypedDict

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ..const import DOMAIN, HISTORY_RETENTION

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY = 60  # seconds


class ConsumptionRecord(TypedDict):
    """Average house consumption over one interval."""

    start: str  # ISO 8601, UTC
    minutes: int  # interval length
    avg_w: float  # time-weighted average power while measured
    coverage: float  # fraction of the interval with a valid measurement (0..1)


class ConsumptionHistory:
    """Time-weighted average of house consumption per interval, persisted to disk.

    Feed power samples with :meth:`add_sample`. After :meth:`async_start`,
    intervals are closed automatically at every clock-aligned boundary. Records
    older than ``HISTORY_RETENTION`` are pruned.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str, minutes: int) -> None:
        """Initialize."""
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.consumption"
        )
        self.minutes = minutes
        self._interval = timedelta(minutes=minutes)
        self.records: list[ConsumptionRecord] = []

        self._interval_start: datetime | None = None
        self._last_time: datetime | None = None
        self._last_power: float | None = None
        self._energy_ws = 0.0
        self._measured_s = 0.0
        self._unsub_timer: CALLBACK_TYPE | None = None

    async def async_start(self) -> None:
        """Load stored records and close intervals at every boundary."""
        await self.async_load()
        minute: str | int = f"/{self.minutes}" if self.minutes < 60 else 0
        self._unsub_timer = async_track_utc_time_change(
            self.hass, self._async_boundary, minute=minute, second=0
        )
        _LOGGER.debug(
            "Consumption history started: %s-minute interval, %d stored records",
            self.minutes,
            len(self.records),
        )

    async def async_stop(self) -> None:
        """Stop the boundary timer and write records to disk."""
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None
        await self.async_save()

    async def async_load(self) -> None:
        """Load stored records."""
        if (data := await self._store.async_load()) is not None:
            self.records = data.get("records", [])

    async def async_save(self) -> None:
        """Write records to disk now."""
        await self._store.async_save(self._data())

    def interval_start(self, when: datetime) -> datetime:
        """Return the start of the interval containing ``when`` (UTC aligned)."""
        seconds = self._interval.total_seconds()
        ts = dt_util.as_utc(when).timestamp()
        return dt_util.utc_from_timestamp(ts - ts % seconds)

    @callback
    def add_sample(self, when: datetime, power: float | None) -> None:
        """Register a new power value (W), or ``None`` if unknown."""
        start = self.interval_start(when)
        if self._interval_start is None:
            self._interval_start = start
        elif start > self._interval_start:
            # The boundary has not been processed yet (or was missed).
            self._roll_over(start)
        self._integrate(when)
        self._last_power = power

    @callback
    def close_interval(self, when: datetime) -> ConsumptionRecord | None:
        """Finish the running interval if ``when`` is past its end.

        Safe to call late or more than once: the interval is closed exactly at
        its end and only once.
        """
        start = self.interval_start(when)
        if self._interval_start is None or start <= self._interval_start:
            return None
        return self._roll_over(start)

    @callback
    def _async_boundary(self, now: datetime) -> None:
        self.close_interval(now)

    def _roll_over(self, new_start: datetime) -> ConsumptionRecord | None:
        """Close the running interval at its end and continue at ``new_start``.

        If intervals were skipped entirely (e.g. Home Assistant was not running),
        the gap counts as not measured.
        """
        assert self._interval_start is not None
        end = self._interval_start + self._interval
        self._integrate(end)
        record = self._finish()
        self._interval_start = new_start
        if new_start > end:
            self._last_time = new_start
        return record

    def _finish(self) -> ConsumptionRecord | None:
        record: ConsumptionRecord | None = None
        if self._interval_start is not None and self._measured_s > 0:
            record = ConsumptionRecord(
                start=self._interval_start.isoformat(),
                minutes=self.minutes,
                avg_w=round(self._energy_ws / self._measured_s, 1),
                coverage=round(
                    min(self._measured_s / self._interval.total_seconds(), 1.0), 3
                ),
            )
            self.records.append(record)
            self._prune(self._interval_start)
            self._store.async_delay_save(self._data, SAVE_DELAY)
            _LOGGER.debug("Recorded %s", record)

        self._energy_ws = 0.0
        self._measured_s = 0.0
        return record

    def _integrate(self, when: datetime) -> None:
        if self._last_time is not None and self._last_power is not None:
            seconds = max((when - self._last_time).total_seconds(), 0.0)
            self._energy_ws += self._last_power * seconds
            self._measured_s += seconds
        self._last_time = when

    def _prune(self, now: datetime) -> None:
        cutoff = (dt_util.as_utc(now) - HISTORY_RETENTION).isoformat()
        self.records = [r for r in self.records if r["start"] >= cutoff]

    def _data(self) -> dict[str, Any]:
        return {"records": self.records}
