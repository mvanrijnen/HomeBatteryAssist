"""Websocket commands for the dashboard's *Occasional consumption* dialog.

Add, change and remove energy adjustments of the consumption forecast per
day (``engine/forecast/user_adjustments.py``): an amount of energy (kWh) on a
day, optionally within a time window (local time; without one the whole
day), either extra or part of the learned consumption of that day. Other
adjustments (from the ``adjust_forecast`` action) are listed and can be
removed, not changed here.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from ..services import describe_change


def _loaded(hass: HomeAssistant) -> Any:
    return next(
        (
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED
        ),
        None,
    )


def adjustment_rows(entry: Any) -> list[dict[str, Any]]:
    """The adjustments for the dashboard (local day and window)."""
    rows = []
    for a in sorted(
        entry.runtime_data.forecast.adjustments.items, key=lambda a: a["start"]
    ):
        start = dt_util.parse_datetime(a["start"])
        end = dt_util.parse_datetime(a["end"])
        if start is None or end is None:
            continue
        local_start, local_end = dt_util.as_local(start), dt_util.as_local(end)
        whole_day = (
            local_start.time() == time(0)
            and local_end.time() == time(0)
            and local_end.date() == local_start.date() + timedelta(days=1)
        )
        rows.append(
            {
                "id": a["id"],
                "name": a["name"],
                "kind": a["kind"],
                "value": a["value"],
                "part": bool(a.get("part")),
                "date": local_start.date().isoformat(),
                "from": None if whole_day else local_start.strftime("%H:%M"),
                "until": None if whole_day else local_end.strftime("%H:%M"),
                "start": a["start"],
                "end": a["end"],
            }
        )
    return rows


def _period(day: date, start: str | None, end: str | None) -> tuple[datetime, datetime]:
    """The period in UTC: the window on ``day`` (an end at or before the
    start is the next day), or the whole local day."""
    tz = dt_util.get_default_time_zone()
    if not start or not end:
        begin = datetime.combine(day, time(0), tz)
        return dt_util.as_utc(begin), dt_util.as_utc(
            datetime.combine(day + timedelta(days=1), time(0), tz)
        )
    t1, t2 = time.fromisoformat(start), time.fromisoformat(end)
    begin = datetime.combine(day, t1, tz)
    finish = datetime.combine(day + timedelta(days=1 if t2 <= t1 else 0), t2, tz)
    return dt_util.as_utc(begin), dt_util.as_utc(finish)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/adjustment_save",
        vol.Optional("adjustment_id"): str,
        vol.Optional("name"): vol.All(str, vol.Length(max=60)),
        vol.Required("date"): str,
        vol.Optional("from"): vol.Any(None, str),
        vol.Optional("until"): vol.Any(None, str),
        vol.Required("energy_kwh"): vol.All(
            vol.Coerce(float), vol.Range(min=-500, max=500)
        ),
        vol.Optional("part", default=False): bool,
    }
)
@websocket_api.async_response
async def websocket_adjustment_save(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Add or change an energy adjustment."""
    if (entry := _loaded(hass)) is None:
        connection.send_error(
            msg["id"], "not_loaded", "HomeBatteryAssist is not loaded"
        )
        return
    try:
        day = date.fromisoformat(msg["date"])
        start, end = _period(day, msg.get("from"), msg.get("until"))
    except ValueError:
        connection.send_error(msg["id"], "invalid", "invalid date or time")
        return
    has_window = bool(msg.get("from") and msg.get("until"))
    if msg["part"] and not has_window:
        # Part of the day's consumption over the whole day changes nothing.
        connection.send_error(msg["id"], "invalid", "part needs a time window")
        return
    if end <= dt_util.utcnow():
        connection.send_error(msg["id"], "invalid", "the period is over")
        return
    data = entry.runtime_data
    known = {
        a["id"] for a in data.forecast.adjustments.items if a["kind"] == "energy_kwh"
    }
    if (
        adjustment_id := msg.get("adjustment_id")
    ) is not None and adjustment_id not in known:
        connection.send_error(msg["id"], "not_found", "adjustment not found")
        return
    dutch = (hass.config.language or "").startswith("nl")
    name = (msg.get("name") or "").strip() or (
        "Extra verbruik" if dutch else "Extra consumption"
    )
    adjustment = await data.forecast.adjustments.async_add(
        name, start, end, "energy_kwh", msg["energy_kwh"], msg["part"], adjustment_id
    )
    data.decisions.async_log(
        "forecast",
        "forecast_adjusted",
        name=adjustment["name"],
        change=describe_change(adjustment, hass.config.language),
        start=start,
        end=end,
    )
    # No recalculation here: the dashboard recalculates once when the dialog
    # closes after a change (action recalculate).
    connection.send_result(msg["id"], {"adjustments": adjustment_rows(entry)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/adjustment_delete",
        vol.Required("adjustment_id"): str,
    }
)
@websocket_api.async_response
async def websocket_adjustment_delete(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Remove an adjustment."""
    if (entry := _loaded(hass)) is None:
        connection.send_error(
            msg["id"], "not_loaded", "HomeBatteryAssist is not loaded"
        )
        return
    data = entry.runtime_data
    count = await data.forecast.adjustments.async_clear(ids=[msg["adjustment_id"]])
    if count:
        data.decisions.async_log(
            "forecast", "forecast_adjustments_cleared", count=count
        )
    connection.send_result(msg["id"], {"adjustments": adjustment_rows(entry)})
