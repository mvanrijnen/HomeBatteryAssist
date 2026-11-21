"""Websocket command for the dashboard's *Charge the car* dialog.

Advice only: when to switch the car's charging on (and off) to charge an
amount of energy within a period at the lowest expected cost
(``engine/planning/ev_advice.py``). Nothing is switched.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from ..engine.planning.ev_advice import advise, slots_from_plan
from .adjustments_ws import _loaded


def _local(text: str) -> datetime:
    """A local date and time from the dialog (``YYYY-MM-DDTHH:MM``, in Home
    Assistant's time zone; one with a zone as it is) in UTC."""
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_util.get_default_time_zone())
    return dt_util.as_utc(value)


def _iso(value: datetime | None) -> str | None:
    return dt_util.as_local(value).isoformat() if value is not None else None


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/ev_advice",
        vol.Required("kwh"): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=200)),
        vol.Required("power_kw"): vol.All(
            vol.Coerce(float), vol.Range(min=0.5, max=50)
        ),
        vol.Required("start"): str,
        vol.Required("end"): str,
    }
)
@websocket_api.async_response
async def websocket_ev_advice(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The cheapest block to charge the car within the period."""
    if (entry := _loaded(hass)) is None:
        connection.send_error(
            msg["id"], "not_loaded", "HomeBatteryAssist is not loaded"
        )
        return
    try:
        start, end = _local(msg["start"]), _local(msg["end"])
    except ValueError:
        connection.send_error(msg["id"], "invalid", "invalid date or time")
        return
    data = entry.runtime_data.forecast.data
    plan = data.selected_plan if data is not None else None
    advice = advise(
        slots_from_plan(plan),
        msg["kwh"],
        msg["power_kw"] * 1000,
        start,
        end,
        dt_util.utcnow(),
    )
    connection.send_result(
        msg["id"],
        {
            "start": _iso(advice.start),
            "end": _iso(advice.end),
            "kwh": advice.kwh,
            "cost": advice.cost,
            "avg_price": None
            if advice.avg_price is None
            else round(advice.avg_price, 4),
            "sun_kwh": advice.sun_kwh,
            "now_cost": advice.now_cost,
            "now_start": _iso(advice.now_start),
            "prices_until": _iso(advice.prices_until),
            "reason": advice.reason,
            "currency": hass.config.currency,
        },
    )
