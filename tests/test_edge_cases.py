"""Edge cases: daylight saving time, odd inputs, restarts."""

from datetime import datetime, timedelta
from itertools import pairwise
from types import SimpleNamespace

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.forecasts.consumption import (
    forecast_consumption,
)
from custom_components.homebatteryassist.forecasts.horizon import (
    HorizonLimit,
    PlanningWindow,
)
from custom_components.homebatteryassist.inputs.prices import PricePoint
from custom_components.homebatteryassist.planning.battery_plan import (
    MODE_ARBITRAGE,
    MODE_NOM,
    plan_batteries,
)

from .test_battery_plan import _battery

# 25 October 2026: clocks go back from 03:00 to 02:00 in Europe/Amsterdam.
DST_END = datetime(2026, 10, 24, 22, 0, tzinfo=dt_util.UTC)  # 00:00 local (CEST)
Q = timedelta(minutes=15)


def _history(start: datetime, days: int, watts: float = 400.0) -> list[dict]:
    return [
        {
            "start": (start - i * Q).isoformat(),
            "minutes": 15,
            "avg_w": watts,
            "coverage": 1.0,
        }
        for i in range(1, days * 96 + 1)
    ]


async def test_forecast_over_dst_end(hass: HomeAssistant) -> None:
    """The night the clocks go back has 25 hours: every quarter is forecast once."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    window = PlanningWindow(
        DST_END, DST_END + timedelta(hours=25), HorizonLimit.SETTING
    )
    slots = forecast_consumption(_history(DST_END, 21), window, Q, now=DST_END)
    assert len(slots) == 100
    starts = [s.start for s in slots]
    assert len(set(starts)) == 100
    assert all(b - a == Q for a, b in pairwise(starts))
    assert {round(s.power_w) for s in slots} == {400}


async def test_plan_over_dst_end(hass: HomeAssistant) -> None:
    """Plans over the 25-hour day keep the energy balance."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    window = PlanningWindow(
        DST_END, DST_END + timedelta(hours=25), HorizonLimit.SETTING
    )
    consumption = forecast_consumption(_history(DST_END, 21), window, Q, now=DST_END)
    prices = [
        PricePoint(
            DST_END + i * timedelta(hours=1), DST_END + (i + 1) * timedelta(hours=1), p
        )
        for i, p in enumerate([0.2] * 6 + [0.5] * 19)
    ]
    for mode in (MODE_NOM, MODE_ARBITRAGE):
        plan = plan_batteries([_battery(soc=50.0)], consumption, {}, prices, mode=mode)
        assert len(plan.slots) == 100
        for slot in plan.slots:
            assert 10.0 - 0.05 <= slot.soc <= 100.0 + 0.05
            assert abs(slot.grid_w - (400.0 + slot.power_w)) < 0.2


def test_battery_above_maximum() -> None:
    """A battery above its configured maximum is not charged further."""
    battery = _battery(soc=95.0)
    battery.config.max_soc = 90.0
    start = datetime(2026, 11, 16, 12, 0, tzinfo=dt_util.UTC)
    consumption = [
        SimpleNamespace(start=start + i * Q, end=start + (i + 1) * Q, power_w=0.0)
        for i in range(4)
    ]
    plan = plan_batteries([battery], consumption, {start.replace(minute=0): 3000.0}, [])
    assert all(slot.power_w <= 0 for slot in plan.slots)


async def test_invalid_history_records_are_skipped(
    hass: HomeAssistant, hass_storage: dict
) -> None:
    """Damaged stored records do not break every forecast afterwards."""
    from custom_components.homebatteryassist.history import ConsumptionHistory

    good = {
        "start": "2026-11-16T10:00:00+00:00",
        "minutes": 15,
        "avg_w": 400.0,
        "coverage": 1.0,
    }
    hass_storage["homebatteryassist.test.consumption"] = {
        "version": 1,
        "key": "homebatteryassist.test.consumption",
        "data": {
            "records": [
                good,
                {"start": "2026-11-16T10:15:00+00:00", "minutes": 15, "avg_w": 400.0},
                {"start": "nonsense", "minutes": 15, "avg_w": 1.0, "coverage": 1.0},
                {
                    "start": "2026-11-16T10:30:00+00:00",
                    "minutes": 15,
                    "avg_w": None,
                    "coverage": 1.0,
                },
                "not a record",
            ]
        },
    }
    history = ConsumptionHistory(hass, "test", 15)
    await history.async_load()
    assert history.records == [good]


def test_negative_prices_charge() -> None:
    """With a negative import price, arbitrage charges (being paid to use power)
    and the saving compared with no battery is positive."""
    start = datetime(2026, 6, 1, 10, 0, tzinfo=dt_util.UTC)
    hour = timedelta(hours=1)
    consumption = [
        SimpleNamespace(
            start=start + i * hour, end=start + (i + 1) * hour, power_w=300.0
        )
        for i in range(6)
    ]
    prices = [
        PricePoint(start + i * hour, start + (i + 1) * hour, p)
        for i, p in enumerate([-0.10, -0.10, 0.25, 0.25, 0.40, 0.40])
    ]
    plan = plan_batteries(
        [_battery(soc=20.0)], consumption, {}, prices, mode=MODE_ARBITRAGE
    )
    assert plan.slots[0].power_w > 0 and plan.slots[1].power_w > 0
    assert plan.saving is not None and plan.saving > 0


async def test_direct_meter_goes_stale(hass: HomeAssistant, freezer) -> None:
    """A direct meter that stops sending tells its listeners, so the
    measurement becomes unknown instead of keeping the last value."""
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from custom_components.homebatteryassist.inputs.direct import DirectMeter

    freezer.move_to(DST_END)
    meter = DirectMeter(hass, "192.0.2.1")
    calls: list = []
    meter.async_add_listener(calls.append)
    meter._set((500.0,))
    assert meter.available and len(calls) == 1
    freezer.tick(timedelta(seconds=12))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not meter.available
    assert len(calls) == 2  # told once more: now unknown
    meter.cancel_stale()


def test_arbitrage_covers_small_loads() -> None:
    """A house load below one stored-energy level is still covered from a full,
    big battery when power is expensive."""
    battery = _battery(soc=90.0, capacity=15.0, power=5000.0)
    start = datetime(2026, 11, 16, 0, 0, tzinfo=dt_util.UTC)
    consumption = [
        SimpleNamespace(start=start + i * Q, end=start + (i + 1) * Q, power_w=300.0)
        for i in range(48)
    ]
    prices = [
        PricePoint(start + i * Q, start + (i + 1) * Q, 0.40 if i < 24 else 0.20)
        for i in range(48)
    ]
    plan = plan_batteries([battery], consumption, {}, prices, mode=MODE_ARBITRAGE)
    covered = [s for s in plan.slots[:24] if s.power_w < 0]
    assert len(covered) >= 20
    assert all(s.power_w >= -300.0 - 0.1 for s in plan.slots)  # never exports
