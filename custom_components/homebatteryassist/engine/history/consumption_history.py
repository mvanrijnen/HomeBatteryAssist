"""Recording of house consumption per fixed interval, as basis for forecasting."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any, NotRequired, TypedDict

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ...const import DOMAIN, HISTORY_RETENTION

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY = 60  # seconds


class ConsumptionRecord(TypedDict):
    """Average house consumption over one interval."""

    start: str  # ISO 8601, UTC
    minutes: int  # interval length
    avg_w: float  # time-weighted average power while measured
    coverage: float  # fraction of the interval with a valid measurement (0..1)
    source: NotRequired[str]  # "import" for records imported from statistics
    excluded_w: NotRequired[float]  # average power of excluded devices (e.g. EV)
    pv_w: NotRequired[float]  # average measured PV production
    battery_w: NotRequired[float]  # average battery power, + charging / - discharging
    phase_house_w: NotRequired[list[float]]  # average house consumption per phase
    phase_pv_w: NotRequired[list[float]]  # average PV production per phase
    vacation: NotRequired[bool]  # measured in vacation mode: not learned from


def _valid(record: object) -> bool:
    """A stored record has the fields every reader relies on."""
    if not isinstance(record, dict):
        return False
    try:
        return (
            dt_util.parse_datetime(str(record["start"])) is not None
            and float(record["minutes"]) > 0
            and math.isfinite(float(record["avg_w"]))
            and 0.0 <= float(record["coverage"]) <= 1.0
        )
    except (KeyError, TypeError, ValueError):
        return False


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
        self.vacation = False  # mark new records as vacation (not learned)
        self._interval = timedelta(minutes=minutes)
        self.records: list[ConsumptionRecord] = []

        self._interval_start: datetime | None = None
        self._last_time: datetime | None = None
        self._last_power: float | None = None
        self._last_excluded: float | None = None
        self._last_pv: float | None = None
        self._last_battery: float | None = None
        self._energy_ws = 0.0
        self._excluded_ws = 0.0
        self._pv_ws = 0.0
        self._pv_s = 0.0
        self._battery_ws = 0.0
        self._battery_s = 0.0
        self._measured_s = 0.0
        self._last_phases: tuple[tuple[float, ...], tuple[float, ...]] | None = None
        self._phase_house_ws: list[float] = []
        self._phase_pv_ws: list[float] = []
        self._phase_s = 0.0
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
            records = data.get("records", [])
            self.records = [r for r in records if _valid(r)]
            if len(self.records) != len(records):
                _LOGGER.warning(
                    "Skipped %d invalid consumption history records",
                    len(records) - len(self.records),
                )

    async def async_save(self) -> None:
        """Write records to disk now."""
        await self._store.async_save(self._data())

    def interval_start(self, when: datetime) -> datetime:
        """Return the start of the interval containing ``when`` (UTC aligned)."""
        seconds = self._interval.total_seconds()
        ts = dt_util.as_utc(when).timestamp()
        return dt_util.utc_from_timestamp(ts - ts % seconds)

    @callback
    def add_sample(
        self,
        when: datetime,
        power: float | None,
        excluded: float | None = None,
        pv: float | None = None,
        battery: float | None = None,
        phases: tuple[tuple[float, ...], tuple[float, ...]] | None = None,
    ) -> None:
        """Register new values (W): house consumption and excluded devices.

        ``None`` for power means unknown; excluded devices are only recorded
        while the house consumption is known.
        """
        start = self.interval_start(when)
        if self._interval_start is None:
            self._interval_start = start
        elif start > self._interval_start:
            # The boundary has not been processed yet (or was missed).
            self._roll_over(start)
        self._integrate(when)
        self._last_power = power
        self._last_excluded = excluded
        self._last_pv = pv
        self._last_battery = battery
        self._last_phases = phases if phases and phases[0] else None

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
            if self._excluded_ws > 0:
                record["excluded_w"] = round(self._excluded_ws / self._measured_s, 1)
            if self._pv_s > 0:
                record["pv_w"] = round(self._pv_ws / self._pv_s, 1)
            if self._battery_s > 0:
                record["battery_w"] = round(self._battery_ws / self._battery_s, 1)
            if self.vacation:
                record["vacation"] = True
            if self._phase_s > 0:
                record["phase_house_w"] = [
                    round(v / self._phase_s, 1) for v in self._phase_house_ws
                ]
                record["phase_pv_w"] = [
                    round(v / self._phase_s, 1) for v in self._phase_pv_ws
                ]
            self.records.append(record)
            self.prune(self._interval_start)
            self._store.async_delay_save(self._data, SAVE_DELAY)
            _LOGGER.debug("Recorded %s", record)

        self._energy_ws = 0.0
        self._excluded_ws = 0.0
        self._pv_ws = 0.0
        self._pv_s = 0.0
        self._battery_ws = 0.0
        self._battery_s = 0.0
        self._measured_s = 0.0
        self._phase_house_ws = []
        self._phase_pv_ws = []
        self._phase_s = 0.0
        return record

    def _integrate(self, when: datetime) -> None:
        if self._last_time is not None and self._last_power is not None:
            seconds = max((when - self._last_time).total_seconds(), 0.0)
            self._energy_ws += self._last_power * seconds
            self._excluded_ws += (self._last_excluded or 0.0) * seconds
            self._measured_s += seconds
            if self._last_pv is not None:
                self._pv_ws += self._last_pv * seconds
                self._pv_s += seconds
            if self._last_battery is not None:
                self._battery_ws += self._last_battery * seconds
                self._battery_s += seconds
            if self._last_phases is not None:
                house, pv = self._last_phases
                if len(self._phase_house_ws) != len(house):
                    self._phase_house_ws = [0.0] * len(house)
                    self._phase_pv_ws = [0.0] * len(house)
                    self._phase_s = 0.0
                for i, value in enumerate(house):
                    self._phase_house_ws[i] += value * seconds
                for i, value in enumerate(pv[: len(house)]):
                    self._phase_pv_ws[i] += value * seconds
                self._phase_s += seconds
        self._last_time = when

    def prune(self, now: datetime) -> None:
        """Drop records older than the retention period."""
        cutoff = (dt_util.as_utc(now) - HISTORY_RETENTION).isoformat()
        self.records = [r for r in self.records if r["start"] >= cutoff]

    def _data(self) -> dict[str, Any]:
        return {"records": self.records}
