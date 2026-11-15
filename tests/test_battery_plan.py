"""Tests for the battery plan (NOM and arbitrage)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.forecasts.consumption import ForecastSlot
from custom_components.homebatteryassist.inputs.prices import PricePoint
from custom_components.homebatteryassist.planning.battery_plan import (
    MODE_ARBITRAGE,
    MODE_NOM,
    plan_batteries,
)

T0 = datetime(2026, 11, 16, 0, 0, tzinfo=dt_util.UTC)
H = timedelta(hours=1)


def _battery(soc: float = 50.0, capacity: float = 5.0, power: float = 2500.0):
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


def test_nom_follows_surplus_and_shortage() -> None:
    """NOM: charge with PV surplus, discharge on shortage, never from the grid."""
    slots = _slots([500.0, 500.0, 500.0])
    pv = {T0: 1500.0, T0 + H: 0.0, T0 + 2 * H: 500.0}
    plan = plan_batteries(
        [_battery()], slots, pv, _prices([0.3, 0.3, 0.3]), mode=MODE_NOM
    )
    assert plan.strategy == MODE_NOM
    assert [s.power_w for s in plan.slots] == [1000.0, -500.0, 0.0]
    assert [s.grid_w for s in plan.slots] == [0.0, 0.0, 0.0]
    assert plan.saving is not None


def test_arbitrage_charges_cheap_discharges_expensive() -> None:
    """Arbitrage charges from the grid when cheap and discharges when expensive."""
    slots = _slots([500.0] * 4)
    prices = _prices([0.10, 0.10, 0.50, 0.50])
    arbitrage = plan_batteries(
        [_battery(soc=10.0)], slots, {}, prices, mode=MODE_ARBITRAGE
    )
    nom = plan_batteries([_battery(soc=10.0)], slots, {}, prices, mode=MODE_NOM)
    assert arbitrage.strategy == MODE_ARBITRAGE
    assert arbitrage.slots[0].power_w > 0 and arbitrage.slots[1].power_w > 0
    assert arbitrage.slots[2].power_w < 0 and arbitrage.slots[3].power_w < 0
    assert arbitrage.saving > nom.saving  # NOM cannot use the cheap hours
    assert arbitrage.saving > 0


def test_limits_are_respected() -> None:
    """Power and state of charge stay within the battery limits."""
    slots = _slots([3000.0] * 6)
    prices = _prices([0.5] * 6)
    plan = plan_batteries(
        [_battery(soc=100.0, power=1000.0)], slots, {}, prices, mode=MODE_ARBITRAGE
    )
    assert all(-1000.0 - 1e-6 <= s.power_w <= 1000.0 + 1e-6 for s in plan.slots)
    assert all(10.0 - 0.5 <= s.soc <= 100.0 + 0.5 for s in plan.slots)


def test_without_prices_falls_back_to_nom() -> None:
    """No prices: arbitrage is not possible."""
    slots = _slots([500.0, 500.0])
    plan = plan_batteries([_battery()], slots, {T0: 2000.0}, [], mode=MODE_ARBITRAGE)
    assert plan.mode == MODE_ARBITRAGE
    assert plan.strategy == MODE_NOM
    assert plan.saving is None
    assert plan_batteries([], slots, {}, [], mode=MODE_NOM) is None


def test_several_batteries_are_planned_as_one() -> None:
    """Capacity and power of several batteries add up."""
    slots = _slots([0.0])
    pv = {T0: 4000.0}
    plan = plan_batteries(
        [_battery(soc=10.0), _battery(soc=10.0)], slots, pv, [], mode=MODE_NOM
    )
    assert plan.slots[0].power_w == pytest.approx(4000.0)
