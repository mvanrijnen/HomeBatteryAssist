"""Tests for the interval consumption history."""

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.history import ConsumptionHistory

T0 = datetime(2026, 11, 16, 10, 0, tzinfo=dt_util.UTC)


async def test_time_weighted_average(hass: HomeAssistant) -> None:
    """The average is weighted by how long each value was valid."""
    history = ConsumptionHistory(hass, "test", 15)
    history.add_sample(T0, 1000.0)
    history.add_sample(T0 + timedelta(minutes=5), 400.0)

    record = history.close_interval(T0 + timedelta(minutes=15))
    assert record == {
        "start": T0.isoformat(),
        "minutes": 15,
        "avg_w": 600.0,  # (1000*5 + 400*10) / 15
        "coverage": 1.0,
    }
    assert history.records == [record]


async def test_unknown_periods_reduce_coverage(hass: HomeAssistant) -> None:
    """Periods without a valid value are left out of the average."""
    history = ConsumptionHistory(hass, "test", 60)
    history.add_sample(T0, 500.0)
    history.add_sample(T0 + timedelta(minutes=30), None)

    record = history.close_interval(T0 + timedelta(minutes=60))
    assert record is not None
    assert record["avg_w"] == 500.0
    assert record["coverage"] == 0.5


async def test_empty_interval_not_recorded(hass: HomeAssistant) -> None:
    """An interval without any valid measurement produces no record."""
    history = ConsumptionHistory(hass, "test", 5)
    history.add_sample(T0, None)
    assert history.close_interval(T0 + timedelta(minutes=5)) is None
    assert history.records == []


async def test_interval_alignment(hass: HomeAssistant) -> None:
    """Intervals start on clock boundaries of the chosen length."""
    history = ConsumptionHistory(hass, "test", 15)
    assert history.interval_start(T0 + timedelta(minutes=22, seconds=7)) == (
        T0 + timedelta(minutes=15)
    )


async def test_old_records_pruned_and_persisted(hass: HomeAssistant) -> None:
    """Records older than the retention period are dropped; data survives reload."""
    history = ConsumptionHistory(hass, "test", 60)
    history.add_sample(T0, 100.0)
    history.close_interval(T0 + timedelta(hours=1))

    later = T0 + timedelta(days=40)
    history.add_sample(later, 200.0)
    history.close_interval(later + timedelta(hours=1))
    assert [r["avg_w"] for r in history.records] == [200.0]

    await history.async_save()
    reloaded = ConsumptionHistory(hass, "test", 60)
    await reloaded.async_load()
    assert reloaded.records == history.records


async def test_excluded_power_recorded(hass: HomeAssistant) -> None:
    """Excluded devices (e.g. an EV charger) are averaged alongside."""
    history = ConsumptionHistory(hass, "test", 15)
    history.add_sample(T0, 500.0, 0.0)
    history.add_sample(T0 + timedelta(minutes=5), 500.0, 3000.0)
    record = history.close_interval(T0 + timedelta(minutes=15))
    assert record is not None
    assert record["avg_w"] == 500.0
    assert record["excluded_w"] == 2000.0  # 3000 W during 10 of 15 minutes

    history.add_sample(T0 + timedelta(minutes=15), 400.0, None)
    record = history.close_interval(T0 + timedelta(minutes=30))
    assert "excluded_w" not in record


async def test_pv_and_battery_recorded(hass: HomeAssistant) -> None:
    """Measured PV and battery power are averaged per interval."""
    history = ConsumptionHistory(hass, "test", 15)
    history.add_sample(T0, 500.0, None, 1000.0, 400.0)
    history.add_sample(T0 + timedelta(minutes=5), 500.0, None, 2000.0, -200.0)
    record = history.close_interval(T0 + timedelta(minutes=15))
    assert record["pv_w"] == round((1000 * 5 + 2000 * 10) / 15, 1)
    assert record["battery_w"] == 0.0  # 400 W for 5 min, -200 W for 10 min
