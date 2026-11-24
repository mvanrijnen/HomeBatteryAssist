"""Guarding the minimum charge: a battery that sank more than 1 % below its
minimum (standby use) is charged back to 1 % above it; switchable."""

from datetime import timedelta
from types import SimpleNamespace

from custom_components.homebatteryassist.engine.control.pd_controller import PdSettings
from custom_components.homebatteryassist.engine.devices.batteries.virtual import (
    GUARD_W,
    VirtualBatterySimulator,
)
from custom_components.homebatteryassist.engine.measure.house_measurement import (
    PowerFlow,
)
from custom_components.homebatteryassist.engine.planning.battery_plan import PlanRules
from tests.test_virtual_full_charge import T0, _Batteries, _config, _Data


class _NoFull(_Data):
    def full_charge_now(self, bid, now):
        return None


def _sim(socs: dict[str, float], guard: bool = True, house_w: float = 800.0):
    configs = [_config("A", "none"), _config("B", "none")]
    batteries = _Batteries(configs)
    for c in configs:
        batteries.set_virtual(c.id, T0, 0.0, socs[c.id])
    forecast = SimpleNamespace(
        balance_interval=timedelta(hours=1),
        phase_margin=0,
        react_interval=timedelta(seconds=5),
        react_jump_w=0,
        react_average=False,
        peak_w=0,
        peak_include_excluded=True,
        rules=PlanRules(),
        data=_NoFull(),
        pd_settings=PdSettings(),
        nom_control="direct",
        sim_delay_s=0,
        sim_ramp_w_s=0,
        spike_ignore_w=lambda w, now: 0.0,
        pv_entries=[],
        pv_deviation_w=300,
        min_battery_power=0,
        min_soc_guard=guard,
    )
    measurements = SimpleNamespace(
        flow=PowerFlow(
            grid_w=house_w,
            pv_w=0,
            excluded_w=0,
            battery_w=0,
            house_w=house_w,
            phase_w=(house_w,),
        ),
        max_current=63,
        spike=SimpleNamespace(ignore_w=0.0),
        has_pv=True,
        pv_known=True,
    )
    hass = SimpleNamespace(
        config=SimpleNamespace(language="en"),
        states=SimpleNamespace(get=lambda e: None),
    )
    logged: list[str] = []
    sim = VirtualBatterySimulator(
        hass,
        batteries,
        measurements,
        forecast,
        SimpleNamespace(async_log=lambda _c, key, **k: logged.append(key)),
    )
    sim._quiet_until = sim._last = T0
    return sim, batteries, logged


def _powers(sim, batteries, seconds: int = 5) -> dict[str, float]:
    sim.step(T0 + timedelta(seconds=seconds))
    return {i: s.power_w for i, s in batteries.states.items()}


def test_charged_back_and_others_do_not_discharge() -> None:
    """A at 8.5 % (min 10): charged back; B does not discharge meanwhile
    (never one battery charging while another discharges)."""
    sim, batteries, logged = _sim({"A": 8.5, "B": 50.0})
    powers = _powers(sim, batteries)
    assert powers["A"] == GUARD_W
    assert powers["B"] >= 0.0
    assert sim.guarding == {"A"} and logged.count("min_soc_guard_started") == 1


def test_within_one_percent_nothing() -> None:
    """9.5 % is less than 1 % under the minimum: nothing happens."""
    sim, batteries, logged = _sim({"A": 9.5, "B": 50.0})
    powers = _powers(sim, batteries)
    assert powers["A"] <= 0.0 and not sim.guarding and not logged


def test_until_one_percent_above() -> None:
    """Charging goes on until min + 1 %, then the battery is free again."""
    sim, batteries, logged = _sim({"A": 8.5, "B": 50.0})
    _powers(sim, batteries)
    batteries.set_virtual("A", T0, GUARD_W, 10.5)
    sim.step(T0 + timedelta(seconds=10))
    assert "A" in sim.guarding
    batteries.set_virtual("A", T0, GUARD_W, 11.0)
    sim.step(T0 + timedelta(seconds=15))
    assert not sim.guarding and "min_soc_guard_ended" in logged


def test_switched_off() -> None:
    sim, batteries, logged = _sim({"A": 5.0, "B": 50.0}, guard=False)
    powers = _powers(sim, batteries)
    assert powers["A"] <= 0.0 and not sim.guarding and not logged


def test_raised_minimum_not_charged_from_the_grid() -> None:
    """Far below a minimum it was never at (a raised setting): no guard;
    once seen at its minimum, sinking far below it is guarded."""
    sim, batteries, logged = _sim({"A": 5.0, "B": 50.0})
    _powers(sim, batteries)
    assert not sim.guarding and not logged
    batteries.set_virtual("A", T0, 0.0, 10.0)
    sim.step(T0 + timedelta(seconds=10))
    batteries.set_virtual("A", T0, 0.0, 5.0)
    sim.step(T0 + timedelta(seconds=15))
    assert sim.guarding == {"A"}
