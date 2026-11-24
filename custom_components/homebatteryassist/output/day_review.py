"""Looking back at one earlier day: what happened against what was forecast.

Websocket ``homebatteryassist/day_review`` for the dashboard's flow chart:
per local day (up to 28 days back, as long as the history and the forecast
results are kept) the measured flows (house, PV, battery, excluded devices,
grid, per history interval), the forecast that was made for it (house and PV,
from the forecast accuracy results, at the chosen lead time), the prices
(published and as estimated then) and the battery plan against what the
batteries did (the plan check). Totals per day for the summary.

Lead time ``ahead``: the forecast made well before (6-24 h, else further
ahead, else nearer), the one the plan was mostly built on; ``late``: the last
one, shortly before (0-1 h, else the nearest there is).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from ..const import DOMAIN, NAME
from ..engine.evaluation.forecast_accuracy import BUCKET_KEYS, PV_CORRECTOR_KIND
from ..engine.evaluation.plan_check import followed_pct

# Lead times to take a forecast from, in order of preference.
LEADS: dict[str, tuple[str, ...]] = {
    "ahead": ("6-24h", "1-2d", "2-3d", "3-5d", "5d+", "1-6h", "0-1h"),
    "late": BUCKET_KEYS,
}


def _ms(when: datetime) -> int:
    return int(when.timestamp() * 1000)


def pick(pred: dict[str, float], lead: str) -> float | None:
    """The prediction at the preferred lead time that exists."""
    return next((pred[b] for b in LEADS[lead] if b in pred), None)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """Start and end (UTC) of a local day."""
    start = dt_util.start_of_local_day(day)
    end = dt_util.start_of_local_day(start + timedelta(hours=26))
    return dt_util.as_utc(start), dt_util.as_utc(end)


def day_review(
    records: list[dict[str, Any]],
    results: dict[str, list[dict[str, Any]]],
    plan_records: list[dict[str, Any]],
    pv_kind: str,
    day: date,
    lead: str,
) -> dict[str, Any]:
    """Everything the dashboard shows for one earlier day."""
    start, end = day_bounds(day)
    lo, hi = start.isoformat(), end.isoformat()

    def within(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [r for r in items if lo <= r["start"] < hi]

    measured = []
    totals = {"house": 0.0, "pv": 0.0, "imported": 0.0, "exported": 0.0}
    totals |= {"charged": 0.0, "discharged": 0.0, "excluded": 0.0}
    for r in within(records):
        when = dt_util.parse_datetime(r["start"])
        if when is None:
            continue
        house = float(r.get("avg_w") or 0.0)
        pv = float(r.get("pv_w") or 0.0)
        battery = float(r.get("battery_w") or 0.0)
        excluded = float(r.get("excluded_w") or 0.0)
        # house = grid + pv - excluded - battery
        grid = house - pv + excluded + battery
        hours = float(r.get("minutes") or 0) / 60 * float(r.get("coverage") or 1.0)
        measured.append(
            [
                _ms(when),
                round(house),
                round(pv),
                round(battery),
                round(excluded),
                round(grid),
            ]
        )
        totals["house"] += house * hours / 1000
        totals["pv"] += pv * hours / 1000
        totals["excluded"] += excluded * hours / 1000
        totals["imported"] += max(grid, 0.0) * hours / 1000
        totals["exported"] += max(-grid, 0.0) * hours / 1000
        totals["charged"] += max(battery, 0.0) * hours / 1000
        totals["discharged"] += max(-battery, 0.0) * hours / 1000

    def forecast(kind: str) -> list[list[Any]]:
        out = []
        for r in within(results.get(kind, [])):
            when = dt_util.parse_datetime(r["start"])
            value = pick(r.get("pred") or {}, lead)
            if when is not None and value is not None:
                out.append([_ms(when), round(value, 4), r.get("actual")])
        return out

    house_fc = forecast("consumption")
    pv_fc = forecast(pv_kind if results.get(pv_kind) else "pv")
    prices = forecast("price")

    def energy(rows: list[list[Any]], minutes: float) -> tuple[float, float] | None:
        """(forecast, measured) kWh over the slots that have both."""
        both = [(f, a) for _, f, a in rows if f is not None and a is not None]
        if not both:
            return None
        hours = minutes / 60
        return (
            round(sum(f for f, _ in both) * hours / 1000, 2),
            round(sum(a for _, a in both) * hours / 1000, 2),
        )

    def step_minutes(rows: list[list[Any]], default: float) -> float:
        if len(rows) < 2:
            return default
        return max((rows[1][0] - rows[0][0]) / 60000, 1.0)

    priced = [(f, a) for _, f, a in prices if f is not None and a is not None]
    plan = within(plan_records)
    return {
        "day": day.isoformat(),
        "start": _ms(start),
        "end": _ms(end),
        "lead": lead,
        # [time ms, house, PV, battery (+ charging), excluded, grid] W
        "measured": measured,
        # [time ms, forecast W, measured W] per forecast slot
        "house_forecast": house_fc,
        # [time ms, forecast W (Wh per hour), measured W] per hour
        "pv_forecast": pv_fc,
        # [time ms, estimated price, published price] per price slot
        "prices": prices,
        # [time ms, planned W, actual W] of the batteries
        "battery_plan": [
            [_ms(t), r.get("plan_w"), r.get("actual_w")]
            for r in plan
            if (t := dt_util.parse_datetime(r["start"])) is not None
        ],
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "house_vs": energy(house_fc, step_minutes(house_fc, 15)),
        "pv_vs": energy(pv_fc, step_minutes(pv_fc, 60)),
        "price_vs": (
            round(sum(f for f, _ in priced) / len(priced), 4),
            round(sum(a for _, a in priced) / len(priced), 4),
        )
        if priced
        else None,
        "followed": {
            "real": followed_pct(plan, "real"),
            "virtual": followed_pct(plan, "virtual"),
        },
    }


def first_day(records: list[dict[str, Any]]) -> str | None:
    """The oldest local day with history."""
    if not records:
        return None
    when = dt_util.parse_datetime(records[0]["start"])
    return dt_util.as_local(when).date().isoformat() if when else None


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/day_review",
        vol.Required("day"): str,
        vol.Optional("lead", default="ahead"): vol.In(tuple(LEADS)),
    }
)
@callback
def websocket_day_review(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """One earlier day: measured against forecast (dashboard flow chart)."""
    from .panel import _loaded_entry

    if (entry := _loaded_entry(hass)) is None:
        connection.send_error(msg["id"], "not_loaded", f"{NAME} is not loaded")
        return
    try:
        day = date.fromisoformat(msg["day"])
    except ValueError:
        connection.send_error(msg["id"], "invalid_day", "day must be YYYY-MM-DD")
        return
    data = entry.runtime_data
    forecast = data.forecast
    review = day_review(
        data.history.records,
        forecast.accuracy.results,
        data.plan_check.records,
        f"{PV_CORRECTOR_KIND}{forecast.pv_corrector_key}",
        day,
        msg["lead"],
    )
    review["first_day"] = first_day(data.history.records)
    review["price_unit"] = getattr(forecast, "price_unit", None)
    connection.send_result(msg["id"], review)
