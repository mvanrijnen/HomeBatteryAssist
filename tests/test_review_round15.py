"""Review round 15: one test per defect found (each fails without its fix)."""

from dataclasses import replace as dataclass_replace
from datetime import timedelta
from types import SimpleNamespace

import pytest

from custom_components.homebatteryassist.engine.control.pd_controller import PdSettings

from .test_review_round13 import T1, _sim


def _nom(sim, grid_w: float) -> None:
    """The measured grid now (virtual batteries are not in it)."""
    flow = sim._measurements.flow
    from dataclasses import replace

    sim._measurements.flow = replace(flow, grid_w=grid_w, phase_w=(grid_w,))


def test_direct_extra_round_closes_the_whole_gap() -> None:
    """Direct zero on the meter: an extra round soon after the last one
    gives what the grid asks at once (not a part by the time since)."""
    sim, batteries = _sim([0.0], {"A": "l1"})
    sim.step(T1 + timedelta(seconds=5))
    _nom(sim, 1500.0)  # the house jumps
    sim._samples = []
    sim.step(T1 + timedelta(seconds=7))  # 2 s later (a jump round)
    assert batteries.states["A"].power_w == pytest.approx(-1500.0, abs=1)


def test_nom_resumes_from_its_own_wish_after_protection() -> None:
    """PD control: after protection held a battery at another power, zero on
    the meter starts from what it wants, not from the protection's power."""
    sim, batteries = _sim([500.0], {"A": "l1"})
    sim._direct = False
    sim._pd.settings = PdSettings(kp=0.35, kd=0.0, max_step_w=800, hysteresis_w=0)
    sim.step(T1 + timedelta(seconds=5))
    sim._commands = {"A": -2000.0}
    from custom_components.homebatteryassist.engine.measure.battery_monitor import (
        BatteryState,
    )

    config = batteries.configs[0]
    batteries.states["A"] = BatteryState(config, 50.0, -2000.0)
    sim._protected_last = True  # relief held it at -2000 W last round
    sim._samples = []
    sim.step(T1 + timedelta(seconds=10))
    assert batteries.states["A"].power_w == pytest.approx(-500.0, abs=1)


def test_spike_ignored_over_the_same_time_as_the_grid() -> None:
    """A peak ignored for most of the round that ended just before it: its
    ignored part is averaged like the grid (no discharge for it)."""
    sim, batteries = _sim([500.0], {"A": "l1"})
    sim._forecast.spike_ignore_w = lambda w, now: w
    sim._forecast.react_average = True
    sim._measurements.spike.ignore_w = 0.0  # over now
    start = T1
    sim._samples = [
        (start, 2500.0, 0.0, 2000.0),  # kettle 2 kW, ignored, 4 s
        (start + timedelta(seconds=4), 500.0, 0.0, 0.0),  # gone, 1 s
    ]
    sim.step(T1 + timedelta(seconds=5))
    assert batteries.states["A"].power_w == pytest.approx(-500.0, abs=2)


def test_extra_round_averages_from_the_previous_round() -> None:
    """An extra round 2 s after a round averages only those 2 s (the round
    before already acted on what came earlier)."""
    sim, batteries = _sim([1500.0], {"A": "l1"})
    sim._forecast.react_average = True
    sim._samples = [(T1, 1500.0, 0.0, 0.0)]
    sim.step(T1 + timedelta(seconds=5))
    assert batteries.states["A"].power_w == pytest.approx(-1500.0, abs=1)
    # The house drops by 1 kW right after that round.
    _nom(sim, 500.0)
    sim._samples = [(T1 + timedelta(seconds=5), 500.0, 0.0, 0.0)]
    sim._samples.insert(0, (T1 + timedelta(seconds=1), 1500.0, 0.0, 0.0))
    sim.step(T1 + timedelta(seconds=7))
    # The measured grid holds no virtual power: zero on the meter wants
    # -500 W from 500 W since the last round, not the 1500 W before it.
    assert batteries.states["A"].power_w == pytest.approx(-500.0, abs=1)


def test_evening_stays_night_with_daylight_only_pv() -> None:
    """A PV source that sends daylight hours only: this evening (after the
    last sun hour, no PV keys left today) is still night; a day after the
    forecast is not."""
    from datetime import datetime

    from homeassistant.util import dt as dt_util

    from custom_components.homebatteryassist.engine.forecast.consumption_forecast import (
        ForecastSlot,
    )
    from custom_components.homebatteryassist.engine.planning.battery_plan import (
        night_starts,
    )

    old = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(dt_util.UTC)
    try:
        h = timedelta(hours=1)
        now = datetime(2026, 11, 16, 20, 0, tzinfo=dt_util.UTC)  # evening
        slots = [
            ForecastSlot(now + i * h, now + (i + 1) * h, 300.0, 300.0, "h")
            for i in range(52)
        ]
        day2 = datetime(2026, 11, 17, tzinfo=dt_util.UTC)
        sun = {day2 + i * h: 2000.0 for i in range(9, 16)}  # tomorrow only
        night = night_starts(slots, sun)
        assert now in night and now + 3 * h in night  # this evening
        assert day2 + 2 * h in night and day2 + 20 * h in night
        assert day2 + 12 * h not in night
        assert not any(day2 + 24 * h + i * h in night for i in range(24))  # beyond
    finally:
        dt_util.set_default_time_zone(old)


def test_twin_real_unknown_holds_and_explains() -> None:
    """A real battery with a twin whose power is unknown: the virtual
    batteries hold (the grid without it is unknown), and Why says so once."""
    from custom_components.homebatteryassist.engine.measure.battery_monitor import (
        BatteryState,
    )

    sim, batteries = _sim([1000.0], {"A": "l1"})
    real = SimpleNamespace(id="R", name="Real", virtual=False, twin_of="", phase="l1")
    batteries.configs[0] = dataclass_replace(batteries.configs[0], twin_of="R")
    batteries.configs.append(real)
    batteries.states["R"] = BatteryState(real, 50.0, None)
    logged = []
    sim._decisions = SimpleNamespace(async_log=lambda *a, **k: logged.append(a[1]))
    sim.step(T1 + timedelta(seconds=5))
    assert batteries.states["A"].power_w == 0.0
    sim.step(T1 + timedelta(seconds=10))
    assert logged.count("twin_real_unknown_hold") == 1


def test_full_charge_guard_survives_a_restart() -> None:
    """After a full charge, a restart while the SoC flaps 99/100 does not
    count a new one (the guard is kept in the counters)."""
    from custom_components.homebatteryassist.engine.measure.battery_monitor import (
        BatteryInput,
    )

    stats = {"last_soc": 80.0}
    first = SimpleNamespace(stats={"b": stats}, _armed={})
    assert BatteryInput._full_reached(first, "b", 100.0)
    stats["last_full_charge"] = "2026-11-16T12:00:00+00:00"
    assert not BatteryInput._full_reached(first, "b", 99.0)
    restarted = SimpleNamespace(stats={"b": stats}, _armed={})  # new instance
    assert not BatteryInput._full_reached(restarted, "b", 100.0)


async def test_prediction_of_another_length_is_not_settled(hass) -> None:
    """After the history interval changed, an hourly prediction is not
    compared with a quarter record (or the other way round)."""
    from datetime import datetime

    from homeassistant.util import dt as dt_util

    from custom_components.homebatteryassist.engine.evaluation.forecast_accuracy import (
        ForecastAccuracy,
    )

    acc = ForecastAccuracy(hass, "t")
    start = datetime(2026, 11, 16, 12, tzinfo=dt_util.UTC)
    hour = timedelta(hours=1)
    acc.record("consumption", [(start, start + hour, 500.0)], start - 3 * hour)
    record = {
        "start": start.isoformat(),
        "minutes": 15,
        "avg_w": 2000.0,
        "coverage": 1.0,
    }
    assert acc.evaluate_consumption([record]) == 0
    acc.record("consumption", [(start + hour, start + 2 * hour, 500.0)], start)
    same = dict(record, start=(start + hour).isoformat(), minutes=60)
    assert acc.evaluate_consumption(iter([same])) == 1  # a generator works too


def test_diagnostics_mask_addresses_in_texts() -> None:
    from custom_components.homebatteryassist.diagnostics import _addresses, _mask

    entry = SimpleNamespace(
        data={"meter_address": "192.168.1.50"},
        options={},
        subentries={"x": SimpleNamespace(data={"pv_address": "192.168.1.60"})},
    )
    result = _mask(
        {"missing": ["HomeWizard P1 192.168.1.50"], "why": ["kWh 192.168.1.60 gone"]},
        _addresses(entry),
    )
    assert "192.168" not in str(result)
