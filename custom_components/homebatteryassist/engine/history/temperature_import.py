"""Fill in past history records from Home Assistant's statistics (optional).

- **Outdoor temperature**: when an outdoor temperature sensor is set up, the
  records without ``temp_c`` get its hourly mean.
- **Zones** (heating/cooling devices): the records without that zone get its
  power, room and outdoor temperature (hourly means of its sensors), so a
  zone added today is learned right away from weeks of history.

So the temperature effect is learned at once instead of after a week. Only
reads the recorder (long-term statistics); what is already in a record is
left alone.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..measure.heating_zones import HeatingZone
from ..sources.weather import valid_indoor, valid_temperature
from .consumption_history import ConsumptionHistory

_LOGGER = logging.getLogger(__name__)


def fill_temperatures(
    history: ConsumptionHistory, hourly: Mapping[datetime, float]
) -> int:
    """Give records without ``temp_c`` the mean of their hour; returns how many."""
    filled = 0
    for record in history.records:
        if "temp_c" in record:
            continue
        start = dt_util.parse_datetime(str(record["start"]))
        if start is None:
            continue
        hour = dt_util.as_utc(start).replace(minute=0, second=0, microsecond=0)
        if (temp := valid_temperature(hourly.get(hour))) is not None:
            record["temp_c"] = round(temp, 1)
            filled += 1
    return filled


def _hour(record: Mapping) -> datetime | None:
    start = dt_util.parse_datetime(str(record.get("start")))
    if start is None:
        return None
    return dt_util.as_utc(start).replace(minute=0, second=0, microsecond=0)


def fill_zone(
    history: ConsumptionHistory,
    zone_id: str,
    power: Mapping[datetime, float],
    indoor: Mapping[datetime, float] | None = None,
    outdoor: Mapping[datetime, float] | None = None,
) -> int:
    """Give records without ``zone_id`` its hourly power (W) and, when known,
    room (``in``) and outdoor (``out``) temperature; returns how many."""
    filled = 0
    for record in history.records:
        zones = record.get("zones") or {}
        if zone_id in zones or (hour := _hour(record)) is None:
            continue
        watts = power.get(hour)
        if watts is None or not math.isfinite(watts) or watts < 0:
            continue
        values: dict[str, float] = {"w": round(watts, 1)}
        if (room := valid_indoor((indoor or {}).get(hour))) is not None:
            values["in"] = round(room, 1)
        if (out := valid_temperature((outdoor or {}).get(hour))) is not None:
            values["out"] = round(out, 1)
        record["zones"] = {**zones, zone_id: values}
        filled += 1
    return filled


async def _hourly_means(
    hass: HomeAssistant, entity_ids: set[str], start: datetime
) -> dict[str, dict[datetime, float]]:
    """Hourly means from the long-term statistics (°C, W)."""
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import (
        statistics_during_period,
    )

    rows = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        dt_util.utcnow(),
        entity_ids,
        "hour",
        {"temperature": "°C", "power": "W"},
        {"mean"},
    )
    return {
        entity_id: {
            dt_util.utc_from_timestamp(row["start"]): row["mean"]
            for row in rows.get(entity_id, [])
            if row.get("mean") is not None
        }
        for entity_id in entity_ids
    }


async def async_import_zones(
    hass: HomeAssistant, history: ConsumptionHistory, zones: Iterable[HeatingZone]
) -> int:
    """Fill in the zones from the statistics of their sensors."""
    zones = [
        z
        for z in zones
        if any(z.zone_id not in (r.get("zones") or {}) for r in history.records)
    ]
    if not zones or not history.records:
        return 0
    first = _hour(history.records[0])
    if first is None:
        return 0
    sensors = {
        s
        for z in zones
        for s in (z.power_sensor, z.indoor_sensor, z.outdoor_sensor)
        if s
    }
    means = await _hourly_means(hass, sensors, first - timedelta(hours=1))
    filled = 0
    for zone in zones:
        count = fill_zone(
            history,
            zone.zone_id,
            means.get(zone.power_sensor, {}),
            means.get(zone.indoor_sensor or "", {}),
            means.get(zone.outdoor_sensor or "", {}),
        )
        if count:
            _LOGGER.info("Zone %s filled in for %d history records", zone.name, count)
        filled += count
    if filled:
        await history.async_save()
    return filled


async def async_import_temperatures(
    hass: HomeAssistant, history: ConsumptionHistory, entity_id: str
) -> int:
    """Fill in ``temp_c`` from the statistics of ``entity_id`` (°C)."""
    if not history.records or all("temp_c" in r for r in history.records):
        return 0
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import (
        statistics_during_period,
    )

    first = dt_util.parse_datetime(str(history.records[0]["start"]))
    if first is None:
        return 0
    start = dt_util.as_utc(first) - timedelta(hours=1)
    rows = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        dt_util.utcnow(),
        {entity_id},
        "hour",
        {"temperature": "°C"},
        {"mean"},
    )
    hourly = {
        dt_util.utc_from_timestamp(row["start"]): row["mean"]
        for row in rows.get(entity_id, [])
        if row.get("mean") is not None
    }
    filled = fill_temperatures(history, hourly)
    if filled:
        await history.async_save()
        _LOGGER.info("Outdoor temperature filled in for %d history records", filled)
    return filled
