"""The arbitrage plan does not flip between cycles on a price right at its
threshold: what the batteries do now changes only when that clearly pays."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from homeassistant.util import dt as dt_util

import custom_components.homebatteryassist  # noqa: F401
from custom_components.homebatteryassist.engine.forecast.consumption_forecast import (
    ForecastSlot,
)
from custom_components.homebatteryassist.engine.planning.battery_plan import (
    MODE_ARBITRAGE,
    plan_batteries,
)
from custom_components.homebatteryassist.engine.sources.prices.price_points import (
    PricePoint,
)

T0 = datetime(2026, 11, 16, 6, 0, tzinfo=dt_util.UTC)
H = timedelta(hours=1)
# Now a middle price; later an expensive evening the battery cannot fully
# cover, so a kWh now competes with a kWh in the evening.
LATER = [0.40, 0.39, 0.38, 0.40, 0.42, 0.50, 0.52, 0.51, 0.50, 0.40]


def _battery():
    config = SimpleNamespace(
        capacity_kwh=2.0,
        min_soc=10.0,
        max_soc=100.0,
        max_charge_w=2500.0,
        max_discharge_w=2500.0,
        efficiency=0.81,
    )
    return SimpleNamespace(soc=60.0, config=config)


def _plan(now_price, previous=None):
    prices = [now_price, *LATER]
    slots = [
        ForecastSlot(T0 + i * H, T0 + (i + 1) * H, 600.0, 600.0, "hour")
        for i in range(len(prices))
    ]
    points = [PricePoint(T0 + i * H, T0 + (i + 1) * H, p) for i, p in enumerate(prices)]
    return plan_batteries(
        [_battery()],
        slots,
        {},
        points,
        mode=MODE_ARBITRAGE,
        now=T0,
        previous=previous,
    )


def test_sticks_to_the_previous_plan_at_the_threshold():
    use = _plan(0.40).slots[0].use_above
    assert use is not None
    discharging = _plan(use + 0.02)
    assert discharging.slots[0].power_w < -100
    just_below = use - 0.003
    # Without a previous plan: not worth it.
    assert abs(_plan(just_below).slots[0].power_w) < 1
    # The previous plan discharged now: kept for so small a difference.
    assert _plan(just_below, discharging).slots[0].power_w < -100
    # Clearly below the threshold: changed after all.
    assert abs(_plan(use - 0.05, discharging).slots[0].power_w) < 1
    # And the other way: idle stays idle just above the threshold.
    idle = _plan(use - 0.05)
    assert abs(_plan(use + 0.003, idle).slots[0].power_w) < 1
