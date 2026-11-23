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
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from ...const import DOMAIN, NOMINAL_VOLTAGE, SIGN_DISCHARGING_POSITIVE
from .consumption_history import ConsumptionHistory, ConsumptionRecord

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
    # Required for the periods of a series that has this sensor at all (PV)
    required_when_known: bool = False
    # Required between its first and last statistic (a battery or excluded
    # device: before it existed it was 0 W; a gap in between is unknown,
    # as live, not 0 W)
    required_within: bool = False


def formula_terms(
    entry: ConfigEntry, battery_power_history: Iterable[str] = ()
) -> list[Term]:
    """The live house consumption formula as weighted sensors."""
    data = entry.runtime_data
    if data.measurements.direct is not None:
        # A meter read directly has no history in Home Assistant.
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="import_direct_meter"
        )
    if data.measurements.pv_meters:
        # PV read directly has no history either: without it every sunny
        # period would be imported as (almost) no house consumption.
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="import_direct_pv"
        )
    terms: list[Term] = []
    for main, ret in data.measurements.grid_phases:
        terms.append(Term(main, 1.0, required=True))
        if ret:
            terms.append(Term(ret, -1.0, absolute=True, required=True))
    # PV is required where its statistics exist: a period without them would
    # count as (almost) no house consumption in the sun.
    terms += [
        Term(e, 1.0, absolute=True, required_when_known=True)
        for e in data.measurements.pv_sensors
    ]
    terms += [
        Term(e, -1.0, absolute=True, required_within=True)
        for e in data.measurements.excluded_sensors
    ]
    real = [b for b in data.batteries.configs if not b.virtual]
    for index, battery in enumerate(real):
        if not battery.power_sensor:
            continue  # read directly only: no sensor history to import
        # house -= charging; charging = -sensor if the sensor is + discharging.
        weight = 1.0 if battery.power_sign == SIGN_DISCHARGING_POSITIVE else -1.0
        terms.append(Term(battery.power_sensor, weight, required_within=True))
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
    spans = {
        t.entity_id: (min(known), max(known))
        for t in terms
        if t.required_within and (known := series.get(t.entity_id))
    }
    for start in starts:
        total = 0.0
        complete = True
        for term in terms:
            value = series.get(term.entity_id, {}).get(start)
            if value is None:
                span = spans.get(term.entity_id) if term.required_within else None
                if (
                    term.required
                    or (term.required_when_known and series.get(term.entity_id))
                    or (span is not None and span[0] <= start <= span[1])
                ):
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
    pv: dict[datetime, float] | None = None,
    battery: dict[datetime, float] | None = None,
) -> list[ConsumptionRecord]:
    """Group period values into intervals of ``minutes`` (never finer than ``period``).

    ``excluded`` / ``pv``: power of excluded devices / PV per period, averaged
    alongside.
    """
    step = max(timedelta(minutes=minutes), period)
    seconds = step.total_seconds()
    buckets: dict[datetime, list[tuple[float, float, float | None, float | None]]] = {}
    for start, value in values.items():
        ts = start.timestamp()
        bucket = dt_util.utc_from_timestamp(ts - ts % seconds)
        other = (excluded or {}).get(start, 0.0)
        buckets.setdefault(bucket, []).append(
            (
                value,
                other,
                pv.get(start) if pv is not None else None,
                battery.get(start) if battery is not None else None,
            )
        )
    per_bucket = step / period
    records: list[ConsumptionRecord] = []
    for start, vals in sorted(buckets.items()):
        record = ConsumptionRecord(
            start=start.isoformat(),
            minutes=int(seconds // 60),
            avg_w=round(sum(v[0] for v in vals) / len(vals), 1),
            coverage=round(min(len(vals) / per_bucket, 1.0), 3),
            source=SOURCE_IMPORT,
        )
        if (other := sum(v[1] for v in vals)) > 0:
            record["excluded_w"] = round(other / len(vals), 1)
        if pv_values := [v[2] for v in vals if v[2] is not None]:
            record["pv_w"] = round(sum(pv_values) / len(pv_values), 1)
        if battery_values := [v[3] for v in vals if v[3] is not None]:
            record["battery_w"] = round(sum(battery_values) / len(battery_values), 1)
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
    # Earlier imported records outside the new import stay (a short import
    # to fill a gap must not delete the rest).
    new_spans = [span(r) for r in imported]
    earlier = [
        r
        for r in history.records
        if r.get("source") == SOURCE_IMPORT and not overlaps(r, new_spans)
    ]
    if replace:
        imported_spans = [span(r) for r in imported]
        kept = [r for r in own if not overlaps(r, imported_spans)]
        added, skipped = imported, len(own) - len(kept)
    else:
        own_spans = [span(r) for r in own]
        kept = own
        added = [r for r in imported if not overlaps(r, own_spans)]
        skipped = len(imported) - len(added)
    history.records = sorted([*kept, *earlier, *added], key=lambda r: r["start"])
    return len(added), skipped


def _pv_series(
    terms: list[Term], series: Series, starts: list[datetime]
) -> dict[datetime, float] | None:
    """Measured PV per period (only where a PV sensor has a value)."""
    if not terms:
        return None
    return {
        start: value
        for start, value in combine(
            [Term(t.entity_id, 1.0, absolute=True, required=True) for t in terms[:1]]
            + terms[1:],
            series,
            starts,
        ).items()
    }


def _optional_series(
    terms: list[Term], series: Series, starts: list[datetime]
) -> dict[datetime, float] | None:
    """Sum of ``terms`` per period, only where at least one has a value."""
    if not terms:
        return None
    result: dict[datetime, float] = {}
    for start in starts:
        values = [
            t.weight * v
            for t in terms
            if (v := series.get(t.entity_id, {}).get(start)) is not None
        ]
        if values:
            result[start] = round(sum(values), 1)
    return result


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
    battery_ids = {b.power_sensor for b in entry.runtime_data.batteries.configs} | set(
        battery_power_history
    )
    # In the formula a battery term adds discharging; + charging is the negative.
    battery_terms = [
        Term(t.entity_id, -t.weight) for t in terms if t.entity_id in battery_ids
    ]
    pv_terms = [
        Term(e, 1.0, absolute=True) for e in entry.runtime_data.measurements.pv_sensors
    ]
    entity_ids = {t.entity_id for t in [*terms, *excluded_terms, *pv_terms]}
    now = dt_util.utcnow()
    start = history.interval_start(now - timedelta(days=days))
    # On a whole hour: the hourly rows before it must not overlap the
    # 5-minute ones (an hourly row covers its whole hour).
    short_start = max(
        start,
        history.interval_start(now - SHORT_TERM_KEPT).replace(
            minute=0, second=0, microsecond=0
        ),
    )
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
            _pv_series(pv_terms, series, starts),
            _optional_series(battery_terms, series, starts),
        )
    series = await _async_fetch(hass, entity_ids, short_start, end_short, "5minute")
    starts = sorted({s for values in series.values() for s in values})
    records += to_records(
        combine(terms, series, starts),
        SHORT_TERM,
        history.minutes,
        combine(excluded_terms, series, starts),
        _pv_series(pv_terms, series, starts),
        _optional_series(battery_terms, series, starts),
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
