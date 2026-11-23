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
