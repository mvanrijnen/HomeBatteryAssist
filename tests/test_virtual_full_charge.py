"""A forced full charge in the virtual battery simulator never undoes phase
relief or peak shaving."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.control.pd_controller import PdSettings
from custom_components.homebatteryassist.engine.devices.batteries.virtual import (
    VirtualBatterySimulator,
)
from custom_components.homebatteryassist.engine.measure.battery_monitor import (
    BatteryConfig,
    BatteryState,
)
from custom_components.homebatteryassist.engine.measure.house_measurement import (
    PowerFlow,
)
from custom_components.homebatteryassist.engine.planning.battery_plan import PlanRules

T0 = datetime(2026, 11, 16, 12, 0, tzinfo=dt_util.UTC)


def _config(bid: str, phase: str) -> BatteryConfig:
    return BatteryConfig(
        id=bid,
        name=bid,
        soc_sensor="",
        power_sensor="",
        power_sign="",
        capacity_kwh=10.0,
        max_charge_w=2000,
        max_discharge_w=2000,
        min_soc=10,
        max_soc=90,
        efficiency=1.0,
        full_charge_interval_days=0,
        phase=phase,
        virtual=True,
        initial_soc=50,
    )


class _Batteries:
    def __init__(self, configs: list[BatteryConfig]) -> None:
        self.configs = configs
        self.states = {c.id: BatteryState(c, c.initial_soc, 0.0) for c in configs}

    def set_virtual(self, bid, when, power, soc) -> None:
        config = next(c for c in self.configs if c.id == bid)
        self.states[bid] = BatteryState(config, soc, power)

    def plan_states(self):
        return list(self.states.values())

    def price_now(self):
        return None


class _Data:
    plan_mode = "nom"
    selected_plan = None

    def __init__(self) -> None:
        self.forced_by: dict = {}

    def full_charge_now(self, bid, now):
        return True if bid == "F" else None

    def night_at(self, now):
        return False

    def consumption_at(self, now):
        return None

    def pv_at(self, now):
        return None


def _step(phase_w, peak, max_current=63, phases=("none", "none")):
    configs = [_config("A", phases[0]), _config("F", phases[1])]
    batteries = _Batteries(configs)
    forecast = SimpleNamespace(
        balance_interval=timedelta(hours=1),
        phase_margin=0,
        react_interval=timedelta(seconds=5),
        react_jump_w=0,
        react_average=False,
        peak_w=peak,
        peak_include_excluded=True,
        rules=PlanRules(),
        data=_Data(),
        pd_settings=PdSettings(),
        nom_control="direct",
        sim_delay_s=0,
        sim_ramp_w_s=0,
        spike_ignore_w=lambda w, now: 0.0,
        pv_entries=[],
        pv_deviation_w=300,
        min_battery_power=0,
    )
    grid = sum(phase_w)
    measurements = SimpleNamespace(
        flow=PowerFlow(
            grid_w=grid,
            pv_w=0,
            excluded_w=0,
            battery_w=0,
            house_w=grid,
            phase_w=tuple(phase_w),
        ),
        max_current=max_current,
        spike=SimpleNamespace(ignore_w=0.0),
        has_pv=True,
        pv_known=True,
    )
    hass = SimpleNamespace(
        config=SimpleNamespace(language="en"),
        states=SimpleNamespace(get=lambda e: None),
    )
    sim = VirtualBatterySimulator(
        hass,
        batteries,
        measurements,
        forecast,
        SimpleNamespace(async_log=lambda *a, **k: None),
    )
    sim._quiet_until = sim._last = T0
    sim.step(T0 + timedelta(seconds=5))
    return {c.id: batteries.states[c.id].power_w for c in configs}


def test_full_charge_kept_under_the_peak() -> None:
    """The full charge takes only what the peak leaves."""
    powers = _step([4000.0], 5000)
    assert powers["F"] == pytest.approx(1000.0, abs=1) and powers["A"] == 0.0


def test_peak_shaving_beats_the_full_charge() -> None:
    """Above the peak: the full charge waits, the other battery shaves."""
    powers = _step([6000.0], 5000)
    assert powers["F"] == 0.0 and powers["A"] == pytest.approx(-1000.0, abs=1)


def test_phase_relief_beats_the_full_charge() -> None:
    """An overloaded phase is relieved although another battery charges
    fully (that one waits: never both directions)."""
    powers = _step([7000.0, 0.0, 0.0], 0, 25, ("l1", "l2"))
    assert powers["A"] <= -1249.0 and powers["F"] == 0.0
