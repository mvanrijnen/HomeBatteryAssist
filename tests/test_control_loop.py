"""The control loop on a real battery (a fake Marstek Venus over Modbus TCP):
zero on the meter from the measured grid without the battery, commands over
the direct connection, held back during a test, released on stop."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.control.control_loop import (
    ControlLoop,
)
from custom_components.homebatteryassist.engine.control.pd_controller import PdSettings
from custom_components.homebatteryassist.engine.measure.battery_monitor import (
    BatteryState,
)
from custom_components.homebatteryassist.engine.measure.house_measurement import (
    PowerFlow,
)
from custom_components.homebatteryassist.engine.planning.battery_plan import PlanRules

from .test_direct_link import CONFIG, FakeLog, FakeVenus, _link
from .test_direct_link import venus as venus_fixture

venus = venus_fixture  # the fixture, by its name for the tests below

CONTROLLED = replace(CONFIG, control=True)
T0 = datetime(2026, 11, 24, 18, 0, tzinfo=dt_util.UTC)


class _Data:
    plan_mode = "nom"  # the active planner module: zero on the meter
    selected_plan = None

    def __init__(self) -> None:
        self.forced_by: dict = {}

    def full_charge_now(self, bid, now):
        return None

    def night_at(self, now):
        return False

    def consumption_at(self, now):
        return None

    def pv_at(self, now):
        return None


def _forecast():
    return SimpleNamespace(
        balance_interval=timedelta(hours=1),
        phase_margin=0,
        react_interval=timedelta(seconds=5),
        react_jump_w=0,
        react_average=False,
        peak_w=0,
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
        interceptor=None,
    )


def _flow(house_w: float, battery_w: float) -> PowerFlow:
    grid = house_w + battery_w  # the battery's charging is grid load
    return PowerFlow(
        grid_w=grid,
        pv_w=0,
        excluded_w=0,
        battery_w=battery_w,
        house_w=house_w,
        phase_w=(0.0, 0.0, grid),
    )


async def test_zero_on_the_meter(
    hass: HomeAssistant,
    venus: FakeVenus,
) -> None:
    link = _link(hass)
    await link.async_start()
    batteries = SimpleNamespace(
        configs=[CONTROLLED],
        states={"b1": BatteryState(CONTROLLED, 60.0, 0.0)},
        plan_states=lambda: [],
        price_now=lambda: None,
    )
    measurements = SimpleNamespace(
        flow=_flow(600.0, 0.0),
        max_current=25,
        spike=SimpleNamespace(ignore_w=0.0),
        has_pv=False,
        pv_known=True,
        async_add_listener=lambda listener: lambda: None,
    )
    log = FakeLog()
    tests = SimpleNamespace(runs={})
    loop = ControlLoop(hass, batteries, measurements, _forecast(), log, tests=tests)
    assert [c.id for c in loop.virtual] == ["b1"]
    loop._quiet_until = loop._last = T0
    try:
        # The house asks 600 W: discharge 600 W.
        loop.step(T0 + timedelta(seconds=5))
        await hass.async_block_till_done()
        assert venus.registers[42010] == 2 and venus.registers[42021] == 600
        # The battery does it: the grid is 0, the house still asks 600 W.
        batteries.states["b1"] = BatteryState(CONTROLLED, 60.0, -600.0)
        measurements.flow = _flow(600.0, -600.0)
        loop.step(T0 + timedelta(seconds=10))
        await hass.async_block_till_done()
        assert loop.sent["b1"] == -600
        # A test takes the battery: the loop leaves it alone.
        tests.runs["b1"] = object()
        loop.step(T0 + timedelta(seconds=15))
        await hass.async_block_till_done()
        assert loop.sent["b1"] is None and loop.holding["b1"] == "test"
        del tests.runs["b1"]
        loop.step(T0 + timedelta(seconds=20))
        await hass.async_block_till_done()
        assert "b1" not in loop.holding
        keys = [k for k, _ in log.keys]
        assert "control_held" in keys and "control_resumed" in keys
    finally:
        await loop.async_stop_all()
        await link.async_stop()
    # Stopped: back to the battery's own control.
    assert venus.registers[42000] == 0x55BB and venus.registers[42010] == 0
    assert ("control_stopped", {}) in log.keys


async def test_not_controlled_unless_marked(
    hass: HomeAssistant,
    venus: FakeVenus,
) -> None:
    link = _link(hass)
    await link.async_start()
    batteries = SimpleNamespace(
        configs=[CONFIG],
        states={"b1": BatteryState(CONFIG, 60.0, 0.0)},
    )
    try:
        loop = ControlLoop(hass, batteries, SimpleNamespace(), _forecast(), FakeLog())
        assert loop.controllers == {}
        loop.async_start()  # nothing to control: nothing starts
        assert venus.writes == []
    finally:
        await link.async_stop()
