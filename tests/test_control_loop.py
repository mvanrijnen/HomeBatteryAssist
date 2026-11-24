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
        # The house asks 600 W: discharge, half of it in the first round.
        loop.step(T0 + timedelta(seconds=5))
        await hass.async_block_till_done()
        assert venus.registers[42010] == 2 and venus.registers[42021] == 300
        # The battery does it: the meter still shows 300 W: half of that more.
        batteries.states["b1"] = BatteryState(CONTROLLED, 60.0, -300.0)
        measurements.flow = _flow(600.0, -300.0)
        loop.step(T0 + timedelta(seconds=10))
        await hass.async_block_till_done()
        assert loop.sent["b1"] == -450
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


class _Controller:
    """Records the powers sent; a battery that takes them a round later."""

    def __init__(self) -> None:
        self.sent: list[float | None] = []
        self.errors = 0
        self.state = SimpleNamespace(active=False)

    async def async_command(self, power, now=None) -> None:
        self.sent.append(power)

    async def async_release(self, reason="") -> None:
        self.sent.append(None)

    async def async_stop(self) -> None:
        pass


async def test_stable_with_a_lagging_battery(hass: HomeAssistant) -> None:
    """The battery does a command a round later and reports its power a round
    after that (as a Marstek Venus): zero on the meter settles at what the
    house asks, without turning the direction every round."""
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
    loop = ControlLoop(hass, batteries, measurements, _forecast(), FakeLog())
    controller = _Controller()
    loop.controllers = {"b1": controller}
    loop._quiet_until = loop._last = T0
    doing = [0.0, 0.0]  # what the battery does now, and a round before
    for i in range(1, 41):
        # The meter sees what the battery does now; its own reading lags.
        measurements.flow = _flow(600.0, doing[0])
        batteries.states["b1"] = BatteryState(CONTROLLED, 60.0, doing[1])
        loop.step(T0 + i * timedelta(seconds=5))
        await hass.async_block_till_done()
        command = controller.sent[-1] or 0.0
        doing = [command, doing[0]]  # it reacts a round later
    tail = [p for p in controller.sent[-10:] if p is not None]
    assert tail and all(-700 < p < -500 for p in tail), controller.sent
    assert not any(p > 50 for p in controller.sent[5:])  # never charging


async def test_oscillation_pauses_control(hass: HomeAssistant) -> None:
    """Turning charge <-> discharge too often releases the batteries."""
    batteries = SimpleNamespace(
        configs=[CONTROLLED],
        states={"b1": BatteryState(CONTROLLED, 60.0, 0.0)},
    )
    log = FakeLog()
    loop = ControlLoop(hass, batteries, SimpleNamespace(), _forecast(), log)
    loop.controllers = {"b1": _Controller()}
    for i, total in enumerate([600, -600, 600, -600, 600]):
        loop._watch_direction(T0 + timedelta(seconds=5 * i), total)
    assert loop._hold_reason("b1", T0 + timedelta(seconds=30)) == "oscillating"
    assert loop._hold_reason("b1", T0 + timedelta(minutes=11)) is None


def _plan_data(power_w: float, price: float, use_above: float | None):
    """Arbitrage selected; one slot around T0 that discharges for the house."""
    data = _Data()
    data.plan_mode = "arbitrage"
    slot = SimpleNamespace(
        start=T0 - timedelta(hours=1),
        end=T0 + timedelta(hours=2),
        power_w=power_w,
        grid_w=0.0,
        price=price,
        use_above=use_above,
        export_price=None,
    )
    data.selected_plan = SimpleNamespace(strategy="arbitrage", slots=[slot])
    return data


async def _run_plan(hass, data, house_w: float) -> list[float | None]:
    batteries = SimpleNamespace(
        configs=[CONTROLLED],
        states={"b1": BatteryState(CONTROLLED, 60.0, 0.0)},
        plan_states=lambda: [BatteryState(CONTROLLED, 60.0, 0.0)],
        price_now=lambda: None,
    )
    measurements = SimpleNamespace(
        flow=_flow(house_w, 0.0),
        max_current=25,
        spike=SimpleNamespace(ignore_w=0.0),
        has_pv=False,
        pv_known=True,
        async_add_listener=lambda listener: lambda: None,
    )
    forecast = _forecast()
    forecast.data = data
    loop = ControlLoop(hass, batteries, measurements, forecast, FakeLog())
    controller = _Controller()
    loop.controllers = {"b1": controller}
    loop._quiet_until = loop._last = T0
    doing = [0.0, 0.0]
    for i in range(1, 41):
        measurements.flow = _flow(house_w, doing[0])
        batteries.states["b1"] = BatteryState(CONTROLLED, 60.0, doing[1])
        loop.step(T0 + i * timedelta(seconds=5))
        await hass.async_block_till_done()
        command = controller.sent[-1] or 0.0
        doing = [command, doing[0]]
    return controller.sent


async def test_plan_discharge_stable_with_a_lagging_battery(
    hass: HomeAssistant,
) -> None:
    """A planned discharge of 640 W while the house uses 400 W: limited to
    the need on the meter, without flipping between 0 W and the plan."""
    sent = await _run_plan(hass, _plan_data(-640.0, 0.30, 0.35), 400.0)
    tail = [p for p in sent[-10:] if p is not None]
    assert tail and all(-450 < p < -350 for p in tail), sent
    assert not any(p is not None and p > -1 for p in sent[10:]), sent


async def test_plan_discharge_at_most_planned_when_not_worth_it(
    hass: HomeAssistant,
) -> None:
    """The house uses 1500 W, the price is below the plan's use-above
    threshold: no more than the planned 640 W."""
    sent = await _run_plan(hass, _plan_data(-640.0, 0.30, 0.35), 1500.0)
    tail = [p for p in sent[-10:] if p is not None]
    assert tail and all(-645 < p < -600 for p in tail), sent


async def test_plan_discharge_covers_the_house_when_it_pays(
    hass: HomeAssistant,
) -> None:
    """The house uses 1500 W and the price is above the plan's use-above
    threshold: the whole need is covered, above the planned 640 W."""
    sent = await _run_plan(hass, _plan_data(-640.0, 0.40, 0.35), 1500.0)
    tail = [p for p in sent[-10:] if p is not None]
    assert tail and all(-1600 < p < -1400 for p in tail), sent
