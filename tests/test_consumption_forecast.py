"""Tests for the consumption forecast and user adjustments."""

from datetime import datetime, timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist.const import (
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_PHASES,
    CONF_PLANNING_HORIZON,
    DOMAIN,
)
from custom_components.homebatteryassist.engine.forecasts.adjustments import (
    Adjustment,
    apply_adjustments,
)
from custom_components.homebatteryassist.engine.forecasts.consumption import (
    ConsumptionProfile,
    forecast_consumption,
)
from custom_components.homebatteryassist.engine.forecasts.horizon import (
    HorizonLimit,
    PlanningWindow,
)

UTC = dt_util.UTC
# Monday 2026-11-16 00:00 UTC
MONDAY = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
H = timedelta(hours=1)
D = timedelta(days=1)


def _record(start: datetime, avg: float, minutes: int = 60, **extra) -> dict:
    return {
        "start": start.isoformat(),
        "minutes": minutes,
        "avg_w": avg,
        "coverage": 1.0,
        **extra,
    }


def _weeks(weeks: int, value) -> list[dict]:
    """Hourly records for ``weeks`` weeks before MONDAY; value(day, hour)."""
    start = MONDAY - weeks * 7 * D
    return [
        _record(start + d * D + h * H, value(d % 7, h))
        for d in range(weeks * 7)
        for h in range(24)
    ]


@pytest.fixture(autouse=True)
async def utc_time_zone(hass: HomeAssistant) -> None:
    """Keep local time equal to UTC so weekdays/hours are easy to reason about."""
    await hass.config.async_set_time_zone("UTC")


async def test_profile_per_weekday_and_hour(hass: HomeAssistant) -> None:
    """With enough history: average of the same weekday and hour."""
    records = _weeks(3, lambda day, hour: 1000.0 if day == 0 and hour == 18 else 300.0)
    profile = ConsumptionProfile(records, MONDAY)
    assert profile.predict(MONDAY + 18 * H) == (1000.0, "weekday_hour")  # Monday 18h
    assert profile.predict(MONDAY + D + 18 * H) == (300.0, "weekday_hour")  # Tuesday


async def test_profile_falls_back_with_little_history(hass: HomeAssistant) -> None:
    """One day of data: per hour needs 2 days -> overall average."""
    one_day = [_record(MONDAY - D + h * H, 100.0 * (h + 1)) for h in range(24)]
    profile = ConsumptionProfile(one_day, MONDAY)
    value, method = profile.predict(MONDAY + 5 * H)
    assert method == "overall"
    assert value == pytest.approx(1250.0, rel=0.02)  # recent hours weigh a bit more

    two_days = one_day + [
        _record(MONDAY - 2 * D + h * H, 100.0 * (h + 1)) for h in range(24)
    ]
    assert ConsumptionProfile(two_days, MONDAY).predict(MONDAY + 5 * H) == (
        600.0,
        "hour",
    )


async def test_recent_days_weigh_more(hass: HomeAssistant) -> None:
    """Half-life of 14 days: last week's change shows up in the forecast."""
    records = _weeks(4, lambda day, hour: 400.0)
    for record in records:
        if record["start"] >= (MONDAY - 7 * D).isoformat():
            record["avg_w"] = 800.0
    value, _ = ConsumptionProfile(records, MONDAY).predict(MONDAY + 3 * H)
    assert 500.0 < value < 800.0
    assert value > 400 + (800 - 400) / 4  # more than a plain average of 4 weeks


def _adjustment(
    kind: str, value: float, start: datetime, end: datetime, name: str = "x"
) -> Adjustment:
    return Adjustment(
        id="1",
        name=name,
        start=start.isoformat(),
        end=end.isoformat(),
        kind=kind,
        value=value,
    )


def test_apply_adjustments() -> None:
    """Fixed power, then factors, then offsets; partial overlap is weighted."""
    s, e = MONDAY, MONDAY + timedelta(minutes=15)
    assert apply_adjustments(400.0, s, e, []) == (400.0, ())
    assert apply_adjustments(400.0, s, e, [_adjustment("factor", 0.5, s, e)]) == (
        200.0,
        ("x",),
    )
    assert (
        apply_adjustments(400.0, s, e, [_adjustment("offset_w", 2000, s, e)])[0]
        == 2400.0
    )
    both = [
        _adjustment("offset_w", -100, s, e, "b"),
        _adjustment("power_w", 1000, s, e, "a"),
    ]
    assert apply_adjustments(400.0, s, e, both) == (900.0, ("b", "a"))
    half = [_adjustment("offset_w", 1000, s + timedelta(minutes=7, seconds=30), e)]
    assert apply_adjustments(400.0, s, e, half)[0] == 900.0
    assert (
        apply_adjustments(400.0, s, e, [_adjustment("offset_w", -5000, s, e)])[0] == 0.0
    )


async def test_forecast_within_window_only(hass: HomeAssistant) -> None:
    """Slots cover exactly the window; adjustments show in the slot."""
    records = _weeks(2, lambda day, hour: 500.0)
    window = PlanningWindow(MONDAY, MONDAY + 2 * H, HorizonLimit.PRICE)
    party = _adjustment("offset_w", 1500, MONDAY + H, MONDAY + 2 * H, "Party")
    slots = forecast_consumption(
        records, window, timedelta(minutes=15), [party], MONDAY
    )
    assert len(slots) == 8
    assert slots[0].power_w == 500.0
    assert (slots[-1].power_w, slots[-1].base_w, slots[-1].adjustments) == (
        2000.0,
        500.0,
        ("Party",),
    )
    assert (
        forecast_consumption(
            records, PlanningWindow(MONDAY, MONDAY, HorizonLimit.NO_PRICE), H
        )
        == []
    )
    assert forecast_consumption([], window, H) == []


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.l1"},
        options={CONF_HISTORY_INTERVAL: 60, CONF_PLANNING_HORIZON: 1},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _sensor(hass: HomeAssistant, entry: MockConfigEntry, key: str):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{key}"
    )
    return hass.states.get(entity_id)


async def test_forecast_sensor_and_adjust_actions(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The sensor shows the forecast; actions adjust it and remove adjustments."""
    freezer.move_to(MONDAY + timedelta(minutes=10))
    entry = await _setup(hass)
    data = entry.runtime_data
    data.history.records = _weeks(2, lambda day, hour: 500.0)
    await data.forecast.async_refresh()
    await hass.async_block_till_done()

    state = _sensor(hass, entry, "consumption_forecast")
    assert float(state.state) == 500.0
    assert state.attributes["method"] == "weekday_hour"
    # Window 00:10 + 24 h: 24 whole hours plus the last 10 minutes.
    assert state.attributes["slots"] == 25
    assert state.attributes["total_kwh"] == 12.08

    response = await hass.services.async_call(
        DOMAIN,
        "adjust_forecast",
        {"name": "Vakantie", "duration": {"hours": 2}, "factor": 0.2},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    assert response["name"] == "Vakantie"
    state = _sensor(hass, entry, "consumption_forecast")
    # 00:10-02:10 at x0.2: the current hour is covered for 50 of 60 minutes.
    assert float(state.state) == 166.7
    forecast = state.attributes["forecast"]
    assert forecast[0]["adjusted_by"] == ["Vakantie"]
    assert forecast[1]["power_w"] == 100.0
    assert forecast[2]["power_w"] == 433.3  # 10 of 60 minutes
    assert forecast[3]["power_w"] == 500.0
    assert data.decisions.latest["key"] == "forecast_adjusted"

    # Local times without time zone are fine too.
    await hass.services.async_call(
        DOMAIN,
        "adjust_forecast",
        {
            "name": "Oven",
            "start": "2026-11-16 18:00:00",
            "end": "2026-11-16 19:00:00",
            "offset_w": 2000,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    oven = next(
        s
        for s in _sensor(hass, entry, "consumption_forecast").attributes["forecast"]
        if s.get("adjusted_by") == ["Oven"]
    )
    assert (oven["start"], oven["power_w"]) == ((MONDAY + 18 * H).isoformat(), 2500.0)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "adjust_forecast",
            {"start": "2026-11-16 18:00:00", "end": "2026-11-16 17:00:00", "factor": 2},
            blocking=True,
        )

    response = await hass.services.async_call(
        DOMAIN,
        "clear_forecast_adjustments",
        {"name": "Vakantie"},
        blocking=True,
        return_response=True,
    )
    assert response == {"removed": 1}
    await hass.async_block_till_done()
    assert float(_sensor(hass, entry, "consumption_forecast").state) == 500.0
    await hass.services.async_call(
        DOMAIN, "clear_forecast_adjustments", {}, blocking=True
    )
    assert data.forecast.adjustments.items == []
