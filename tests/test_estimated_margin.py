"""Margin for estimated prices: acting on an estimate must bring more."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.util import dt as dt_util

import custom_components.homebatteryassist  # noqa: F401
from custom_components.homebatteryassist.engine.forecast.consumption_forecast import (
    ForecastSlot,
)
from custom_components.homebatteryassist.engine.planning.battery_plan import (
    MODE_ARBITRAGE,
    PlanRules,
    plan_batteries,
)
from custom_components.homebatteryassist.engine.planning.ev_advice import (
    EvSlot,
    advise,
    slots_from_plan,
)
from custom_components.homebatteryassist.engine.sources.prices.price_points import (
    PricePoint,
)

T0 = datetime(2026, 11, 16, 0, 0, tzinfo=dt_util.UTC)
H = timedelta(hours=1)


def _battery(soc: float):
    config = SimpleNamespace(
        capacity_kwh=5.0,
        min_soc=10.0,
        max_soc=100.0,
        max_charge_w=2500.0,
        max_discharge_w=2500.0,
        efficiency=0.81,
    )
    return SimpleNamespace(soc=soc, config=config)


def _slots(count: int) -> list[ForecastSlot]:
    return [
        ForecastSlot(T0 + i * H, T0 + (i + 1) * H, 500.0, 500.0, "hour")
        for i in range(count)
    ]


def _prices(values) -> list[PricePoint]:
    return [
        PricePoint(T0 + i * H, T0 + (i + 1) * H, p, estimated)
        for i, (p, estimated) in enumerate(values)
    ]


def _plan(soc, prices, margin):
    return plan_batteries(
        [_battery(soc)],
        _slots(len(prices)),
        {},
        _prices(prices),
        mode=MODE_ARBITRAGE,
        rules=PlanRules(estimated_margin=margin),
    )


def test_charges_at_the_published_price_unless_the_estimate_is_clearly_cheaper():
    prices = [(0.30, False), (0.29, True), (0.50, False), (0.50, False)]
    eager = _plan(10.0, prices, 0.0)
    assert eager.slots[1].power_w > 0 and eager.slots[0].power_w <= 0
    careful = _plan(10.0, prices, 0.02)
    assert careful.slots[0].power_w > 0 and careful.slots[1].power_w <= 0
    assert careful.slots[1].price_margin == pytest.approx(0.02)
    assert careful.slots[0].price_margin == 0.0
    # Clearly cheaper (more than the margin): the estimate is used.
    cheap = [(0.30, False), (0.20, True), (0.50, False), (0.50, False)]
    assert _plan(10.0, cheap, 0.02).slots[1].power_w > 0


def test_does_not_hold_for_an_estimate_that_is_hardly_higher():
    prices = [(0.40, False), (0.41, True)]
    eager = _plan(20.0, prices, 0.0)
    assert eager.slots[1].power_w < 0 and eager.slots[0].power_w == 0
    careful = _plan(20.0, prices, 0.02)
    assert careful.slots[0].power_w < 0


def test_costs_are_at_the_prices_themselves():
    prices = [(0.30, False), (0.20, True), (0.50, False), (0.50, False)]
    assert _plan(10.0, prices, 0.02).cost == pytest.approx(
        _plan(10.0, prices, 0.0).cost
    )


def test_ev_advice_prefers_a_published_price():
    slots = [
        EvSlot(T0, T0 + H, 0.30, 0.05, 0.0),
        EvSlot(T0 + H, T0 + 2 * H, 0.29, 0.05, 0.0, margin=0.02),
    ]
    advice = advise(slots, 10, 10_000, T0, T0 + 2 * H, T0)
    assert advice.start == T0 and advice.cost == pytest.approx(3.0)
    slots[1] = EvSlot(T0 + H, T0 + 2 * H, 0.25, 0.05, 0.0, margin=0.02)
    advice = advise(slots, 10, 10_000, T0, T0 + 2 * H, T0)
    assert advice.start == T0 + H and advice.cost == pytest.approx(2.5)


def test_ev_slots_carry_the_margin():
    plan = SimpleNamespace(
        slots=[
            SimpleNamespace(
                start=T0,
                end=T0 + H,
                price=0.2,
                export_price=0.05,
                grid_w=0.0,
                price_margin=0.02,
            )
        ]
    )
    assert slots_from_plan(plan)[0].margin == 0.02
