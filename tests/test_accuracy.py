"""Tests for the running accuracy and corrections of all forecasts."""

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
from custom_components.homebatteryassist.engine.evaluation.accuracy import (
    MIN_SAMPLES,
    ForecastAccuracy,
    bucket_for,
)

UTC = dt_util.UTC
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


def test_buckets() -> None:
    """Lead times map to their bucket; started slots to none."""
    assert bucket_for(timedelta(minutes=30)) == "0-1h"
    assert bucket_for(13 * H) == "6-24h"
    assert bucket_for(30 * H) == "1-2d"
    assert bucket_for(10 * D) == "5d+"
    assert bucket_for(-H) is None


async def test_consumption_learning_and_correction(hass: HomeAssistant) -> None:
    """Systematically too high -> corrected down, growing with the samples."""
    acc = ForecastAccuracy(hass, "t")
    slots = [
        (MONDAY + i * H, MONDAY + (i + 1) * H)
        for i in range(MIN_SAMPLES["consumption"])
    ]
    # Predicted 13 h ahead (6-24h): 600 W; measured 500 W.
    for s, e in slots:  # each predicted 13 h ahead (6-24h)
        acc.record("consumption", [(s, e, 600.0)], s - 13 * H)
    # Imported records are no measurement of our forecast.
    assert acc.evaluate_consumption([_record(slots[0][0], 1.0, source="import")]) == 0
    half = len(slots) // 2
    acc.evaluate_consumption([_record(s, 500.0) for s, _ in slots[:half]])
    acc.refresh_stats(MONDAY + 100 * H)
    stats = acc.stats("consumption")["6-24h"]
    assert stats.samples == half
    assert stats.bias == pytest.approx(100.0)
    assert stats.strength == pytest.approx(0.5)
    assert stats.correction == pytest.approx(-50.0)
    # A new forecast 13 h ahead is corrected; one 1 h ahead not (no data there).
    now = MONDAY + 200 * H
    assert acc.correct("consumption", 600.0, now + 13 * H, now) == pytest.approx(550.0)
    assert acc.correct("consumption", 600.0, now + H, now) == 600.0

    acc.evaluate_consumption([_record(s, 500.0) for s, _ in slots[half:]])
    acc.refresh_stats(MONDAY + 100 * H)
    assert acc.stats("consumption")["6-24h"].correction == pytest.approx(-100.0)
    # Never more than half of the value.
    assert acc.correct("consumption", 150.0, now + 13 * H, now) == 75.0


async def test_pv_factor_from_measured_production(hass: HomeAssistant) -> None:
    """PV: factor = measured / predicted energy; night hours are ignored."""
    acc = ForecastAccuracy(hass, "t")
    day = [MONDAY + 12 * H + i * H for i in range(MIN_SAMPLES["pv"])]
    night = MONDAY + 2 * H
    for s in [*day, night]:  # each predicted 30 h ahead (1-2d)
        acc.record("pv", [(s, s + H, 0.0 if s == night else 1000.0)], s - 30 * H)
    # Measured 800 W average in each daytime hour (4 quarter records per hour).
    records = [
        _record(s + q * timedelta(minutes=15), 300.0, 15, pv_w=800.0)
        for s in day
        for q in range(4)
    ] + [
        _record(night + q * timedelta(minutes=15), 300.0, 15, pv_w=0.0)
        for q in range(4)
    ]
    assert acc.evaluate_pv(records) == len(day)
    acc.refresh_stats(MONDAY + 3 * D)
    stats = acc.stats("pv")["1-2d"]
    assert stats.ratio == pytest.approx(0.8)
    assert stats.correction == pytest.approx(0.8)
    now = MONDAY + 4 * D
    assert acc.correct("pv", 1000.0, now + 30 * H, now) == pytest.approx(800.0)


async def test_price_correction_only_learned_from_estimates(
    hass: HomeAssistant,
) -> None:
    """Estimated prices vs. published later; the bias is subtracted."""
    acc = ForecastAccuracy(hass, "t")
    starts = [MONDAY + i * timedelta(minutes=15) for i in range(MIN_SAMPLES["price"])]
    for s in starts:  # each estimated 36 h ahead (1-2d)
        acc.record("price", [(s, s + timedelta(minutes=15), 0.30)], s - 36 * H)
    acc.evaluate_prices({s.isoformat(): 0.25 for s in starts})
    acc.refresh_stats(MONDAY + D)
    stats = acc.stats("price")["1-2d"]
    assert stats.bias == pytest.approx(0.05)
    now = MONDAY + 2 * D
    assert acc.correct("price", 0.30, now + 36 * H, now) == pytest.approx(0.25)


async def test_modes_and_reset(hass: HomeAssistant) -> None:
    """Off, manual (per bucket, temporary) and reset."""
    acc = ForecastAccuracy(hass, "t")
    now = MONDAY
    acc.set_mode("pv", "manual", 0.9)
    assert acc.correct("pv", 1000.0, now + 3 * H, now) == pytest.approx(900.0)
    acc.set_mode("pv", "manual", 0.5, bucket="3-5d", until=now + H)
    assert acc.correct("pv", 1000.0, now + 4 * D, now) == pytest.approx(500.0)
    # Other lead times keep the earlier manual value for all lead times.
    assert acc.correct("pv", 1000.0, now + 3 * H, now) == pytest.approx(900.0)
    # After the end: back to learned (no data -> no correction).
    later = now + 2 * H
    assert acc.mode("pv", later) == "learned"
    acc.set_mode("consumption", "off")
    assert acc.correct("consumption", 700.0, later + H, later) == 700.0

    acc.record("price", [(now + D, now + D + H, 0.3)], now)
    acc.reset("price")
    assert acc.predictions["price"] == {}

    await acc.async_save()
    reloaded = ForecastAccuracy(hass, "t")
    await reloaded.async_load()
    assert reloaded.settings["consumption"]["mode"] == "off"


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


async def test_cycle_actions_and_sensor(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The cycle records and verifies; actions switch modes; sensors report."""
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to(MONDAY + timedelta(minutes=10))
    entry = await _setup(hass)
    data = entry.runtime_data
    data.history.records = [
        _record(MONDAY - 14 * D + i * H, 500.0) for i in range(14 * 24)
    ]
    await data.forecast.async_refresh()
    pending = data.forecast.accuracy.predictions["consumption"]
    assert (MONDAY + H).isoformat() in pending

    # The 01:00 slot is measured at 600 W.
    freezer.move_to(MONDAY + 2 * H + timedelta(minutes=5))
    data.history.records.append(_record(MONDAY + H, 600.0))
    await data.forecast.async_refresh()
    await hass.async_block_till_done()
    sensor = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_consumption_forecast_accuracy"
    )
    state = hass.states.get(sensor)
    assert float(state.state) == 100.0
    assert state.attributes["mode"] == "learned"
    assert state.attributes["lead_times"]["0-1h"]["bias"] == -100.0

    response = await hass.services.async_call(
        DOMAIN,
        "set_forecast_correction",
        {
            "kind": "consumption",
            "mode": "manual",
            "value": -50,
            "duration": {"hours": 1},
        },
        blocking=True,
        return_response=True,
    )
    assert response["consumption"]["mode"] == "manual"
    expected = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_consumption_forecast"
    )
    await hass.async_block_till_done()
    assert float(hass.states.get(expected).state) == 450.0
    keys = [d["key"] for d in data.decisions.entries[-2:]]
    assert keys == ["correction_mode_manual", "correction_consumption"]

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_forecast_correction",
            {"kind": "pv", "mode": "manual"},
            blocking=True,
        )
    await hass.services.async_call(
        DOMAIN, "reset_forecast_accuracy", {"kind": "all"}, blocking=True
    )
    assert data.forecast.accuracy.results["consumption"] == []
