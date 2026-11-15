"""Tests for the phase limits of the grid connection (main fuse)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.forecasts.consumption import ForecastSlot
from custom_components.homebatteryassist.forecasts.phases import PhaseProfile
from custom_components.homebatteryassist.history.consumption import (
    ConsumptionHistory,
)
from custom_components.homebatteryassist.inputs.prices import PricePoint
from custom_components.homebatteryassist.planning.battery_plan import (
    MODE_ARBITRAGE,
    plan_batteries,
)
from custom_components.homebatteryassist.planning.phase_limit import (
    PhaseDevice,
    cap_powers,
    max_power,
    phase_limit_w,
)
from custom_components.homebatteryassist.simulation.virtual_battery import (
    VirtualBatterySimulator,
)

T0 = datetime(2026, 11, 16, 0, 0, tzinfo=dt_util.UTC)
H = timedelta(hours=1)
LIMIT = phase_limit_w(25)  # 25 A x 230 V x 0.9 = 5175 W


def test_limit_includes_margin() -> None:
    assert LIMIT == 5175.0


def test_max_power_per_phase() -> None:
    """Batteries on a busy phase get only the room that is left on it."""
    devices = [PhaseDevice("a", 0, 2500, 2500), PhaseDevice("b", 0, 2500, 2500)]
    loads = [4000.0, 0.0, 0.0]
    assert max_power(devices, loads, LIMIT, charging=True) == 1175.0
    assert max_power(devices, loads, LIMIT, charging=False) == 5000.0
    # Spread over the phases: three times the room of the busiest phase.
    spread = [PhaseDevice("c", None, 3000, 3000)]
    assert max_power(spread, [5000.0, 0.0, 0.0], LIMIT, charging=True) == 525.0
    # PV export on the phase gives extra room for charging.
    assert max_power(devices, [-3000.0, 0, 0], LIMIT, charging=True) == 5000.0


def test_cap_powers_scales_down_and_reports_phase() -> None:
    devices = [
        PhaseDevice("a", 0, 2500, 2500),
        PhaseDevice("b", 0, 2500, 2500),
        PhaseDevice("c", 1, 2500, 2500),
    ]
    powers, limited = cap_powers(
        {"a": 2500.0, "b": 2500.0, "c": 2500.0}, devices, [4000.0, 0.0, 0.0], LIMIT
    )
    assert powers == {"a": 587.5, "b": 587.5, "c": 2500.0}
    assert limited == [0]
    # Discharging into a phase that already exports a lot.
    powers, limited = cap_powers({"c": -2500.0}, devices, [0.0, -4000.0, 0.0], LIMIT)
    assert powers == {"c": -1175.0}
    assert limited == [1]
    powers, limited = cap_powers({"a": 1000.0}, devices, [0.0, 0.0, 0.0], LIMIT)
    assert powers == {"a": 1000.0}
    assert limited == []


def _battery(phase: str = "l1"):
    config = SimpleNamespace(
        id="a",
        capacity_kwh=10.0,
        min_soc=10.0,
        max_soc=100.0,
        max_charge_w=5000.0,
        max_discharge_w=5000.0,
        efficiency=0.81,
        phase=phase,
    )
    return SimpleNamespace(soc=20.0, config=config)


def test_plan_respects_phase_limits() -> None:
    """Charging from the grid stays within the room per slot and is marked."""
    slots = [
        ForecastSlot(T0 + i * H, T0 + (i + 1) * H, 500.0, 500.0, "hour")
        for i in range(3)
    ]
    prices = [
        PricePoint(T0 + i * H, T0 + (i + 1) * H, p)
        for i, p in enumerate([0.10, 0.10, 0.60])
    ]
    limits = {T0: (1500.0, 5000.0), T0 + H: (1500.0, 5000.0)}
    plan = plan_batteries(
        [_battery()], slots, {}, prices, mode=MODE_ARBITRAGE, limits=limits
    )
    assert all(s.power_w <= 1500.0 for s in plan.slots)
    assert plan.slots[0].power_w > 1000 and plan.slots[0].limited
    unlimited = plan_batteries([_battery()], slots, {}, prices, mode=MODE_ARBITRAGE)
    assert unlimited.slots[0].power_w > 1500.0
    assert not any(s.limited for s in unlimited.slots)


def test_phase_profile_learns_shares() -> None:
    """The house consumption is spread like the history; even without history."""
    records = [
        {
            "start": (T0 + i * H).isoformat(),
            "minutes": 60,
            "coverage": 1.0,
            "avg_w": 1000.0,
            "phase_house_w": [600.0, 300.0, 100.0],
            "phase_pv_w": [0.0, 0.0, 900.0],
        }
        for i in range(3)
    ]
    profile = PhaseProfile(records, 3)
    slots = [ForecastSlot(T0, T0 + H, 2000.0, 2000.0, "hour")]
    assert profile.loads(slots, {T0: 1000.0}) == {T0: [1200.0, 600.0, -800.0]}
    even = PhaseProfile([], 3)
    assert even.loads(slots, {}) == {T0: [666.7, 666.7, 666.7]}


async def test_history_records_phases(hass: HomeAssistant) -> None:
    history = ConsumptionHistory(hass, "test", 15)
    history.add_sample(T0, 900.0, phases=((300.0, 300.0, 300.0), (0.0, 0.0, 0.0)))
    history.add_sample(
        T0 + timedelta(minutes=5),
        900.0,
        phases=((600.0, 300.0, 0.0), (100.0, 0.0, 0.0)),
    )
    record = history.close_interval(T0 + timedelta(minutes=15))
    assert record["phase_house_w"] == [500.0, 300.0, 100.0]
    assert record["phase_pv_w"] == [66.7, 0.0, 0.0]


def test_simulator_holds_virtual_batteries_within_limit(hass: HomeAssistant) -> None:
    """A virtual battery may not overload its phase; it is explained once."""
    logged: list[tuple] = []
    config = SimpleNamespace(
        id="v1",
        name="Virtueel 1",
        virtual=True,
        phase="l2",
        max_charge_w=2500.0,
        max_discharge_w=2500.0,
    )
    flow = SimpleNamespace(
        phase_w=(0.0, 4500.0, 0.0), phase_current=lambda i: [0, 4500 / 230, 0][i]
    )
    sim = VirtualBatterySimulator(
        hass,
        SimpleNamespace(configs=[config]),
        SimpleNamespace(flow=flow, max_current=25),
        SimpleNamespace(balance_interval=timedelta(hours=1), phase_margin=10),
        SimpleNamespace(async_log=lambda *a, **kw: logged.append((a, kw))),
    )
    assert sim._phase_limited({"v1": 2500.0}, T0) == {"v1": 675.0}
    assert sim._phase_limited({"v1": 2500.0}, T0 + timedelta(seconds=30)) == {
        "v1": 675.0
    }
    assert [a[1] for a, _ in logged] == ["phase_limit"]
    assert logged[0][1]["phase"] == "L2"
    flow.phase_w = (0.0, 1000.0, 0.0)
    assert sim._phase_limited({"v1": 2500.0}, T0 + timedelta(minutes=1)) == {
        "v1": 2500.0
    }
    sim._phase_limited({"v1": 2500.0}, T0 + timedelta(minutes=7))
    assert [a[1] for a, _ in logged] == ["phase_limit", "phase_limit_cleared"]


def test_margin_is_configurable() -> None:
    assert phase_limit_w(25, 0) == 5750.0
    assert phase_limit_w(25, 20) == 4600.0


def test_relieve_overloaded_phase() -> None:
    """Batteries on an overloaded phase discharge to bring it back to the limit."""
    from custom_components.homebatteryassist.planning.phase_limit import (
        overloaded,
        relieve,
    )

    devices = [
        PhaseDevice("a", 0, 2500, 2500),
        PhaseDevice("b", 0, 2500, 2500),
        PhaseDevice("c", 1, 2500, 2500),
    ]
    loads = [LIMIT + 3000.0, 0.0, -(LIMIT + 500.0)]
    assert overloaded(loads, LIMIT) == [0, 2]
    # a was charging (plan): it stops and discharges; b helps too.
    powers, relieved = relieve(
        {"a": 2000.0, "b": 0.0, "c": 0.0}, devices, loads, LIMIT, ["a", "b"], ["a"]
    )
    assert powers == {"a": -1500.0, "b": -1500.0, "c": 0.0}
    assert relieved == {0: 3000.0}
    # An empty battery cannot help; the other one gives what it can.
    powers, relieved = relieve(
        {"a": 0.0, "b": 0.0, "c": 0.0}, devices, loads, LIMIT, ["a"], []
    )
    assert powers["a"] == -2500.0 and powers["b"] == 0.0
    assert relieved == {0: 2500.0}
    # Too much export: a battery spread over the phases charges a share.
    spread = [PhaseDevice("s", None, 3000, 3000)]
    powers, relieved = relieve(
        {"s": 0.0}, spread, [0.0, 0.0, -(LIMIT + 500.0)], LIMIT, [], ["s"]
    )
    assert powers == {"s": 1500.0}
    assert relieved == {2: 500.0}


def test_simulator_phase_protection(hass: HomeAssistant) -> None:
    """The simulation relieves an overloaded phase and explains start and end."""
    logged: list[tuple] = []
    config = SimpleNamespace(
        id="v1",
        name="Virtueel 1",
        virtual=True,
        phase="l1",
        max_charge_w=2500.0,
        max_discharge_w=2500.0,
        min_soc=10.0,
        max_soc=100.0,
    )
    flow = SimpleNamespace(
        phase_w=(LIMIT + 1000.0, 0.0, 0.0),
        phase_current=lambda i: [(LIMIT + 1000) / 230, 0, 0][i],
    )
    sim = VirtualBatterySimulator(
        hass,
        SimpleNamespace(configs=[config]),
        SimpleNamespace(flow=flow, max_current=25),
        SimpleNamespace(balance_interval=timedelta(hours=1), phase_margin=10),
        SimpleNamespace(async_log=lambda *a, **kw: logged.append((a, kw))),
    )
    socs, full = {"v1": 50.0}, {"v1": None}
    result = sim._phase_relief({"v1": 1000.0}, socs, full, T0, 0.5)
    assert result == {"v1": -1000.0}
    assert logged[-1][0][1] == "phase_relief"
    assert sim.relief[0]["wh"] == 500.0
    flow.phase_w = (1000.0, 0.0, 0.0)
    assert sim._phase_relief({"v1": 1000.0}, socs, full, T0 + H, 0.5) == {"v1": 1000.0}
    assert logged[-1][0][1] == "phase_relief_ended"
    assert logged[-1][1]["energy"] == "0,50" or logged[-1][1]["energy"] == "0.50"
