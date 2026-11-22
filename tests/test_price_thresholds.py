"""Price thresholds of the arbitrage plan: above which price using the
batteries pays and below which charging from the grid pays."""

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
    MODE_NOM,
    PlanRules,
    plan_batteries,
)
from custom_components.homebatteryassist.engine.sources.prices.price_points import (
    PricePoint,
)

T0 = datetime(2026, 11, 16, 0, 0, tzinfo=dt_util.UTC)
H = timedelta(hours=1)
PRICES = [0.36, 0.35, 0.34, 0.36, 0.47, 0.45, 0.40, 0.38, 0.39, 0.50, 0.52, 0.48, 0.42]


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


def _plan(soc, prices=PRICES, mode=MODE_ARBITRAGE, rules=None):
    slots = [
        ForecastSlot(T0 + i * H, T0 + (i + 1) * H, 600.0, 600.0, "hour")
        for i in range(len(prices))
    ]
    points = [PricePoint(T0 + i * H, T0 + (i + 1) * H, p) for i, p in enumerate(prices)]
    return plan_batteries(
        [_battery(soc)], slots, {}, points, mode=mode, rules=rules or PlanRules()
    )


@pytest.mark.parametrize("soc", [10.0, 50.0, 90.0])
def test_the_plan_agrees_with_its_thresholds(soc):
    plan = _plan(soc)
    known = 0
    for s in plan.slots:
        if s.power_w < -100 and s.use_above is not None:
            assert s.price >= s.use_above - 0.01, s
            known += 1
        if s.power_w > 100 and s.charge_below is not None:
            assert s.price <= s.charge_below + 0.01, s
            known += 1
        if abs(s.power_w) < 1:
            if s.use_above is not None:
                assert s.price <= s.use_above + 0.01, s
            if s.charge_below is not None:
                assert s.price >= s.charge_below - 0.01, s
    assert known


def test_using_pays_above_charging_below():
    for s in _plan(50.0).slots:
        if s.use_above is not None and s.charge_below is not None:
            # A round trip costs: the two never cross.
            assert s.charge_below < s.use_above


def test_price_rules_hold_in_the_thresholds():
    plan = _plan(50.0, rules=PlanRules(max_charge_price=0.20, min_discharge_price=0.49))
    assert all(s.charge_below is None or s.charge_below <= 0.20 for s in plan.slots)
    assert all(s.use_above is None or s.use_above >= 0.49 for s in plan.slots)


def test_no_thresholds_without_a_planner_that_knows_them():
    assert all(
        s.use_above is None and s.charge_below is None
        for s in _plan(50.0, mode=MODE_NOM).slots
    )


@pytest.fixture
def utc():
    """Local time = UTC (the times in the texts are local)."""
    before = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(dt_util.UTC)
    yield
    dt_util.set_default_time_zone(before)


@pytest.mark.usefixtures("utc")
def test_summary_tells_now_with_the_thresholds():
    from custom_components.homebatteryassist.engine.explain.plan_summary import (
        plan_summary,
        state_text,
    )

    plan = _plan(50.0)
    now = T0 + timedelta(minutes=30)  # idle, waiting for the evening
    nl = plan_summary(plan, plan.slots, now, plan.strategy, 10.0, "nl", "EUR")
    assert nl["now"].startswith("Wachten tot ")
    assert "loont pas boven € 0,47" in nl["now"]
    assert "laden uit het net onder € 0,3" in nl["now"]
    assert nl["use_above"] == plan.slots[0].use_above
    assert nl["plan"].startswith("Leveren 09:00-12:00.")
    assert "Verwachte winst tot " in nl["plan"]
    assert [line["label"] for line in nl["lines"]][:3] == ["Nu", "Straks", "Plan"]
    assert nl["next"].startswith("09:00: leveren tot 12:00")
    en = plan_summary(plan, plan.slots, now, plan.strategy, 10.0, "en", "EUR")
    assert en["now"].startswith("Waiting until ")
    assert "only pays above € 0.47" in en["now"]
    assert len(state_text({"now": "x" * 400})) == 255
    # The state: short, with the price now and the thresholds.
    assert nl["state"].startswith("Wachten tot ")
    assert "Stroom nu € 0,360." in nl["state"]
    assert "Gebruiken loont boven € 0,47" in nl["state"]
    assert len(nl["state"]) < 160
    assert state_text(nl) == nl["state"]


@pytest.mark.usefixtures("utc")
def test_summary_cheapest_published_and_sun():
    from custom_components.homebatteryassist.engine.explain.plan_summary import (
        plan_summary,
    )

    plan = _plan(50.0)
    now = T0 + timedelta(minutes=30)
    summary = plan_summary(
        plan,
        plan.slots,
        now,
        plan.strategy,
        10.0,
        "en",
        "EUR",
        {T0 + 10 * H: 800.0},
        T0 + 6 * H,
    )
    # Only published prices count: 02:00 (0.34), not later estimates.
    assert summary["cheapest"].startswith("02:00-03:00: € 0.340 per kWh")
    assert "prices known until 06:00" in summary["cheapest"]
    assert summary["sun"].startswith("expected 0.8 kWh more today")
