"""Review round 14: one test per defect found (each fails without its fix)."""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.measure import (  # noqa: F401
    battery_monitor,
    house_measurement,
)

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=dt_util.UTC)
H = timedelta(hours=1)


def test_twin_grid_unknown_while_its_real_battery_is_unknown() -> None:
    """The grid without the twinned real battery is not known while that
    battery's power is unknown (not counted as 0 W)."""
    from custom_components.homebatteryassist.engine.measure.battery_monitor import (
        BatteryInput,
    )

    real = SimpleNamespace(id="r", virtual=False)
    twin = SimpleNamespace(id="t", virtual=True, twin_of="r")
    fake = SimpleNamespace(
        configs=[real, twin],
        states={
            "r": SimpleNamespace(power_w=None),
            "t": SimpleNamespace(power_w=500.0),
        },
        grid_now=lambda: 1000.0,
    )
    assert BatteryInput.grid_planned_w(fake) is None
    fake.states["r"].power_w = -800.0
    assert BatteryInput.grid_planned_w(fake) == 1000.0 + 500.0 + 800.0


def test_efficiency_starts_anew_after_an_uncounted_stretch() -> None:
    """Energy the counters missed (a restart while the battery moved) is not
    in the round trip: only day starts after it count."""
    from custom_components.homebatteryassist.engine.measure.battery_monitor import (
        measured_efficiency,
    )

    days = [
        {"date": "2026-11-10", "charged": 0.0, "discharged": 0.0, "stored": 2.0},
        {"date": "2026-11-14", "charged": 6.0, "discharged": 4.0, "stored": 2.0},
    ]
    stats = {"days": days, "charged_kwh": 12.0, "discharged_kwh": 9.4}
    first = measured_efficiency(stats, 2.5, 5.0)
    assert first is not None and first.charged_kwh == 12.0
    stats["uncounted"] = datetime(2026, 11, 12, 3, tzinfo=dt_util.UTC).isoformat()
    after = measured_efficiency(stats, 2.5, 5.0)
    assert after is not None and after.charged_kwh == 6.0  # from 14 Nov on


def _monitor(stats: dict) -> SimpleNamespace:
    from custom_components.homebatteryassist.engine.measure.battery_monitor import (
        BatteryInput,
    )

    fake = SimpleNamespace(stats={"b": stats}, _armed={})
    fake.reached = lambda soc: BatteryInput._full_reached(fake, "b", soc)
    return fake


def test_full_charge_across_a_gap_and_no_flapping() -> None:
    """Full after a gap (last known 80 %, then 100 %) counts; the first
    value ever does not; 100/99 flapping after a full charge does not."""
    fresh = _monitor({})
    assert not fresh.reached(100.0)  # the first value ever
    gap = _monitor({"last_soc": 80.0})  # known before a restart
    assert gap.reached(100.0)
    gap.stats["b"]["last_full_charge"] = "2026-11-16T12:00:00+00:00"
    assert not gap.reached(99.0)
    assert not gap.reached(100.0)  # flapping: not a new one
    assert not gap.reached(90.0)
    assert gap.reached(100.0)  # after a real drop


def test_capacity_in_wh_is_converted() -> None:
    from custom_components.homebatteryassist.const import CONF_CAPACITY
    from custom_components.homebatteryassist.engine.devices.batteries.recognition import (
        _factor,
    )

    states = {
        "sensor.cap_wh": SimpleNamespace(attributes={"unit_of_measurement": "Wh"}),
        "sensor.cap_pct": SimpleNamespace(attributes={"unit_of_measurement": "%"}),
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))
    assert _factor(hass, "sensor.cap_wh", CONF_CAPACITY) == 0.001
    assert _factor(hass, "sensor.cap_pct", CONF_CAPACITY) is None


def test_window_ends_at_a_gap_in_the_prices() -> None:
    from custom_components.homebatteryassist.engine.coordinator import _contiguous_end
    from custom_components.homebatteryassist.engine.sources.prices.price_points import (
        PricePoint,
    )

    prices = [PricePoint(NOW + i * H, NOW + (i + 1) * H, 0.2) for i in (0, 1, 2, 4, 5)]
    assert _contiguous_end(prices, NOW + timedelta(minutes=30)) == NOW + 3 * H
    assert _contiguous_end(prices[:3], NOW) == NOW + 3 * H


async def test_polling_meter_sets_nothing_after_stop(hass) -> None:
    """A poll still running when the meter stops (reload) sets no values
    and starts no stale timer afterwards."""
    from custom_components.homebatteryassist.engine.devices.meters.direct_reading import (
        PollingMeter,
    )

    gate = asyncio.Event()

    class Slow(PollingMeter):
        label = "slow"

        async def _async_read(self):
            await gate.wait()
            return (100.0,)

    meter = Slow(hass, "1.2.3.4")
    task = hass.async_create_task(meter._async_poll(None))
    await asyncio.sleep(0)
    await meter.async_stop()
    gate.set()
    await task
    assert meter.phase_w in ((), None) and meter.count == 0


def test_price_forecast_unit_is_used() -> None:
    from custom_components.homebatteryassist.engine.sources.prices.price_forecasts import (
        StroomprijsprognoseDriver,
    )

    driver = StroomprijsprognoseDriver.__new__(StroomprijsprognoseDriver)
    data = driver.parse(
        {
            "series": {
                "price": [
                    {
                        "start": "2026-11-16T12:00:00+00:00",
                        "end": "2026-11-16T13:00:00+00:00",
                        "value": 25.0,
                        "unit": "ct/kWh",
                    }
                ]
            }
        }
    )
    assert data.points[0].price == pytest.approx(0.25)


def test_weerlive_live_as_a_dict() -> None:
    from custom_components.homebatteryassist.engine.sources.weather.weerlive_api import (
        parse_weerlive,
        weerlive_error,
    )

    payload = {"liveweer": {"temp": 7.5, "fout": "x"}}
    assert parse_weerlive(payload)[0] == 7.5
    assert weerlive_error(payload) == "x"
