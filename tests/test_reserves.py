"""Tests for the night reserve and the peak reserve in the plans."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.forecast.consumption_forecast import (
    ForecastSlot,
)
from custom_components.homebatteryassist.engine.planning.battery_plan import (
    MODE_ARBITRAGE,
    MODE_NOM,
    PlanRules,
    night_starts,
    plan_batteries,
)
from custom_components.homebatteryassist.engine.sources.prices.price_points import (
    PricePoint,
)

H = timedelta(hours=1)


@pytest.fixture(autouse=True)
def _utc():
    """Local days = UTC days, so the night is where the test expects it."""
    old = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(dt_util.UTC)
    yield
    dt_util.set_default_time_zone(old)


T0 = datetime(2026, 11, 16, 0, 0, tzinfo=dt_util.UTC)


def _battery(soc: float, capacity: float = 5.0, power: float = 2500.0):
    config = SimpleNamespace(
        capacity_kwh=capacity,
        min_soc=10.0,
        max_soc=100.0,
        max_charge_w=power,
        max_discharge_w=power,
        efficiency=0.81,  # 0.9 each way
    )
    return SimpleNamespace(soc=soc, config=config)


def _slots(house: list[float]) -> list[ForecastSlot]:
    return [
        ForecastSlot(T0 + i * H, T0 + (i + 1) * H, w, w, "hour")
        for i, w in enumerate(house)
    ]


def _prices(values: list[float]) -> list[PricePoint]:
    return [PricePoint(T0 + i * H, T0 + (i + 1) * H, p) for i, p in enumerate(values)]


SUN = {T0 + i * H: 2000.0 for i in range(6, 10)}  # sun from 06:00 to 10:00


def test_night_is_outside_the_sun() -> None:
    """Night: before the first and after the last hour with sun; none
    without a PV forecast."""
    slots = _slots([300.0] * 12)
    assert night_starts(slots, SUN) == {T0 + i * H for i in (*range(6), 10, 11)}
    assert night_starts(slots, {}) == set()


def test_nom_keeps_the_night_reserve() -> None:
    """Zero on the meter discharges at night only down to the night reserve,
    and does not charge from the grid for it."""
    slots = _slots([500.0] * 10)
    plan = plan_batteries(
        [_battery(50.0)],
        slots,
        SUN,
        _prices([0.3] * 10),
        mode=MODE_NOM,
        rules=PlanRules(night_reserve_soc=40.0),
    )
    night = plan.slots[:6]
    assert night[0].power_w == pytest.approx(-450.0)  # 500 Wh x 0.9 above 40 %
    assert all(s.power_w <= 0 for s in night)
    assert min(s.soc for s in night) == pytest.approx(40.0)


def test_arbitrage_charges_for_the_night_reserve_before_sunrise() -> None:
    """Arbitrage: the night reserve missing at sunrise is charged from the
    grid at the cheapest moment before."""
    slots = _slots([300.0] * 10)
    prices = _prices([0.30, 0.30, 0.29, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30])
    without = plan_batteries([_battery(10.0)], slots, SUN, prices, mode=MODE_ARBITRAGE)
    assert all(s.power_w <= 0 for s in without.slots[:6])
    plan = plan_batteries(
        [_battery(10.0)],
        slots,
        SUN,
        prices,
        mode=MODE_ARBITRAGE,
        rules=PlanRules(night_reserve_soc=40.0),
    )
    assert plan.slots[2].power_w > 0  # the cheapest hour of the night
    assert plan.slots[5].soc >= 39.0


def test_peak_reserve_only_shaves_below_it() -> None:
    """Below the peak reserve only the import above the peak limit is
    discharged for."""
    slots = _slots([800.0, 800.0, 2000.0])
    plan = plan_batteries(
        [_battery(70.0)],
        slots,
        {},
        _prices([0.3] * 3),
        mode=MODE_NOM,
        peak_w=1000.0,
        rules=PlanRules(peak_reserve_soc=60.0),
    )
    assert [s.power_w for s in plan.slots] == pytest.approx([-450.0, 0.0, -1000.0])
    assert [s.grid_w for s in plan.slots] == pytest.approx([350.0, 800.0, 1000.0])


def test_peak_reserve_needs_a_peak_limit() -> None:
    """Without a peak limit the peak reserve does nothing."""
    plan = plan_batteries(
        [_battery(70.0)],
        _slots([800.0]),
        {},
        _prices([0.3]),
        mode=MODE_NOM,
        rules=PlanRules(peak_reserve_soc=60.0),
    )
    assert plan.slots[0].power_w == pytest.approx(-800.0)
