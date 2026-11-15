"""Tests for checking the battery plan afterwards."""

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.planning.battery_plan import PlanSlot
from custom_components.homebatteryassist.planning.verification import (
    PlanVerification,
    slot_saving,
)

T0 = datetime(2026, 11, 16, 1, 0, tzinfo=dt_util.UTC)
Q = timedelta(minutes=15)


def _slot(start: datetime, power: float, grid: float, price: float = 0.30) -> PlanSlot:
    return PlanSlot(start, start + Q, power, 50.0, grid, price)


def test_slot_saving() -> None:
    """Discharging 1 kW for a quarter while importing saves 0.25 kWh x price."""
    slot = _slot(T0, -1000.0, 500.0)  # house 1500 W, battery covers 1000 W
    assert round(slot_saving(slot, 1.0, 0.0), 4) == round(0.25 * 0.30, 4)
    assert round(slot_saving(slot, 1.0, 0.02), 4) == round(0.25 * 0.30 - 0.25 * 0.02, 4)
    assert slot_saving(_slot(T0, 0, 0, None), 1.0, 0.0) is None


async def test_plan_versus_counters(hass: HomeAssistant) -> None:
    """The finished slot is compared with the batteries' energy counters."""
    check = PlanVerification(hass, "test")
    totals = {"charged_kwh": 10.0, "discharged_kwh": 5.0, "value": 1.0}
    plan = [_slot(T0, 2000.0, 2500.0, 0.10), _slot(T0 + Q, 0.0, 500.0)]

    check.settle(T0, lambda: dict(totals))  # first snapshot
    check.record_plan(plan, "arbitrage", T0, 1.0, 0.0)
    # A later cycle in the same slot does not overwrite it.
    check.record_plan([_slot(T0, 0.0, 500.0)], "arbitrage", T0 + Q / 2, 1.0, 0.0)
    totals.update(charged_kwh=10.4, value=0.96)  # 0.4 kWh in 15 min = 1600 W
    check.settle(T0 + Q, lambda: dict(totals))

    (record,) = check.records
    assert record["plan_w"] == 2000.0
    assert record["actual_w"] == 1600.0
    assert record["value"] == -0.04
    (day,) = check.days()
    assert day["power_deviation_w"] == 400
    assert day["slots"] == 1
