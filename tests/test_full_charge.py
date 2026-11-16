"""Tests for planning periodic full charges at the cheapest moment."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.inputs.prices import PricePoint
from custom_components.homebatteryassist.planning.full_charge import (
    full_charge_due,
    schedule_full_charges,
)

NOW = datetime(2026, 11, 16, 0, 0, tzinfo=dt_util.UTC)
H = timedelta(hours=1)
D = timedelta(days=1)


def _battery(id_: str, soc: float = 80.0, interval: int = 28):
    config = SimpleNamespace(
        id=id_,
        name=id_.upper(),
        capacity_kwh=5.0,
        max_charge_w=2000.0,
        efficiency=1.0,
        full_charge_interval_days=interval,
    )
    return SimpleNamespace(soc=soc, config=config)


def _prices(per_hour: list[float]) -> list[PricePoint]:
    return [
        PricePoint(NOW + i * H, NOW + (i + 1) * H, p) for i, p in enumerate(per_hour)
    ]


def test_due() -> None:
    """Never charged: due now; otherwise last + interval; 0 = off."""
    assert full_charge_due(None, 28, NOW) == NOW
    assert full_charge_due(NOW - 20 * D, 28, NOW) == NOW + 8 * D
    assert full_charge_due(None, 0, NOW) is None


def test_cheapest_block_before_deadline() -> None:
    """80 % -> 100 % of 5 kWh at 2 kW = 30 min: the cheapest half hour."""
    prices = _prices([0.30, 0.30, 0.05, 0.30, 0.30, 0.30])
    last = {"a": NOW - 26 * D}  # due in 2 days: within the 3-day window
    (charge,) = schedule_full_charges([_battery("a")], last, prices, 3, NOW)
    assert charge.start == NOW + 2 * H
    assert charge.end == NOW + 2 * H + timedelta(minutes=30)
    assert charge.power_w == 2000.0


def test_not_yet_due() -> None:
    """Outside the window nothing is planned."""
    prices = _prices([0.1] * 24)
    assert (
        schedule_full_charges([_battery("a")], {"a": NOW - 10 * D}, prices, 3, NOW)
        == []
    )


def test_never_two_batteries_at_once() -> None:
    """The second battery gets the cheapest block that does not overlap."""
    prices = _prices([0.30, 0.05, 0.10, 0.30])
    batteries = [_battery("a"), _battery("b")]
    first, second = schedule_full_charges(batteries, {}, prices, 3, NOW)
    assert (first.battery_id, first.start) == ("a", NOW + H)
    assert second.battery_id == "b"
    assert second.start >= first.end or second.end <= first.start
    # 01:30-02:00 is as cheap as the first block and does not overlap it.
    assert second.start == NOW + H + timedelta(minutes=30)


def test_together_when_the_connection_allows() -> None:
    """Full charges may overlap if that costs nothing extra (phase limits ok)."""
    prices = _prices([0.30, 0.05, 0.10, 0.30])
    batteries = [_battery("a"), _battery("b")]
    first, second = schedule_full_charges(
        batteries, {}, prices, 3, NOW, fits=lambda when, powers: True
    )
    assert first.start == second.start == NOW + H  # both in the cheapest block
    # Not together when the connection cannot carry both.
    first, second = schedule_full_charges(
        batteries, {}, prices, 3, NOW, fits=lambda when, powers: len(powers) < 2
    )
    assert second.start >= first.end or second.end <= first.start


def test_preferred_day_and_solar() -> None:
    """A preferred weekday wins when possible; solar surplus counts as cheap."""
    prices = _prices([0.30, 0.05, 0.10, 0.30])
    battery = [_battery("a")]
    other_day = (dt_util.as_local(NOW).weekday() + 3) % 7
    (charge,) = schedule_full_charges(
        battery, {}, prices, 3, NOW, preferred_day=other_day
    )
    assert charge.start == NOW + H  # preferred day not in reach: cheapest
    (charge,) = schedule_full_charges(
        battery,
        {},
        prices,
        3,
        NOW,
        slot_price=lambda when, price, power: 0.0 if when >= NOW + 3 * H else price,
    )
    assert charge.start >= NOW + 3 * H  # free solar power wins
