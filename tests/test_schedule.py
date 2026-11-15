"""Tests for time slots and the manual mode."""

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.forecasts.consumption import ForecastSlot
from custom_components.homebatteryassist.inputs.prices import PricePoint
from custom_components.homebatteryassist.planning.battery_plan import (
    MODE_MANUAL,
    MODE_TIME_SLOTS,
    plan_batteries,
)
from custom_components.homebatteryassist.planning.schedule import (
    Target,
    TimeSlot,
    slot_target,
)

from .test_battery_plan import _battery

H = timedelta(hours=1)


async def test_slot_active_past_midnight(hass: HomeAssistant) -> None:
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    slot = TimeSlot.from_data(
        {
            "name": "Night",
            "start": "23:00:00",
            "end": "02:00:00",
            "days": ["mon"],
            "action": "charge",
            "power": 1500,
        }
    )
    tz = dt_util.get_default_time_zone()
    monday = datetime(2026, 11, 16, 23, 30, tzinfo=tz)
    assert slot.active(monday)
    assert slot.active(monday + timedelta(hours=2))  # Tuesday 01:30
    assert not slot.active(monday + timedelta(hours=3))  # Tuesday 02:30
    assert not slot.active(monday - timedelta(days=1))  # Sunday 23:30
    assert slot_target([slot], monday) == Target(1500.0, None, "Night")


async def test_plan_follows_time_slots_and_manual(hass: HomeAssistant) -> None:
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    tz = dt_util.get_default_time_zone()
    t0 = datetime(2026, 11, 16, 0, 0, tzinfo=tz)
    slots = [
        ForecastSlot(t0 + i * H, t0 + (i + 1) * H, 500.0, 500.0, "hour")
        for i in range(4)
    ]
    prices = [PricePoint(s.start, s.end, 0.3) for s in slots]
    charge = TimeSlot.from_data(
        {
            "name": "Cheap",
            "start": "01:00:00",
            "end": "03:00:00",
            "days": ["mon"],
            "action": "charge",
            "power": 2000,
            "soc": 60,
        }
    )
    plan = plan_batteries(
        [_battery(soc=50.0)],
        slots,
        {},
        prices,
        mode=MODE_TIME_SLOTS,
        target=lambda when: slot_target([charge], when),
    )
    assert plan.strategy == MODE_TIME_SLOTS
    assert plan.slots[0].power_w < 0 and plan.slots[0].reason is None  # NOM
    assert plan.slots[1].power_w > 0 and plan.slots[1].reason == "Cheap"
    assert max(s.soc for s in plan.slots) <= 60.1  # stops at the slot's SoC

    manual = plan_batteries(
        [_battery(soc=50.0)],
        slots,
        {},
        prices,
        mode=MODE_MANUAL,
        target=lambda when: Target(-1000.0, None, "manual"),
    )
    # 1000 W, until the battery reaches its minimum (5 kWh, 50 % -> 10 %).
    assert [s.power_w for s in manual.slots] == [-1000.0, -800.0, 0.0, 0.0]
    assert manual.slots[0].reason == "manual"
