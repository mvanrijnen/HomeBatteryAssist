"""Review round 13: one test per defect found (each fails without its fix)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.forecast.consumption_forecast import (
    ForecastSlot,
)
from custom_components.homebatteryassist.engine.planning.battery_plan import (
    PlanRules,
    night_starts,
    plan_batteries,
)
from custom_components.homebatteryassist.engine.sources.prices.price_points import (
    PricePoint,
)

NOW = datetime(2026, 11, 16, 0, 0, tzinfo=dt_util.UTC)
H = timedelta(hours=1)


@pytest.fixture(autouse=True)
def _utc():
    old = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(dt_util.UTC)
    yield
    dt_util.set_default_time_zone(old)


def _battery(id_: str, soc: float, capacity: float = 5.0):
    config = SimpleNamespace(
        id=id_,
        name=id_.upper(),
        capacity_kwh=capacity,
        min_soc=10.0,
        max_soc=100.0,
        max_charge_w=2000.0,
        max_discharge_w=2000.0,
        efficiency=1.0,
        full_charge_interval_days=28,
    )
    return SimpleNamespace(soc=soc, config=config)


def _slots(house: list[float]) -> list[ForecastSlot]:
    return [
        ForecastSlot(NOW + i * H, NOW + (i + 1) * H, w, w, "hour")
        for i, w in enumerate(house)
    ]


def _prices(values: list[float]) -> list[PricePoint]:
    return [PricePoint(NOW + i * H, NOW + (i + 1) * H, p) for i, p in enumerate(values)]


def test_nom_keeps_the_surplus_after_a_full_charge_is_done() -> None:
    """A full charge block whose battery is full: zero on the meter still
    stores the whole sun surplus in the other battery (finalise took the
    full charge off a request that never had it)."""
    a, b = _battery("a", 99.0), _battery("b", 20.0, capacity=10.0)
    block = {NOW + k * H: 1500.0 for k in range(3)}
    plan = plan_batteries(
        [a, b],
        _slots([500.0] * 4),
        {NOW + k * H: 2500.0 for k in range(4)},  # 2000 W surplus
        _prices([0.30] * 4),
        mode="nom",
        forced=block,
        forced_by={k: {"a": w} for k, w in block.items()},
    )
    assert plan.slots[1].power_w >= 1999.0, [s.power_w for s in plan.slots]
    assert plan.slots[2].power_w >= 1999.0


def test_night_reserve_does_not_hide_room_of_another_battery() -> None:
    """A battery below its minimum does not hide another's room at night
    (as it does not by day): the night floor counts its shortfall too."""
    from custom_components.homebatteryassist.engine.planning.battery_plan import (
        _pack,
    )

    a, b = _battery("a", 80.0), _battery("b", 4.0)  # b below its 10 % minimum
    rules = PlanRules(night_reserve_soc=5.0)  # below the minimum: no effect
    pack = _pack([a, b], rules)
    assert pack.night_floor == pytest.approx(pack.floor)
    assert pack.stored - pack.night_floor == pytest.approx(4000 - 500)


def test_a_day_beyond_the_pv_forecast_is_no_night() -> None:
    """A day the PV forecast does not reach is left out, not one long night."""
    slots = [
        ForecastSlot(NOW + i * H, NOW + (i + 1) * H, 300.0, 300.0, "hour")
        for i in range(48)
    ]
    sun = {NOW + i * H: 2000.0 for i in range(8, 16)}  # only day 1
    night = night_starts(slots, sun)
    assert NOW + 3 * H in night and NOW + 20 * H in night
    assert not any(NOW + i * H in night for i in range(24, 48))


# --- virtual battery simulator ------------------------------------------------

from custom_components.homebatteryassist.engine.control.interceptors.base import (  # noqa: E402
    REJECT,
    Decision,
    Interceptor,
    InterceptResult,
)
from custom_components.homebatteryassist.engine.control.pd_controller import (  # noqa: E402
    PdSettings,
)
from custom_components.homebatteryassist.engine.devices.batteries.virtual import (  # noqa: E402
    VirtualBatterySimulator,
)
from custom_components.homebatteryassist.engine.measure.battery_monitor import (  # noqa: E402
    BatteryConfig,
    BatteryState,
)
from custom_components.homebatteryassist.engine.measure.house_measurement import (  # noqa: E402
    PowerFlow,
)

T1 = datetime(2026, 11, 16, 12, 0, tzinfo=dt_util.UTC)


def _vconfig(bid: str, phase: str) -> BatteryConfig:
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
        self.calls: list[tuple] = []

    def set_virtual(self, bid, when, power, soc, since=None) -> None:
        config = next(c for c in self.configs if c.id == bid)
        self.states[bid] = BatteryState(config, soc, power)
        self.calls.append((bid, when, power, since))

    def plan_states(self):
        return list(self.states.values())

    def price_now(self):
        return None


class _NoPlan:
    plan_mode = "nom"
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


class _Reject(Interceptor):
    key = "reject_a"

    def intercept(self, data):
        return InterceptResult(
            decisions=[Decision("A", REJECT, reason="test")], redistribute=False
        )


def _sim(phase_w, phases, interceptor=None, max_current=25):
    configs = [_vconfig(b, p) for b, p in phases.items()]
    batteries = _Batteries(configs)
    forecast = SimpleNamespace(
        balance_interval=timedelta(hours=1),
        phase_margin=0,
        react_interval=timedelta(seconds=5),
        react_jump_w=0,
        react_average=False,
        peak_w=0,
        peak_include_excluded=True,
        rules=PlanRules(),
        data=_NoPlan(),
        pd_settings=PdSettings(),
        nom_control="direct",
        sim_delay_s=0,
        sim_ramp_w_s=0,
        spike_ignore_w=lambda w, now: 0.0,
        pv_entries=[],
        pv_deviation_w=300,
        min_battery_power=0,
        interceptor=interceptor,
    )
    grid = sum(phase_w)
    measurements = SimpleNamespace(
        flow=PowerFlow(
            grid_w=grid,
            pv_w=0,
            excluded_w=0,
            battery_w=0,
            house_w=max(grid, 0),
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
    sim._quiet_until = sim._last = T1
    return sim, batteries


def test_two_phases_overloaded_the_opposite_way_both_relieved() -> None:
    """L1 imports, L2 exports too much: both relieved (main fuse first), the
    direction block for a battery still ramping does not stop one."""
    sim, batteries = _sim([7000.0, -7000.0, 0.0], {"A": "l1", "B": "l2"})
    sim.step(T1 + timedelta(seconds=5))
    assert batteries.states["A"].power_w == pytest.approx(-1250.0, abs=1)
    assert batteries.states["B"].power_w == pytest.approx(1250.0, abs=1)


def test_interceptor_cannot_undo_relief_already_given() -> None:
    """A battery already discharging enough on an overloaded phase protects
    it: an interceptor rejecting it does not stop it."""
    sim, batteries = _sim([6200.0], {"A": "l1"}, interceptor=_Reject())
    sim.step(T1 + timedelta(seconds=5))
    assert batteries.states["A"].power_w <= -450.0


def test_counters_count_the_power_of_the_round_it_was_used() -> None:
    """The power of a round goes with the stretch it moved the state of
    charge for (from the previous round), not the next one."""
    sim, batteries = _sim([1000.0], {"A": "l1"})
    sim.step(T1 + timedelta(seconds=5))
    _bid, when, power, since = batteries.calls[-1]
    assert since == T1 and when == T1 + timedelta(seconds=5) and power < 0


# --- measurement, history import, storage, sensors ---------------------------


def test_import_battery_gap_is_unknown_not_zero() -> None:
    """A battery's statistics with a gap: that period is skipped (unknown,
    as live), not imported as 0 W battery; before its first statistic the
    battery did not exist (0 W)."""
    from custom_components.homebatteryassist.engine.history.history_import import (
        Term,
        combine,
    )

    terms = [
        Term("grid", 1.0, required=True),
        Term("bat", 1.0, required_within=True),
        Term("ev", -1.0, absolute=True, required_within=True),
    ]
    starts = [NOW + i * H for i in range(4)]
    series = {
        "grid": dict.fromkeys(starts, 500.0),
        "bat": {starts[1]: 2000.0, starts[3]: 2000.0},  # gap at starts[2]
        "ev": {starts[1]: 0.0, starts[2]: 0.0, starts[3]: 0.0},
    }
    result = combine(terms, series, starts)
    assert result[starts[0]] == 500.0  # before the battery existed
    assert result[starts[1]] == 2500.0
    assert starts[2] not in result  # battery unknown: not 0 W
    assert result[starts[3]] == 2500.0


async def test_signed_current_sensor_keeps_the_current(hass) -> None:
    """A current sensor signed with the power (negative while exporting)
    still gives the current (its size), as a direct meter does."""
    from custom_components.homebatteryassist.engine.measure.house_measurement import (
        MeasurementInput,
    )

    for i, value in enumerate(("-12.5", "3", "-0.4")):
        hass.states.async_set(f"sensor.i{i}", value, {"unit_of_measurement": "A"})
    fake = SimpleNamespace(hass=hass)
    sensors = [f"sensor.i{i}" for i in range(3)]
    assert MeasurementInput._per_phase(fake, sensors, 3, signed=True) == (
        12.5,
        3.0,
        0.4,
    )
    assert MeasurementInput._per_phase(fake, sensors, 3) is None  # voltage: invalid


async def test_unloaded_store_writes_nothing(hass) -> None:
    """After the databases close (unload), a store of that instance no
    longer writes (a late cycle would leave rows the reloaded one lacks)."""
    from unittest.mock import AsyncMock

    from custom_components.homebatteryassist.engine import db_store

    json_store = SimpleNamespace(
        key="test_store", async_save=AsyncMock(), async_delay_save=lambda *a: None
    )
    store = db_store.HbaStore(hass, json_store, layout=None)  # type: ignore[arg-type]
    await store.async_save({"a": 1})
    assert json_store.async_save.await_count == 1
    await db_store.async_close_databases(hass)
    await store.async_save({"a": 2})
    assert json_store.async_save.await_count == 1
    assert db_store.HbaStore(hass, json_store, layout=None).closed is False  # type: ignore[arg-type]


def test_price_accuracy_keeps_its_unit() -> None:
    """The price accuracy sensor keeps the last known unit while the price
    source gives nothing for a cycle."""
    from custom_components.homebatteryassist.output.sensors import (
        ForecastAccuracySensor,
    )

    sensor = ForecastAccuracySensor.__new__(ForecastAccuracySensor)
    sensor._kind = "price"
    sensor.coordinator = SimpleNamespace(data=SimpleNamespace(price_unit="EUR/kWh"))
    assert sensor.native_unit_of_measurement == "EUR/kWh"
    sensor.coordinator.data.price_unit = None
    assert sensor.native_unit_of_measurement == "EUR/kWh"
