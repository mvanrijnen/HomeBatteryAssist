"""Fill in the outdoor temperature of past history records (optional).

When an outdoor temperature sensor is set up, the records that have no
``temp_c`` yet get it from Home Assistant's long-term statistics of that
sensor (hourly means), so the temperature effect can be learned right away
instead of after a week. Only reads the recorder; records that already have
a temperature are left alone.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..sources.weather import valid_temperature
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
