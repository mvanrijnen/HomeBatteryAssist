"""Import past house consumption from Home Assistant's long-term statistics.

Reconstructs the house consumption with the same formula as the live
measurement (grid + PV - excluded - battery charging), from the recorder
statistics of the configured sensors; or takes over a ready-made consumption
sensor (``source_entity``). Uses 5-minute statistics where the recorder still
has them (about 10 days) and hourly statistics before that.

Own measurements always win: imported records never overwrite them (unless
``replace``). Imported records carry ``source: "import"``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..const import NOMINAL_VOLTAGE, SIGN_DISCHARGING_POSITIVE
from .consumption import ConsumptionHistory, ConsumptionRecord

_LOGGER = logging.getLogger(__name__)

SHORT_TERM = timedelta(minutes=5)
LONG_TERM = timedelta(hours=1)
SHORT_TERM_KEPT = timedelta(days=10)  # recorder default for 5-minute statistics
SOURCE_IMPORT = "import"

type Series = dict[str, dict[datetime, float]]  # statistic id -> start -> mean (W)


@dataclass(frozen=True, slots=True)
class Term:
    """One sensor in the formula: ``weight * value`` (``absolute``: abs first)."""

    entity_id: str
    weight: float
    absolute: bool = False
    required: bool = False  # grid sensors: without them no value


def formula_terms(
    entry: ConfigEntry, battery_power_history: Iterable[str] = ()
) -> list[Term]:
    """The live house consumption formula as weighted sensors."""
    data = entry.runtime_data
    terms: list[Term] = []
    for main, ret in data.measurements.grid_phases:
        terms.append(Term(main, 1.0, required=True))
        if ret:
            terms.append(Term(ret, -1.0, absolute=True, required=True))
    terms += [Term(e, 1.0, absolute=True) for e in data.measurements.pv_sensors]
    terms += [Term(e, -1.0, absolute=True) for e in data.measurements.excluded_sensors]
    for index, battery in enumerate(data.batteries.configs):
        # house -= charging; charging = -sensor if the sensor is + discharging.
        weight = 1.0 if battery.power_sign == SIGN_DISCHARGING_POSITIVE else -1.0
        terms.append(Term(battery.power_sensor, weight))
        if index == 0:  # older sensors of the (first) battery, same sign
            terms += [Term(e, weight) for e in battery_power_history]
    return terms


def combine(
    terms: list[Term], series: Series, starts: Iterable[datetime]
) -> dict[datetime, float]:
    """House consumption per period start; periods without grid data are skipped.

    Several sensors of the same battery (current + history) never overlap in
    practice; their values are simply added.
    """
    result: dict[datetime, float] = {}
    for start in starts:
        total = 0.0
        complete = True
        for term in terms:
            value = series.get(term.entity_id, {}).get(start)
            if value is None:
                if term.required:
                    complete = False
                    break
                continue
            total += term.weight * (abs(value) if term.absolute else value)
        if complete:
            result[start] = max(round(total, 1), 0.0)
    return result


def to_records(
    values: dict[datetime, float],
    period: timedelta,
    minutes: int,
    excluded: dict[datetime, float] | None = None,
) -> list[ConsumptionRecord]:
    """Group period values into intervals of ``minutes`` (never finer than ``period``).

    ``excluded``: power of excluded devices per period, averaged alongside.
    """
    step = max(timedelta(minutes=minutes), period)
    seconds = step.total_seconds()
    buckets: dict[datetime, list[tuple[float, float]]] = {}
    for start, value in values.items():
        ts = start.timestamp()
        bucket = dt_util.utc_from_timestamp(ts - ts % seconds)
        other = (excluded or {}).get(start, 0.0)
        buckets.setdefault(bucket, []).append((value, other))
    per_bucket = step / period
    records: list[ConsumptionRecord] = []
    for start, vals in sorted(buckets.items()):
        record = ConsumptionRecord(
            start=start.isoformat(),
            minutes=int(seconds // 60),
            avg_w=round(sum(v for v, _ in vals) / len(vals), 1),
            coverage=round(min(len(vals) / per_bucket, 1.0), 3),
            source=SOURCE_IMPORT,
        )
        if (other := sum(o for _, o in vals)) > 0:
            record["excluded_w"] = round(other / len(vals), 1)
        records.append(record)
    return records


def merge(
    history: ConsumptionHistory,
    imported: list[ConsumptionRecord],
    *,
    replace: bool,
) -> tuple[int, int]:
    """Merge imported records into the history; returns (added, skipped).

    Earlier imported records are always replaced by the new import. Where an
    imported record overlaps an own measurement, the own one is kept, unless
    ``replace`` (then the imported one wins).
    """

    def span(record: ConsumptionRecord) -> tuple[datetime, datetime]:
        start = dt_util.parse_datetime(record["start"])
        assert start is not None
        return start, start + timedelta(minutes=record["minutes"])

    def overlaps(
        record: ConsumptionRecord, others: list[tuple[datetime, datetime]]
    ) -> bool:
        start, end = span(record)
        return any(start < o_end and end > o_start for o_start, o_end in others)

    own = [r for r in history.records if r.get("source") != SOURCE_IMPORT]
    if replace:
        imported_spans = [span(r) for r in imported]
        kept = [r for r in own if not overlaps(r, imported_spans)]
        added, skipped = imported, len(own) - len(kept)
    else:
        own_spans = [span(r) for r in own]
        kept = own
        added = [r for r in imported if not overlaps(r, own_spans)]
        skipped = len(imported) - len(added)
    history.records = sorted([*kept, *added], key=lambda r: r["start"])
    return len(added), skipped


async def _async_fetch(
    hass: HomeAssistant,
    entity_ids: set[str],
    start: datetime,
    end: datetime,
    period: str,
) -> Series:
    """Mean per period from the recorder, converted to W (A via nominal voltage)."""
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import (
        get_metadata,
        statistics_during_period,
    )

    recorder = get_instance(hass)
    metadata = await recorder.async_add_executor_job(
        lambda: get_metadata(hass, statistic_ids=entity_ids)
    )
    rows = await recorder.async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        end,
        entity_ids,
        period,
        {"power": "W"},
        {"mean"},
    )
    series: Series = {}
    for entity_id, entity_rows in rows.items():
        unit = metadata.get(entity_id, (None, {}))[1].get(
            "statistics_unit_of_measurement"
        )
        factor = (
            NOMINAL_VOLTAGE
            if unit == "A"
            else 0.001 * NOMINAL_VOLTAGE
            if unit == "mA"
            else 1.0
        )
        series[entity_id] = {
            dt_util.utc_from_timestamp(row["start"]): row["mean"] * factor
            for row in entity_rows
            if row.get("mean") is not None
        }
    return series


async def async_import_history(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    days: int,
    source_entity: str | None = None,
    battery_power_history: Iterable[str] = (),
    replace: bool = False,
) -> dict[str, Any]:
    """Import ``days`` of past house consumption into the consumption history."""
    history: ConsumptionHistory = entry.runtime_data.history
    terms = (
        [Term(source_entity, 1.0, required=True)]
        if source_entity
        else formula_terms(entry, battery_power_history)
    )
    excluded_terms = [
        Term(e, 1.0, absolute=True)
        for e in entry.runtime_data.measurements.excluded_sensors
    ]
    entity_ids = {t.entity_id for t in [*terms, *excluded_terms]}
    now = dt_util.utcnow()
    start = history.interval_start(now - timedelta(days=days))
    short_start = max(start, history.interval_start(now - SHORT_TERM_KEPT))
    # Only completed periods.
    end_short = history.interval_start(now)

    records: list[ConsumptionRecord] = []
    if start < short_start:
        series = await _async_fetch(hass, entity_ids, start, short_start, "hour")
        starts = sorted({s for values in series.values() for s in values})
        records += to_records(
            combine(terms, series, starts),
            LONG_TERM,
            history.minutes,
            combine(excluded_terms, series, starts),
        )
    series = await _async_fetch(hass, entity_ids, short_start, end_short, "5minute")
    starts = sorted({s for values in series.values() for s in values})
    records += to_records(
        combine(terms, series, starts),
        SHORT_TERM,
        history.minutes,
        combine(excluded_terms, series, starts),
    )

    added, skipped = merge(history, records, replace=replace)
    history.prune(now)
    await history.async_save()
    summary = {
        "imported": added,
        # replace=False: imported records skipped for own measurements;
        # replace=True: own measurements replaced by imported records.
        "overlapping_own_measurements": skipped,
        "first": records[0]["start"] if records else None,
        "last": records[-1]["start"] if records else None,
        "sensors": sorted(entity_ids),
    }
    _LOGGER.info("Imported consumption history: %s", summary)
    return summary
