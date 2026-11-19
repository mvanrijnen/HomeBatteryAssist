"""Tests for the plan phases (status sensors)."""

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.explain.plan_phases import (
    current_and_next,
    phase_attributes,
    slot_parts,
)
from custom_components.homebatteryassist.engine.planning.battery_plan import PlanSlot

T0 = datetime(2026, 11, 20, 0, 0, tzinfo=dt_util.UTC)
H = timedelta(hours=1)


def _slot(
    hour: int, power: float, grid: float, price: float, soc: float = 50.0
) -> PlanSlot:
    return PlanSlot(
        T0 + hour * H, T0 + (hour + 1) * H, power, soc, grid, price, export_price=0.05
    )


def _plan() -> list[PlanSlot]:
    return [
        _slot(0, 2000.0, 2500.0, 0.20, 20.0),  # charge from the grid (house 500 W)
        _slot(1, 2000.0, 2500.0, 0.21, 40.0),
        _slot(2, 0.0, 600.0, 0.30),  # grid only
        _slot(3, 1500.0, -200.0, 0.30),  # solar surplus 1700 W: charge with solar
        _slot(4, -1000.0, 0.0, 0.45),  # discharge, expensive
        _slot(5, -1000.0, 0.0, 0.40),
    ]


def test_slot_parts() -> None:
    assert slot_parts(_slot(0, 2000.0, 2500.0, 0.2)) == {"charge_grid": 2000.0}
    assert slot_parts(_slot(0, 1500.0, -200.0, 0.2)) == {"charge_pv": 1500.0}
    mixed = slot_parts(_slot(0, 1500.0, 1000.0, 0.2))  # 500 W solar, 1000 W grid
    assert mixed == {"charge_pv": 500.0, "charge_grid": 1000.0}
    assert slot_parts(_slot(0, 0.0, 600.0, 0.2)) == {"grid_only": 600.0}
    assert slot_parts(_slot(0, -900.0, 0.0, 0.2)) == {"discharge": 900.0}


def test_current_and_next_with_reasons(hass: HomeAssistant) -> None:
    plan = _plan()
    now = T0 + timedelta(minutes=30)
    current, following = current_and_next(
        plan, "charge_grid", now, "arbitrage", language="nl"
    )
    assert following is None
    # A running phase: what is left from now (90 of 120 minutes).
    assert current.start == T0 and current.minutes == 90 and round(current.wh) == 3000
    assert "goedkoop" in current.reason and "0,45" in current.reason  # later up to
    current, following = current_and_next(
        plan, "discharge", now, "arbitrage", language="en"
    )
    assert current is None and following.start == T0 + 4 * H
    assert round(following.wh) == 2000 and "expensive" in following.reason
    _, grid_only = current_and_next(plan, "grid_only", now, "arbitrage", language="en")
    assert "keep their energy" in grid_only.reason
    _, pv = current_and_next(plan, "charge_pv", now, "arbitrage", language="en")
    assert pv.start == T0 + 3 * H and pv.price == 0.05
    nom, _ = current_and_next(plan, "discharge", T0 + 4 * H, "nom", language="en")
    assert "zero on the meter" in nom.reason


def test_attributes_per_battery() -> None:
    _, following = current_and_next(
        _plan(), "discharge", T0, "arbitrage", language="en"
    )
    shares = {"a": ("Venus", 0.75), "b": ("Virtual", 0.25)}
    total = phase_attributes(following, "next_", shares)
    assert total["next_kwh"] == 2.0 and total["next_minutes"] == 120
    assert total["next_batteries"] == {"Venus": 1.5, "Virtual": 0.5}
    one = phase_attributes(following, "next_", shares, 0.75)
    assert one["next_kwh"] == 1.5 and "next_batteries" not in one
    assert phase_attributes(None, "current_", shares) == {"current_start": None}
