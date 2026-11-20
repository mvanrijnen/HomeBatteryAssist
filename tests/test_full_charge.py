"""Tests for planning periodic full charges at the cheapest moment."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.planning.full_charge import (
    full_charge_due,
    schedule_full_charges,
)
from custom_components.homebatteryassist.engine.sources.prices.price_points import (
    PricePoint,
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


def test_one_after_the_other_emptiest_first() -> None:
    """Sequential: the emptiest battery first; never two at the same time,
    whatever the connection or the sun allows."""
    prices = _prices([0.30, 0.05, 0.10, 0.30])
    batteries = [_battery("a", soc=80.0), _battery("b", soc=60.0)]
    for together in ("sequential", "parallel"):
        charges = schedule_full_charges(
            batteries, {}, prices, 3, NOW, together=together
        )
        assert len(charges) == 2
        first, second = charges
        assert second.start >= first.end or second.end <= first.start
    first, _second = schedule_full_charges(
        batteries, {}, prices, 3, NOW, together="sequential"
    )
    assert first.battery_id == "b"  # the emptiest first


def test_block_long_enough_within_the_limits() -> None:
    """With little room (a peak limit), the block is made longer so the
    battery really reaches 100 %, at the cheapest moment that allows it."""
    prices = _prices([0.30, 0.05, 0.10, 0.30, 0.30, 0.30])
    (fast,) = schedule_full_charges([_battery("a")], {}, prices, 3, NOW)
    (slow,) = schedule_full_charges(
        [_battery("a")], {}, prices, 3, NOW, room=lambda when, _id: 500.0
    )
    assert slow.end - slow.start > fast.end - fast.start
    assert slow.power_w >= 500.0


def test_block_sized_with_the_battery_own_room() -> None:
    """The room is asked per battery (its own phase): a battery on a full
    phase gets a block long enough at what that phase leaves."""
    prices = _prices([0.30] * 24)
    (block,) = schedule_full_charges(
        [_battery("a", soc=10.0), _battery("b")],
        {"b": NOW},
        prices,
        3,
        NOW,
        room=lambda when, battery_id: 300.0 if battery_id == "a" else 2000.0,
    )
    assert block.battery_id == "a"
    assert (block.end - block.start) * 300.0 / H >= 4500.0  # 90 % of 5 kWh


def test_full_battery_block_does_not_charge_the_others() -> None:
    """Once the battery charging fully is full, the rest of its block is no
    forced charge: zero on the meter does not charge the other battery from
    the grid."""
    from custom_components.homebatteryassist.engine.forecast.consumption_forecast import (
        ForecastSlot,
    )
    from custom_components.homebatteryassist.engine.planning.battery_plan import (
        plan_batteries,
    )

    a, b = _battery("a", soc=80.0), _battery("b", soc=50.0)
    for battery in (a, b):
        battery.config.min_soc, battery.config.max_soc = 10.0, 100.0
        battery.config.max_discharge_w = 2000.0
    slots = [
        ForecastSlot(NOW + k * H, NOW + (k + 1) * H, 500.0, 500.0, "x")
        for k in range(6)
    ]
    block = {NOW + k * H: 2000.0 for k in (1, 2, 3)}
    plan = plan_batteries(
        [a, b],
        slots,
        {},
        _prices([0.30] * 6),
        mode="nom",
        forced=block,
        forced_by={k: {"a": w} for k, w in block.items()},
    )
    charged = sum(max(s.power_w, 0.0) for s in plan.slots)  # Wh (1 h slots)
    assert charged <= 1000.0 + 1  # a's missing 20 % only
