"""Recording of house consumption per fixed interval, as basis for forecasting."""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, NotRequired, TypedDict

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ...const import DOMAIN, HISTORY_RETENTION, NOMINAL_VOLTAGE

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
    # With a meter that measures current: net grid power (W) and current (A)
    # per phase, to learn the current that flows besides the power.
    phase_grid_w: NotRequired[list[float]]
    phase_a: NotRequired[list[float]]
    # Current besides the power per phase (as W at 230 V), worked out per
    # reading and averaged (not from the averages: a load switching within
    # the interval is no reactive power)
    phase_q: NotRequired[list[float]]
    vacation: NotRequired[bool]  # measured in vacation mode: not learned from
    heating_w: NotRequired[float]  # average power of heating/cooling (part of house)
    temp_c: NotRequired[float]  # average outdoor temperature (°C)
    # per heating/cooling zone (subentry id): average power "w" and, when
    # measured, room temperature "in" and own outdoor temperature "out"
    zones: NotRequired[dict[str, dict[str, float]]]
    # average power of short peaks that ended in this interval (part of avg_w)
    spike_w: NotRequired[float]


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


# The sums of the running interval (saved with the records, so a reload
# within the interval does not lose what was measured so far).
RUNNING_SUMS = (
    "_energy_ws",
    "_excluded_ws",
    "_heating_ws",
    "_heating_s",
    "_temp_cs",
    "_temp_s",
    "_zone_sums",
    "_spike_wh",
    "_pv_ws",
    "_pvm_ws",
    "_pv_s",
    "_battery_ws",
    "_battery_s",
    "_measured_s",
    "_phase_house_ws",
    "_phase_pv_ws",
    "_grid_ws",
    "_amp_s",
    "_q_s",
    "_grid_s",
    "_phase_s",
)


def reactive_w(power: float, current: float, voltage: float | None = None) -> float:
    """The current besides the power on a phase, as W at 230 V (one
    reading). With the measured voltage where known; a current in whole amps
    (a smart meter rounds it) counts half an amp less, so the rounding is not
    taken for reactive power."""
    volt = voltage if voltage is not None and voltage > 100 else NOMINAL_VOLTAGE
    amps = abs(current)
    if amps and abs(amps - round(amps)) < 1e-6:
        amps = max(amps - 0.5, 0.0)
    seen = amps * volt
    reactive = math.sqrt(max(seen * seen - power * power, 0.0))
    return reactive * NOMINAL_VOLTAGE / volt


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
        self._last_pv_measured: float | None = None
        self._last_battery: float | None = None
        self._energy_ws = 0.0
        self._excluded_ws = 0.0
        self._heating_ws = 0.0
        self._heating_s = 0.0
        self._temp_cs = 0.0
        self._temp_s = 0.0
        self._last_heating: float | None = None
        self._last_temp: float | None = None
        # zone -> [sum w*s, s, sum in*s, s, sum out*s, s]
        self._zone_sums: dict[str, list[float]] = {}
        self._last_zones: Mapping[str, tuple[float | None, ...]] | None = None
        self._spike_wh = 0.0
        self._pv_ws = 0.0
        self._pvm_ws = 0.0  # measured PV (W x s)
        self._pv_s = 0.0
        self._battery_ws = 0.0
        self._battery_s = 0.0
        self._measured_s = 0.0
        self._last_phases: tuple[tuple[float, ...], tuple[float, ...]] | None = None
        self._phase_house_ws: list[float] = []
        self._phase_pv_ws: list[float] = []
        self._last_grid_phases: tuple[tuple[float, ...], tuple[float, ...]] | None = (
            None
        )
        self._grid_ws: list[float] = []  # net grid W x s per phase
        self._amp_s: list[float] = []  # A x s per phase
        self._q_s: list[float] = []  # reactive W (at 230 V) x s per phase
        self._grid_s = 0.0
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
        """Stop the boundary timer and write records to disk (with the sums
        of the running interval up to now)."""
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None
        if self._interval_start is not None and self._last_time is not None:
            self._integrate(dt_util.utcnow())
        await self._store.async_save(self._data(running=True))

    async def async_save_running(self) -> None:
        """Write the records and the running interval up to now (Home
        Assistant stops: config entries are not unloaded then)."""
        if self._interval_start is not None and self._last_time is not None:
            self._integrate(dt_util.utcnow())
        await self._store.async_save(self._data(running=True))

    async def async_load(self) -> None:
        """Load stored records."""
        if (data := await self._store.async_load()) is not None:
            records = data.get("records", [])
            self.records = [r for r in records if _valid(r)]
            running = data.get("running") or {}
            start = dt_util.parse_datetime(running.get("start") or "")
            if (
                start is not None
                and running.get("minutes") == self.minutes
                and start == self.interval_start(dt_util.utcnow())
            ):
                # The same interval still runs: go on with its sums (the
                # time in between counts as not measured).
                self._interval_start = start
                for name in RUNNING_SUMS:
                    if name in running:
                        setattr(self, name, running[name])
                if "_pvm_ws" not in running:  # saved by an older version
                    self._pvm_ws = self._pv_ws
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
        heating: float | None = None,
        temperature: float | None = None,
        zones: Mapping[str, tuple[float | None, ...]] | None = None,
        spike_wh: float = 0.0,
        grid_phases: tuple[tuple[float, ...], ...] | None = None,
        pv_measured: float | None = None,
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
        # What the inverters gave (``pv`` may be the potential when an
        # inverter held PV back): for the energy per day.
        self._last_pv_measured = pv_measured if pv_measured is not None else pv
        self._last_battery = battery
        self._last_phases = phases if phases and phases[0] else None
        self._last_heating = heating
        self._last_temp = temperature
        self._last_zones = zones
        self._last_grid_phases = (
            grid_phases
            if grid_phases and len(grid_phases[0]) == len(grid_phases[1])
            else None
        )
        self._spike_wh += spike_wh

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
                measured = round(self._pvm_ws / self._pv_s, 1)
                if abs(measured - record["pv_w"]) >= 1:  # PV held back
                    record["pv_measured_w"] = measured
            if self._battery_s > 0:
                record["battery_w"] = round(self._battery_ws / self._battery_s, 1)
            if self.vacation:
                record["vacation"] = True
            if self._heating_s > 0:
                record["heating_w"] = round(self._heating_ws / self._heating_s, 1)
            if self._temp_s > 0:
                record["temp_c"] = round(self._temp_cs / self._temp_s, 1)
            if zones := self._zone_record():
                record["zones"] = zones
            if self._spike_wh > 0:
                record["spike_w"] = round(
                    min(self._spike_wh * 3600 / self._measured_s, record["avg_w"]), 1
                )
            if self._phase_s > 0:
                record["phase_house_w"] = [
                    round(v / self._phase_s, 1) for v in self._phase_house_ws
                ]
                record["phase_pv_w"] = [
                    round(v / self._phase_s, 1) for v in self._phase_pv_ws
                ]
            if self._grid_s > 0:
                record["phase_grid_w"] = [
                    round(v / self._grid_s, 1) for v in self._grid_ws
                ]
                record["phase_a"] = [round(v / self._grid_s, 2) for v in self._amp_s]
                record["phase_q"] = [round(v / self._grid_s, 1) for v in self._q_s]
            self.records.append(record)
            self.prune(self._interval_start)
            # With the running interval (Home Assistant may be stopping).
            self._store.async_delay_save(lambda: self._data(running=True), SAVE_DELAY)
            _LOGGER.debug("Recorded %s", record)

        self._energy_ws = 0.0
        self._excluded_ws = 0.0
        self._heating_ws = 0.0
        self._heating_s = 0.0
        self._temp_cs = 0.0
        self._temp_s = 0.0
        self._zone_sums = {}
        self._spike_wh = 0.0
        self._pv_ws = 0.0
        self._pvm_ws = 0.0  # measured PV (W x s)
        self._pv_s = 0.0
        self._battery_ws = 0.0
        self._battery_s = 0.0
        self._measured_s = 0.0
        self._phase_house_ws = []
        self._phase_pv_ws = []
        self._grid_ws = []
        self._amp_s = []
        self._q_s = []
        self._grid_s = 0.0
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
                self._pvm_ws += (
                    self._last_pv_measured
                    if self._last_pv_measured is not None
                    else self._last_pv
                ) * seconds
                self._pv_s += seconds
            if self._last_heating is not None:
                self._heating_ws += self._last_heating * seconds
                self._heating_s += seconds
            if self._last_temp is not None:
                self._temp_cs += self._last_temp * seconds
                self._temp_s += seconds
            for zone, values in (self._last_zones or {}).items():
                sums = self._zone_sums.setdefault(zone, [0.0] * 6)
                for i, value in enumerate(values[:3]):
                    if value is not None:
                        sums[2 * i] += value * seconds
                        sums[2 * i + 1] += seconds
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
            if self._last_grid_phases is not None:
                grid, amps = self._last_grid_phases[:2]
                volts = (
                    self._last_grid_phases[2] if len(self._last_grid_phases) > 2 else ()
                )
                if not (
                    len(self._grid_ws)
                    == len(self._amp_s)
                    == len(self._q_s)
                    == len(grid)
                ):
                    # A new phase count, or sums saved by an older version.
                    self._grid_ws = [0.0] * len(grid)
                    self._amp_s = [0.0] * len(grid)
                    self._q_s = [0.0] * len(grid)
                    self._grid_s = 0.0
                for i, (watts, current) in enumerate(zip(grid, amps, strict=True)):
                    self._grid_ws[i] += watts * seconds
                    self._amp_s[i] += current * seconds
                    volt = volts[i] if i < len(volts) else None
                    self._q_s[i] += reactive_w(watts, current, volt) * seconds
                self._grid_s += seconds
        self._last_time = when

    def _zone_record(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for zone, sums in self._zone_sums.items():
            if not sums[1]:
                continue  # no power: nothing to learn from
            values = {"w": round(sums[0] / sums[1], 1)}
            for key, i in (("in", 2), ("out", 4)):
                if sums[i + 1]:
                    values[key] = round(sums[i] / sums[i + 1], 1)
            out[zone] = values
        return out

    def _hour_averages(
        self, since: datetime, until: datetime, *, running: bool
    ) -> dict[datetime, tuple[dict[str, float], dict[str, float]]]:
        """Per clock hour in [since, until): the average W of what was
        measured (house, pv, excluded, battery) and of each zone; with
        ``running`` the interval running now counts too."""
        keys = ("house", "pv", "excluded", "battery")
        hours: dict[datetime, list[Any]] = {}

        def add(
            start: datetime,
            seconds: float,
            values: dict[str, float],
            zones: dict[str, float],
        ) -> None:
            if seconds <= 0 or not since <= start < until:
                return
            hour = start.replace(minute=0, second=0, microsecond=0)
            acc = hours.setdefault(hour, [dict.fromkeys(keys, 0.0), 0.0, {}])
            for key in keys:
                acc[0][key] += values.get(key, 0.0) * seconds
            acc[1] += seconds
            for zone, watts in zones.items():
                acc[2][zone] = acc[2].get(zone, 0.0) + watts * seconds

        for record in self.records:
            start = dt_util.parse_datetime(str(record["start"]))
            if start is None:
                continue
            add(
                dt_util.as_utc(start),
                record["minutes"] * 60 * record.get("coverage", 1.0),
                {
                    "house": record["avg_w"],
                    # What was produced (the potential stays for learning).
                    "pv": record.get("pv_measured_w", record.get("pv_w", 0.0)),
                    "excluded": record.get("excluded_w", 0.0),
                    "battery": record.get("battery_w", 0.0),
                },
                {
                    z: v.get("w", 0.0)
                    for z, v in (record.get("zones") or {}).items()
                    if isinstance(v, dict)
                },
            )
        if running and self._measured_s and self._interval_start is not None:
            add(
                self._interval_start,
                self._measured_s,
                {
                    "house": self._energy_ws / self._measured_s,
                    "pv": self._pvm_ws / self._pv_s if self._pv_s else 0.0,
                    "excluded": self._excluded_ws / self._measured_s,
                    "battery": self._battery_ws / self._battery_s
                    if self._battery_s
                    else 0.0,
                },
                {
                    z: sums[0] / sums[1]
                    for z, sums in self._zone_sums.items()
                    if sums[1]
                },
            )
        return {
            hour: (
                {k: v / seconds for k, v in sums.items()},
                {z: ws / seconds for z, ws in zone_sums.items()},
            )
            for hour, (sums, seconds, zone_sums) in hours.items()
        }

    def day_energy(
        self, start: datetime, end: datetime, now: datetime
    ) -> dict[str, Any]:
        """Energy (Wh) from ``start`` to ``end`` (a local day), per clock hour:
        the average of what was measured in that hour over the whole hour (the
        current one: until now), so a gap such as a restart counts at that
        hour's average, as in the hourly charts. Grid import/export and
        battery charge/discharge from the net per hour; ``flows`` = who
        supplied whom (solar first to the house, then excluded devices, the
        battery and the grid; then the battery; the grid the rest)."""
        now = dt_util.as_utc(now)
        total = dict.fromkeys(
            (
                "house",
                "pv",
                "excluded",
                "charged",
                "discharged",
                "imported",
                "exported",
            ),
            0.0,
        )
        zones: dict[str, float] = {}
        flows: dict[str, float] = {}
        averages = self._hour_averages(start, end, running=start <= now < end)
        for hour, (avg, zone_avg) in averages.items():
            # The part of the clock hour inside the day and before now (a
            # day may start on a half hour: UTC+5:30).
            span = (
                min(hour + timedelta(hours=1), end, now) - max(hour, start)
            ).total_seconds() / 3600  # h
            if span <= 0:
                continue
            grid = avg["house"] - avg["pv"] + avg["excluded"] + avg["battery"]
            total["house"] += avg["house"] * span
            total["pv"] += avg["pv"] * span
            total["excluded"] += avg["excluded"] * span
            total["charged"] += max(avg["battery"], 0.0) * span
            total["discharged"] += max(-avg["battery"], 0.0) * span
            total["imported"] += max(grid, 0.0) * span
            total["exported"] += max(-grid, 0.0) * span
            for zone, watts in zone_avg.items():
                zones[zone] = zones.get(zone, 0.0) + watts * span
            supply = {
                "pv": max(avg["pv"], 0.0),
                "battery": max(-avg["battery"], 0.0),
                "grid": max(grid, 0.0),
            }
            demand = {
                "house": max(avg["house"], 0.0),
                "excluded": max(avg["excluded"], 0.0),
                "battery": max(avg["battery"], 0.0),
                "grid": max(-grid, 0.0),
            }
            for source in supply:
                for sink in demand:
                    if source == sink:
                        continue
                    watts = min(supply[source], demand[sink])
                    if watts > 0:
                        flows[f"{source}-{sink}"] = (
                            flows.get(f"{source}-{sink}", 0.0) + watts * span
                        )
                        supply[source] -= watts
                        demand[sink] -= watts
        result: dict[str, Any] = {k: round(v) for k, v in total.items()}
        result["zones"] = {k: round(v) for k, v in zones.items()}
        result["flows"] = {k: round(v) for k, v in flows.items() if v >= 1}
        return result

    def today_energy(self, now: datetime) -> dict[str, Any]:
        """Energy since local midnight (Wh), incl. the interval running now."""
        start = dt_util.start_of_local_day(dt_util.as_local(now))
        return self.day_energy(
            dt_util.as_utc(start), dt_util.as_utc(start + timedelta(days=1)), now
        )

    def energy_days(self, now: datetime) -> list[dict[str, Any]]:
        """The energy of every earlier local day in the history, newest
        first, each with its ``date`` (YYYY-MM-DD)."""
        if not self.records:
            return []
        first = dt_util.parse_datetime(str(self.records[0]["start"]))
        if first is None:
            return []
        day = dt_util.start_of_local_day(dt_util.as_local(first))
        today = dt_util.start_of_local_day(dt_util.as_local(now))
        out: list[dict[str, Any]] = []
        while day < today:
            following = dt_util.start_of_local_day(day + timedelta(hours=26))
            energy = self.day_energy(
                dt_util.as_utc(day), dt_util.as_utc(following), now
            )
            if energy["house"]:
                out.append({"date": day.date().isoformat(), **energy})
            day = following
        return out[::-1]

    def prune(self, now: datetime) -> None:
        """Drop records older than the retention period."""
        cutoff = (dt_util.as_utc(now) - HISTORY_RETENTION).isoformat()
        self.records = [r for r in self.records if r["start"] >= cutoff]

    def _data(self, running: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {"records": self.records}
        if running and self._interval_start is not None and self._measured_s > 0:
            data["running"] = {
                "start": self._interval_start.isoformat(),
                "minutes": self.minutes,
                **{name: getattr(self, name) for name in RUNNING_SUMS},
            }
        return data
