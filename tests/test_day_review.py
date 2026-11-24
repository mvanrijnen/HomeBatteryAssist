"""Looking back at an earlier day: measured against forecast."""

from datetime import date

from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.output.day_review import (
    day_bounds,
    day_review,
    first_day,
    pick,
)


def test_pick_prefers_the_lead_time() -> None:
    pred = {"0-1h": 900.0, "6-24h": 700.0, "1-2d": 650.0}
    assert pick(pred, "ahead") == 700.0
    assert pick(pred, "late") == 900.0
    assert pick({"1-6h": 800.0}, "ahead") == 800.0  # nearest there is
    assert pick({}, "late") is None


def test_day_review(hass) -> None:
    day = date(2026, 11, 23)
    start, _end = day_bounds(day)
    t0 = start.isoformat()
    t1 = start.replace(minute=15).isoformat()
    before = start.replace(year=2025).isoformat()  # another day: left out
    records = [
        {"start": before, "minutes": 15, "avg_w": 9999.0},
        # 800 W house, 0 PV, battery discharging 400 W -> grid 400 W
        {
            "start": t0,
            "minutes": 15,
            "coverage": 1.0,
            "avg_w": 800.0,
            "pv_w": 0.0,
            "battery_w": -400.0,
            "excluded_w": 0.0,
        },
        # 400 W house, 1000 W PV, battery charging 600 W -> grid 0 W
        {
            "start": t1,
            "minutes": 15,
            "coverage": 1.0,
            "avg_w": 400.0,
            "pv_w": 1000.0,
            "battery_w": 600.0,
            "excluded_w": 0.0,
        },
    ]
    results = {
        "consumption": [
            {"start": t0, "actual": 800.0, "pred": {"6-24h": 600.0, "0-1h": 750.0}},
            {"start": t1, "actual": 400.0, "pred": {"6-24h": 600.0, "0-1h": 450.0}},
        ],
        "pv@x": [{"start": t0, "actual": 500.0, "pred": {"1-2d": 400.0}}],
        "price": [{"start": t0, "actual": 0.30, "pred": {"6-24h": 0.28}}],
    }
    plan = [
        {
            "start": t0,
            "plan_w": -500.0,
            "actual_w": -400.0,
            "real_w": -400.0,
            "real_share": 1.0,
        }
    ]
    r = day_review(records, results, plan, "pv@x", day, "ahead")
    assert [row[5] for row in r["measured"]] == [400, 0]  # grid
    assert r["totals"]["house"] == 0.3 and r["totals"]["imported"] == 0.1
    assert r["totals"]["charged"] == 0.15 and r["totals"]["discharged"] == 0.1
    assert [row[1] for row in r["house_forecast"]] == [600.0, 600.0]
    assert r["house_vs"] == (0.3, 0.3)  # forecast, measured kWh
    assert r["pv_forecast"][0][1] == 400.0  # the corrected PV forecast
    assert r["price_vs"] == (0.28, 0.3)
    assert r["battery_plan"][0][1:] == [-500.0, -400.0]
    assert r["followed"]["real"] is not None
    late = day_review(records, results, plan, "pv@x", day, "late")
    assert [row[1] for row in late["house_forecast"]] == [750.0, 450.0]
    assert (
        first_day(records)
        == dt_util.as_local(dt_util.parse_datetime(before)).date().isoformat()
    )


async def test_websocket(hass, hass_ws_client) -> None:
    """Not loaded: a clear error, no crash."""
    from homeassistant.components import websocket_api

    from custom_components.homebatteryassist.output.day_review import (
        websocket_day_review,
    )

    websocket_api.async_register_command(hass, websocket_day_review)
    client = await hass_ws_client(hass)
    await client.send_json(
        {"id": 1, "type": "homebatteryassist/day_review", "day": "2026-11-23"}
    )
    msg = await client.receive_json()
    assert not msg["success"] and msg["error"]["code"] == "not_loaded"
