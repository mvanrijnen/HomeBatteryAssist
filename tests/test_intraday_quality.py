"""Correction within the day, excluded days, frozen grid sensors and the
control quality of the virtual batteries."""

from datetime import date, datetime, timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.homebatteryassist.const import (
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_PHASES,
    DOMAIN,
)
from custom_components.homebatteryassist.engine.devices.batteries.control_quality import (
    ControlQuality,
)
from custom_components.homebatteryassist.engine.forecast.intraday import (
    MAX_SHIFT,
    intraday_correction,
    measured_today,
    weight_at,
)
from custom_components.homebatteryassist.engine.history.consumption_history import (
    ConsumptionHistory,
)

SENSOR = "sensor.homebatteryassist_house_consumption"


def _local(hour: int, minute: int = 0) -> datetime:
    return dt_util.start_of_local_day(date(2026, 11, 20)).replace(
        hour=hour, minute=minute
    )


def test_weight_by_time_of_day() -> None:
    """Nothing before 03:00, fully from 12:00, linear in between."""
    assert weight_at(_local(2, 59)) == 0
    assert weight_at(_local(3)) == 0
    assert weight_at(_local(7, 30)) == pytest.approx(0.5)
    assert weight_at(_local(12)) == 1
    assert weight_at(_local(20)) == 1


def test_intraday_shift_capped_and_both_ways() -> None:
    """Measured vs predicted moves the rest of today, at most MAX_SHIFT."""
    starts = [dt_util.as_utc(_local(h)) for h in range(8)]
    predicted = dict.fromkeys(starts, 400.0)
    now = dt_util.as_utc(_local(14))
    more = intraday_correction(dict.fromkeys(starts, 480.0), predicted, 1.0, now)
    assert more is not None
    assert more.factor == pytest.approx(1.2)
    assert more.applies(dt_util.as_utc(_local(23)))
    assert not more.applies(dt_util.as_utc(_local(23)) + timedelta(hours=2))
    much = intraday_correction(dict.fromkeys(starts, 1000.0), predicted, 1.0, now)
    assert much.factor == pytest.approx(1 + MAX_SHIFT)
    less = intraday_correction(dict.fromkeys(starts, 300.0), predicted, 1.0, now)
    assert less.factor == pytest.approx(0.75)
    # half way the morning: half of the shift
    early = intraday_correction(
        dict.fromkeys(starts, 480.0), predicted, 1.0, dt_util.as_utc(_local(7, 30))
    )
    assert early.factor == pytest.approx(1.1)
    # too little expected so far: nothing
    assert intraday_correction({starts[0]: 300.0}, {starts[0]: 100.0}, 1.0, now) is None


def test_measured_today_counts_finished_covered_intervals() -> None:
    """Only today's finished intervals with enough coverage (no vacation)."""
    midnight = dt_util.as_utc(_local(0))
    now = midnight + timedelta(hours=2, minutes=10)

    def record(minutes_after: int, coverage: float = 1.0, **extra) -> dict:
        start = midnight + timedelta(minutes=minutes_after)
        return {
            "start": start.isoformat(),
            "minutes": 60,
            "avg_w": 500.0,
            "coverage": coverage,
            **extra,
        }

    records = [
        record(-60),  # yesterday
        record(0),
        record(60, coverage=0.5),  # too little measured
        record(120),  # still running
    ]
    assert list(measured_today(records, midnight, now)) == [midnight]
    assert measured_today([record(0, vacation=True)], midnight, now) == {}


async def test_exclude_days_and_take_back(hass: HomeAssistant) -> None:
    """Excluded days are marked as vacation and taken back; real vacation
    records stay vacation."""
    history = ConsumptionHistory(hass, "x", 60)
    day = dt_util.start_of_local_day(date(2026, 11, 14))
    history.records = [
        {
            "start": dt_util.as_utc(day + timedelta(hours=h)).isoformat(),
            "minutes": 60,
            "avg_w": 400.0,
            "coverage": 1.0,
        }
        for h in range(30)
    ]
    history.records[2]["vacation"] = True
    assert history.exclude_days([date(2026, 11, 14)]) == 23
    assert "2026-11-14" in history.excluded_days
    assert all(r.get("vacation") for r in history.records[:24])
    assert not any(r.get("vacation") for r in history.records[24:])
    assert history.exclude_days([date(2026, 11, 14)], exclude=False) == 23
    assert history.excluded_days == set()
    assert [i for i, r in enumerate(history.records) if r.get("vacation")] == [2]


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MAX_CURRENT: 25, CONF_PHASES: 1, "sensor_l1": "sensor.l1"},
        options={CONF_HISTORY_INTERVAL: 15},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_exclude_days_action(hass: HomeAssistant) -> None:
    """The action checks the range and answers with the excluded days."""
    entry = await _setup(hass)
    today = dt_util.now().date()
    result = await hass.services.async_call(
        DOMAIN,
        "exclude_consumption_days",
        {"dates": [today.isoformat()]},
        blocking=True,
        return_response=True,
    )
    assert result["excluded_days"] == [today.isoformat()]
    assert entry.runtime_data.decisions.latest["key"] == "days_excluded"
    with pytest.raises(Exception, match="between"):
        await hass.services.async_call(
            DOMAIN,
            "exclude_consumption_days",
            {"dates": [(today + timedelta(days=1)).isoformat()]},
            blocking=True,
        )
    result = await hass.services.async_call(
        DOMAIN,
        "exclude_consumption_days",
        {"dates": [today.isoformat()], "include": True},
        blocking=True,
        return_response=True,
    )
    assert result["excluded_days"] == []


@pytest.mark.frozen_grid
async def test_frozen_grid_sensor_counts_as_unknown(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A grid sensor that is not reported anew for 90 s is unknown (the
    virtual batteries hold); reported again, it counts again."""
    entry = await _setup(hass)
    hass.states.async_set("sensor.l1", "800", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert float(hass.states.get(SENSOR).state) == 800.0
    freezer.tick(timedelta(minutes=3))  # past the start-up quiet time
    hass.states.async_set("sensor.l1", "800", {"unit_of_measurement": "W"})
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert float(hass.states.get(SENSOR).state) == 800.0
    freezer.tick(timedelta(seconds=100))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state == "unavailable"
    measurements = entry.runtime_data.measurements
    assert measurements.flow is None
    assert measurements.stale == ["sensor.l1"]
    assert entry.runtime_data.decisions.latest["key"] == "grid_stale"
    # the same value reported again (no state change event)
    hass.states.async_set("sensor.l1", "800", {"unit_of_measurement": "W"})
    freezer.tick(timedelta(seconds=16))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert float(hass.states.get(SENSOR).state) == 800.0
    assert measurements.stale == []


def test_control_quality_states() -> None:
    """Stable, oscillating, sluggish and idle from the rounds."""
    start = datetime(2026, 11, 20, 12, tzinfo=dt_util.UTC)

    def run(errors: list[float], powers: list[float]) -> str:
        quality = ControlQuality()
        for i, (error, power) in enumerate(zip(errors, powers, strict=True)):
            quality.add(start + timedelta(seconds=5 * i), error, power)
        return quality.summary(start + timedelta(seconds=5 * len(errors)))["state"]

    n = 60
    assert run([20.0] * n, [500.0] * n) == "stable"
    assert run([20.0] * 5, [500.0] * 5) == "idle"
    assert run([300.0] * n, [500.0] * n) == "sluggish"
    swing = [250.0 if i % 2 else -250.0 for i in range(n)]
    assert run(swing, [-s * 2 for s in swing]) == "oscillating"
    # old rounds drop out of the window
    quality = ControlQuality()
    quality.add(start, 300.0, 0.0)
    assert quality.summary(start + timedelta(minutes=11))["rounds"] == 0


def test_intraday_leaves_out_adjusted_intervals() -> None:
    """Energy the user announced (an adjustment) that really happened is no
    forecast error: those intervals are left out, also after the adjustment
    was pruned."""
    from types import SimpleNamespace
    from unittest.mock import patch

    from custom_components.homebatteryassist.engine import coordinator as mod

    now = _local(12)
    midnight = dt_util.as_utc(dt_util.start_of_local_day(now))
    q = timedelta(minutes=15)
    starts = [midnight + i * q for i in range(48)]
    adjusted = {s for s in starts if 32 <= starts.index(s) < 40}  # 08:00-10:00
    measured = {s: 2000.0 if s in adjusted else 500.0 for s in starts}
    coord = object.__new__(mod.ForecastCoordinator)
    coord.intraday_on = True
    coord.history = SimpleNamespace(vacation=False)
    coord.forecast_records = list
    coord.forecaster_key = "profile"
    coord._intraday_key = (midnight, max(measured), len(measured), "profile")
    coord._intraday_predicted = dict.fromkeys(starts, 500.0)
    coord._intraday_logged = None
    coord._decisions = SimpleNamespace(async_log=lambda *a, **k: None)
    coord._adjusted_today = adjusted
    with patch.object(mod, "measured_today", return_value=measured):
        result = coord._intraday_correction(None, q, dt_util.as_utc(now))
    assert result is not None and result.factor == pytest.approx(1.0)
