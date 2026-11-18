"""Tests for checking the battery plan afterwards."""

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.evaluation.plan_check import (
    PlanVerification,
    slot_followed,
    slot_saving,
)
from custom_components.homebatteryassist.engine.planning.battery_plan import PlanSlot

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


async def test_realised_value_after_wear(hass: HomeAssistant) -> None:
    """The realised value counts the same wear as the planned saving."""
    check = PlanVerification(hass, "test")
    totals = {"charged_kwh": 10.0, "discharged_kwh": 5.0, "value": 1.0}
    check.settle(T0, lambda: dict(totals), 0.05)
    check.record_plan([_slot(T0, 2000.0, 2500.0, 0.10)], "arbitrage", T0, 1.0, 0.05)
    totals.update(charged_kwh=10.4, value=0.96)
    check.settle(T0 + Q, lambda: dict(totals), 0.05)
    (record,) = check.records
    assert record["value"] == round(-0.04 - 0.4 * 0.05, 5)


def test_slot_followed() -> None:
    assert slot_followed(1000.0, 1000.0) == 1.0
    assert slot_followed(1000.0, 800.0) == 0.8
    assert slot_followed(0.0, 0.0) == 1.0  # idle as planned
    assert slot_followed(0.0, 20.0) == 0.6  # small: against at least 50 W
    assert slot_followed(-1000.0, 1000.0) == 0.0  # the wrong way


async def test_plan_followed_per_group(hass: HomeAssistant) -> None:
    """The plan for all batteries, split by capacity: the virtual battery
    follows its half, the real one (own control) does nothing."""
    check = PlanVerification(hass, "test")
    totals = {
        "charged_kwh": 0.0,
        "discharged_kwh": 0.0,
        "value": 0.0,
        "real_share": 0.5,
        "real_charged_kwh": 0.0,
        "real_discharged_kwh": 0.0,
        "virtual_charged_kwh": 0.0,
        "virtual_discharged_kwh": 0.0,
    }
    check.settle(T0, lambda: dict(totals))
    check.record_plan([_slot(T0, 2000.0, 2500.0)], "arbitrage", T0, 1.0, 0.0)
    # Virtual: 0.25 kWh in 15 min = 1000 W, its half of 2000 W.
    totals.update(charged_kwh=0.25, virtual_charged_kwh=0.25)
    check.settle(T0 + Q, lambda: dict(totals))
    (record,) = check.records
    assert record["virtual_w"] == 1000.0 and record["real_w"] == 0.0
    (day,) = check.days()
    assert day["followed_virtual"] == 100.0 and day["followed_real"] == 0.0
    followed = check.followed(T0 + Q)
    assert followed == {"days": 7, "real": 0.0, "virtual": 100.0}


async def test_plan_followed_without_groups(hass: HomeAssistant) -> None:
    """Records from before (no groups): nothing to tell."""
    check = PlanVerification(hass, "test")
    totals = {"charged_kwh": 0.0, "discharged_kwh": 0.0, "value": 0.0}
    check.settle(T0, lambda: dict(totals))
    check.record_plan([_slot(T0, 1000.0, 1500.0)], "arbitrage", T0, 1.0, 0.0)
    check.settle(T0 + Q, lambda: dict(totals))
    assert check.followed(T0 + Q) == {"days": 7, "real": None, "virtual": None}
