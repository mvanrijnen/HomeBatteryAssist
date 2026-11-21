"""Advice when to charge the car (nothing is switched)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.planning.ev_advice import (
    EvSlot,
    advise,
    slots_from_plan,
)

NOW = datetime(2026, 11, 21, 18, 0, tzinfo=dt_util.UTC)
H = timedelta(hours=1)


def _slots(prices, surplus=None, export=0.05):
    surplus = surplus or [0.0] * len(prices)
    return [
        EvSlot(NOW + i * H, NOW + (i + 1) * H, p, export, s)
        for i, (p, s) in enumerate(zip(prices, surplus, strict=True))
    ]


def test_cheapest_block_in_the_period() -> None:
    """20 kWh at 10 kW = 2 h: the cheapest two hours in a row."""
    slots = _slots([0.30, 0.30, 0.10, 0.08, 0.25, 0.30])
    advice = advise(slots, 20, 10_000, NOW, NOW + 6 * H, NOW)
    assert advice.start == NOW + 2 * H and advice.end == NOW + 4 * H
    assert advice.cost == pytest.approx(10 * 0.10 + 10 * 0.08)
    assert advice.now_cost == pytest.approx(10 * 0.30 * 2)
    assert advice.avg_price == pytest.approx(0.09)


def test_block_may_start_within_a_slot() -> None:
    """1.5 h ending where the cheap period ends: starts half an hour in."""
    slots = _slots([0.30, 0.10, 0.10, 0.30])
    advice = advise(slots, 15, 10_000, NOW, NOW + 4 * H, NOW)
    assert advice.cost == pytest.approx(15 * 0.10)
    assert advice.start >= NOW + H and advice.end <= NOW + 3 * H


def test_solar_surplus_costs_the_export_price() -> None:
    slots = _slots([0.25, 0.25, 0.25], surplus=[0.0, 6000.0, 0.0], export=0.05)
    advice = advise(slots, 10, 10_000, NOW, NOW + 3 * H, NOW)
    assert advice.start == NOW + H
    assert advice.sun_kwh == pytest.approx(6.0)
    assert advice.cost == pytest.approx(6 * 0.05 + 4 * 0.25)


def test_not_possible_reasons() -> None:
    slots = _slots([0.2, 0.2])
    assert advise(slots, 50, 10_000, NOW, NOW + 2 * H, NOW).reason == "too_short"
    late = advise(slots, 10, 10_000, NOW, NOW + 10 * H, NOW + 30 * timedelta(minutes=1))
    assert late.reason is None  # fits between now and the prices' end
    beyond = advise(_slots([0.2]), 20, 10_000, NOW, NOW + 10 * H, NOW)
    assert beyond.reason == "beyond_prices" and beyond.prices_until == NOW + H
    assert advise([], 10, 10_000, NOW, NOW + 3 * H, NOW).reason == "no_prices"
    assert advise(slots, 0, 10_000, NOW, NOW + 3 * H, NOW).reason == "invalid"


def test_not_before_now() -> None:
    """A period that began already: the block starts now at the earliest."""
    slots = _slots([0.05, 0.30, 0.30])
    advice = advise(
        slots, 10, 10_000, NOW - 5 * H, NOW + 3 * H, NOW + 30 * timedelta(minutes=1)
    )
    assert advice.start >= NOW + 30 * timedelta(minutes=1)


def test_slots_from_the_plan() -> None:
    plan = SimpleNamespace(
        slots=[
            SimpleNamespace(
                start=NOW, end=NOW + H, price=0.2, export_price=0.05, grid_w=-800.0
            ),
            SimpleNamespace(
                start=NOW + H,
                end=NOW + 2 * H,
                price=None,
                export_price=None,
                grid_w=300.0,
            ),
        ]
    )
    (slot,) = slots_from_plan(plan)
    assert slot.surplus_w == 800.0 and slot.price == 0.2
    assert slots_from_plan(None) == []
