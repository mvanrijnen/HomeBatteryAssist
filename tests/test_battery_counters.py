"""Tests for today's energy and the measured round-trip efficiency."""

from custom_components.homebatteryassist.engine.measure.battery_monitor import (
    measured_efficiency,
    today_energy,
)


def _stats(charged, discharged, days):
    return {"charged_kwh": charged, "discharged_kwh": discharged, "days": days}


def _day(date, charged, discharged, stored):
    return {
        "date": date,
        "charged": charged,
        "discharged": discharged,
        "stored": stored,
    }


def test_today_from_the_last_day_start() -> None:
    stats = _stats(
        12.5,
        9.0,
        [_day("2026-11-17", 5.0, 4.0, 1.0), _day("2026-11-18", 10.0, 8.5, 0.6)],
    )
    assert today_energy(stats) == (2.5, 0.5)
    assert today_energy(_stats(1.0, 1.0, [])) is None


def test_efficiency_from_the_counters() -> None:
    # 10 kWh charged, 8.4 kWh discharged, 0.2 kWh more inside than then.
    stats = _stats(10.0, 8.4, [_day("2026-11-01", 0.0, 0.0, 0.6)])
    result = measured_efficiency(stats, 0.8, 5.12)
    assert result is not None
    assert result.pct == 86.0 and result.days == 1 and result.charged_kwh == 10.0


def test_efficiency_needs_a_full_capacity_charged() -> None:
    stats = _stats(4.0, 3.4, [_day("2026-11-01", 0.0, 0.0, 0.6)])
    assert measured_efficiency(stats, 0.6, 5.12) is None


def test_efficiency_not_while_much_is_still_inside() -> None:
    # 3 kWh more inside on 8 kWh charged: too uncertain.
    stats = _stats(8.0, 4.5, [_day("2026-11-01", 0.0, 0.0, 0.5)])
    assert measured_efficiency(stats, 3.5, 5.12) is None


def test_efficiency_skips_days_without_a_stored_energy() -> None:
    days = [_day("2026-11-01", 0.0, 0.0, None), _day("2026-11-02", 1.0, 0.0, 1.0)]
    stats = _stats(11.0, 8.6, days)
    result = measured_efficiency(stats, 1.0, 5.0)
    assert result is not None and result.pct == 86.0


def test_efficiency_rejects_nonsense() -> None:
    stats = _stats(10.0, 12.0, [_day("2026-11-01", 0.0, 0.0, 0.6)])
    assert measured_efficiency(stats, 0.6, 5.12) is None
    assert measured_efficiency(stats, None, 5.12) is None
