"""The activity log: minutes merged into periods per battery, with who
decided and whether it was the plan."""

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.explain.activity_log import (
    ActivityLog,
)

T0 = datetime(2026, 11, 24, 6, 0, tzinfo=dt_util.UTC)
MINUTE = timedelta(minutes=1)


def _look(power, source="own", plan="discharge", surplus=0.0, price=0.40):
    return {
        "id": "b1",
        "name": "Venus",
        "power_w": power,
        "pv_surplus_w": surplus,
        "source": source,
        "plan": plan,
        "price": price,
    }


async def test_periods(hass: HomeAssistant) -> None:
    log = ActivityLog(hass, "e1", list)
    # Ten minutes discharging 600 W as planned, by HBA's control.
    for i in range(1, 11):
        log.add(T0 + i * MINUTE, _look(-600, "hba_nom"), MINUTE)
    # Then charging from the sun, the plan said discharge.
    for i in range(11, 16):
        log.add(T0 + i * MINUTE, _look(1000, "own", surplus=1500), MINUTE)
    # Charging from the grid in a test.
    log.add(T0 + 16 * MINUTE, _look(800, "test", surplus=0), MINUTE)
    periods = log.recent(7, T0 + 20 * MINUTE)
    assert [p["kind"] for p in periods] == ["charge_grid", "charge_pv", "discharge"]
    discharge = periods[-1]
    assert discharge["source"] == "hba_nom" and discharge["follows"] is True
    assert discharge["kwh"] == 0.1 and discharge["price"] == 0.4
    assert discharge["start"] == T0.isoformat()
    assert periods[1]["follows"] is False
    assert periods[0]["source"] == "test"
    # Old periods go after 30 days.
    log._sample = None  # (not used here)
    assert log.recent(1, T0 + timedelta(days=2)) == []


async def test_reasons(hass: HomeAssistant) -> None:
    """Reasons add up in minutes within one period, never split it."""
    log = ActivityLog(hass, "e1", list)
    for i in range(1, 9):
        look = {**_look(-600, "hba_nom"), "reason": "house_demand"}
        if i in (4, 5):
            look["reason"] = "spike"
        log.add(T0 + i * MINUTE, look, MINUTE)
    log.add(T0 + 9 * MINUTE, _look(-600, "hba_nom"), MINUTE)  # no reason
    (period,) = log.recent(7, T0 + 10 * MINUTE)
    assert period["reasons"] == {"house_demand": 6.0, "spike": 2.0}


async def test_websocket(hass, hass_ws_client) -> None:
    """The dashboard's call answers (also before the first forecast)."""
    from types import SimpleNamespace

    from homeassistant.components import websocket_api

    from custom_components.homebatteryassist.output import panel

    log = ActivityLog(hass, "e1", list)
    log.add(T0 + MINUTE, _look(-600), MINUTE)
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(activity=log, forecast=SimpleNamespace(data=None))
    )
    websocket_api.async_register_command(hass, panel.websocket_activity)
    panel_loaded = panel._loaded_entry
    try:
        panel._loaded_entry = lambda hass: entry
        client = await hass_ws_client(hass)
        await client.send_json(
            {"id": 1, "type": "homebatteryassist/activity", "days": 30}
        )
        result = await client.receive_json()
    finally:
        panel._loaded_entry = panel_loaded
    assert result["success"], result
    assert result["result"]["price_unit"] is None
