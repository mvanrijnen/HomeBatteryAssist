"""Tests for the battery plan (NOM and arbitrage)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.forecast.consumption_forecast import (
    ForecastSlot,
)
from custom_components.homebatteryassist.engine.planning.battery_plan import (
    MODE_ARBITRAGE,
    MODE_NOM,
    PlanSlot,
    plan_batteries,
    reach_times,
)
from custom_components.homebatteryassist.engine.sources.prices.price_points import (
    PricePoint,
)

T0 = datetime(2026, 11, 16, 0, 0, tzinfo=dt_util.UTC)
H = timedelta(hours=1)


def _battery(soc: float = 50.0, capacity: float = 5.0, power: float = 2500.0):
    config = SimpleNamespace(
        capacity_kwh=capacity,
        min_soc=10.0,
        max_soc=100.0,
        max_charge_w=power,
        max_discharge_w=power,
        efficiency=0.81,  # 0.9 each way
    )
    return SimpleNamespace(soc=soc, config=config)


def _slots(house: list[float]) -> list[ForecastSlot]:
    return [
        ForecastSlot(T0 + i * H, T0 + (i + 1) * H, w, w, "hour")
        for i, w in enumerate(house)
    ]


def _prices(values: list[float]) -> list[PricePoint]:
    return [PricePoint(T0 + i * H, T0 + (i + 1) * H, p) for i, p in enumerate(values)]


def test_nom_follows_surplus_and_shortage() -> None:
    """NOM: charge with PV surplus, discharge on shortage, never from the grid."""
    slots = _slots([500.0, 500.0, 500.0])
    pv = {T0: 1500.0, T0 + H: 0.0, T0 + 2 * H: 500.0}
    plan = plan_batteries(
        [_battery()], slots, pv, _prices([0.3, 0.3, 0.3]), mode=MODE_NOM
    )
    assert plan.strategy == MODE_NOM
    assert [s.power_w for s in plan.slots] == [1000.0, -500.0, 0.0]
    assert [s.grid_w for s in plan.slots] == [0.0, 0.0, 0.0]
    assert plan.saving is not None


def test_arbitrage_charges_cheap_discharges_expensive() -> None:
    """Arbitrage charges from the grid when cheap and discharges when expensive."""
    slots = _slots([500.0] * 4)
    prices = _prices([0.10, 0.10, 0.50, 0.50])
    arbitrage = plan_batteries(
        [_battery(soc=10.0)], slots, {}, prices, mode=MODE_ARBITRAGE
    )
    nom = plan_batteries([_battery(soc=10.0)], slots, {}, prices, mode=MODE_NOM)
    assert arbitrage.strategy == MODE_ARBITRAGE
    assert arbitrage.slots[0].power_w > 0 and arbitrage.slots[1].power_w > 0
    assert arbitrage.slots[2].power_w < 0 and arbitrage.slots[3].power_w < 0
    assert arbitrage.saving > nom.saving  # NOM cannot use the cheap hours
    assert arbitrage.saving > 0


def test_limits_are_respected() -> None:
    """Power and state of charge stay within the battery limits."""
    slots = _slots([3000.0] * 6)
    prices = _prices([0.5] * 6)
    plan = plan_batteries(
        [_battery(soc=100.0, power=1000.0)], slots, {}, prices, mode=MODE_ARBITRAGE
    )
    assert all(-1000.0 - 1e-6 <= s.power_w <= 1000.0 + 1e-6 for s in plan.slots)
    assert all(10.0 - 0.5 <= s.soc <= 100.0 + 0.5 for s in plan.slots)


def test_without_prices_falls_back_to_nom() -> None:
    """No prices: arbitrage is not possible."""
    slots = _slots([500.0, 500.0])
    plan = plan_batteries([_battery()], slots, {T0: 2000.0}, [], mode=MODE_ARBITRAGE)
    assert plan.mode == MODE_ARBITRAGE
    assert plan.strategy == MODE_NOM
    assert plan.saving is None
    assert plan_batteries([], slots, {}, [], mode=MODE_NOM) is None


def test_several_batteries_are_planned_as_one() -> None:
    """Capacity and power of several batteries add up."""
    slots = _slots([0.0])
    pv = {T0: 4000.0}
    plan = plan_batteries(
        [_battery(soc=10.0), _battery(soc=10.0)], slots, pv, [], mode=MODE_NOM
    )
    assert plan.slots[0].power_w == pytest.approx(4000.0)


def test_arbitrage_for_own_use_never_exports_battery_energy() -> None:
    """Arbitrage (own use) discharges at most what the house needs."""
    slots = _slots([200.0, 200.0, 200.0, 200.0])
    prices = _prices([0.05, 0.05, 0.90, 0.90])  # tempting to sell to the grid
    plan = plan_batteries([_battery(soc=10.0)], slots, {}, prices, mode=MODE_ARBITRAGE)
    assert all(s.power_w >= -200.0 - 1e-6 for s in plan.slots)
    assert all(s.grid_w >= -1e-6 for s in plan.slots)  # no export by the battery
    assert plan.slots[2].power_w < 0  # but it does cover the expensive hours


def test_compare_modes_cumulative_advantage() -> None:
    """Cumulative advantage of arbitrage over NOM per slot; ends at the difference."""
    from custom_components.homebatteryassist.engine.planning.battery_plan import (
        compare_modes,
    )

    slots = _slots([500.0] * 4)
    prices = _prices([0.10, 0.10, 0.50, 0.50])
    plans = {
        mode: plan_batteries([_battery(soc=10.0)], slots, {}, prices, mode=mode)
        for mode in (MODE_NOM, MODE_ARBITRAGE)
    }
    series = compare_modes(plans, MODE_ARBITRAGE, MODE_NOM, 1.0, 0.02)
    assert len(series) == 4
    assert series[-1][1] > 0  # arbitrage pays off in the expensive hours
    # The last value equals the difference in expected saving.
    diff = plans[MODE_ARBITRAGE].saving - plans[MODE_NOM].saving
    assert abs(series[-1][1] - diff) < 0.01


def test_export_price_per_slot() -> None:
    """A separate export price is used for PV surplus; else import x factor."""
    from custom_components.homebatteryassist.engine.sources.prices.price_points import (
        merge_price_forecasts,
    )

    slots = _slots([0.0, 0.0])
    pv = {T0: 1000.0, T0 + H: 1000.0}
    prices = _prices([0.30, 0.30])
    export = [PricePoint(T0, T0 + H, 0.10)]
    plan = plan_batteries(
        [_battery(soc=100.0)],
        slots,
        pv,
        prices,
        mode=MODE_NOM,
        export_factor=0.5,
        export_prices=export,
    )
    # Full battery: all PV is exported, 1 kWh at 0.10 and 1 kWh at 0.30 x 0.5.
    assert plan.cost_without == pytest.approx(-(0.10 + 0.15))
    assert [s.export_price for s in plan.slots] == [0.10, 0.15]
    merged = merge_price_forecasts([[PricePoint(T0, T0 + H, 0.1)], _prices([0.5, 0.6])])
    assert [(p.start, p.price) for p in merged] == [(T0, 0.1), (T0 + H, 0.6)]


def test_full_arbitrage_exports_when_it_pays() -> None:
    """Full arbitrage may discharge to the grid; own-use arbitrage never does."""
    from custom_components.homebatteryassist.engine.planning.battery_plan import (
        MODE_ARBITRAGE_FULL,
    )

    slots = _slots([200.0] * 4)
    prices = _prices([0.10, 0.10, 0.60, 0.60])
    own = plan_batteries(
        [_battery(soc=10.0)], slots, {}, prices, mode=MODE_ARBITRAGE, export_factor=1.0
    )
    full = plan_batteries(
        [_battery(soc=10.0)],
        slots,
        {},
        prices,
        mode=MODE_ARBITRAGE_FULL,
        export_factor=1.0,
    )
    assert full.strategy == MODE_ARBITRAGE_FULL
    assert min(s.grid_w for s in own.slots) >= -1  # no export
    assert min(s.grid_w for s in full.slots) < -1000  # exports when expensive
    assert full.saving > own.saving


def test_cycle_limit_per_day() -> None:
    """Arbitrage stays within the maximum number of full cycles per day."""
    from custom_components.homebatteryassist.engine.planning.battery_plan import (
        MODE_ARBITRAGE_FULL,
        cycles_per_day,
    )

    # Two cheap/expensive swings in a day: unlimited it cycles about twice.
    slots = _slots([0.0] * 8)
    prices = _prices([0.05, 0.05, 0.60, 0.60, 0.05, 0.05, 0.60, 0.60])
    free = plan_batteries(
        [_battery(soc=10.0)],
        slots,
        {},
        prices,
        mode=MODE_ARBITRAGE_FULL,
        export_factor=1.0,
    )
    limited = plan_batteries(
        [_battery(soc=10.0)],
        slots,
        {},
        prices,
        mode=MODE_ARBITRAGE_FULL,
        export_factor=1.0,
        max_cycles_per_day=1.0,
    )
    assert max(cycles_per_day(free).values()) > 1.2
    assert max(cycles_per_day(limited).values()) <= 1.01
    assert limited.saving < free.saving  # the limit costs something


def test_charges_at_negative_import_price() -> None:
    """A negative import price: charging from the grid pays, even without need."""
    slots = _slots([300.0] * 4)
    prices = _prices([0.30, -0.05, 0.30, 0.30])
    plan = plan_batteries([_battery(soc=30.0)], slots, {}, prices, mode=MODE_ARBITRAGE)
    assert plan.slots[1].power_w > 2000  # fills up at the negative price
    assert plan.slots[1].grid_w > 2000


def test_makes_room_before_negative_export_price() -> None:
    """Full battery and PV surplus at a negative export price: it discharges
    beforehand, so the surplus can be stored instead of exported at a loss."""
    from custom_components.homebatteryassist.engine.sources.prices.price_points import (
        PricePoint,
    )

    slots = _slots([500.0, 500.0, 500.0, 500.0])
    pv = {T0 + 3 * H: 3000.0}  # 2.5 kW surplus in the last hour
    prices = _prices([0.30, 0.30, 0.30, 0.02])
    export = [PricePoint(T0 + 3 * H, T0 + 4 * H, -0.10)]
    plan = plan_batteries(
        [_battery(soc=100.0)],
        slots,
        pv,
        prices,
        mode=MODE_ARBITRAGE,
        export_prices=export,
    )
    assert sum(s.power_w for s in plan.slots[:3]) < -1000  # makes room first
    assert plan.slots[3].power_w > 1500  # stores the surplus
    assert plan.slots[3].grid_w > -1000  # little export at the negative price


def test_plan_rules() -> None:
    """Reserve, discharge price, grid charge price and the NOM target."""
    from custom_components.homebatteryassist.engine.planning.battery_plan import (
        PlanRules,
    )

    slots = _slots([1000.0] * 4)
    prices = _prices([0.10, 0.10, 0.40, 0.20])
    # Reserve: never below 60 % in the plan (battery at 70 %).
    nom = plan_batteries(
        [_battery(soc=70.0)],
        slots,
        {},
        prices,
        mode=MODE_NOM,
        rules=PlanRules(reserve_soc=60.0),
    )
    assert min(s.soc for s in nom.slots) >= 59.9
    # Discharge only from 0.30: only in the expensive slot.
    nom = plan_batteries(
        [_battery(soc=90.0)],
        slots,
        {},
        prices,
        mode=MODE_NOM,
        rules=PlanRules(min_discharge_price=0.30),
    )
    assert [s.power_w < 0 for s in nom.slots] == [False, False, True, False]
    # Arbitrage may not charge from the grid above 0.05: it cannot buy cheap.
    arb = plan_batteries(
        [_battery(soc=10.0)],
        slots,
        {},
        prices,
        mode=MODE_ARBITRAGE,
        rules=PlanRules(max_charge_price=0.05),
    )
    assert all(s.power_w <= 0 for s in arb.slots)
    # NOM aims at +200 W import: it discharges 800 W of the 1000 W shortage.
    nom = plan_batteries(
        [_battery(soc=90.0)],
        slots,
        {},
        prices,
        mode=MODE_NOM,
        rules=PlanRules(nom_target_w=200.0),
    )
    assert nom.slots[0].power_w == -800.0


def test_charge_hysteresis() -> None:
    """Full battery: no top-up charging until it dropped below the hysteresis."""
    from custom_components.homebatteryassist.engine.planning.battery_plan import (
        PlanRules,
    )

    slots = _slots([300.0, -200.0, 300.0, -200.0])
    plan = plan_batteries(
        [_battery(soc=100.0)],
        slots,
        {},
        _prices([0.3] * 4),
        mode=MODE_NOM,
        rules=PlanRules(charge_hysteresis=10.0),
    )
    # 100 -> 93 %: no top-up yet; after 87 % (below 90 %) it charges again
    assert plan.slots[1].power_w == 0.0
    assert plan.slots[3].power_w > 0.0


def test_temperature_derating_in_pack() -> None:
    """A warm battery plans with less charge power."""
    from types import SimpleNamespace

    from custom_components.homebatteryassist.engine.planning.battery_plan import _pack

    battery = _battery()
    warm = SimpleNamespace(
        soc=battery.soc, config=battery.config, charge_factor=0.5, discharge_factor=1.0
    )
    assert _pack([warm]).max_charge == 1250.0
    assert _pack([warm]).max_discharge == 2500.0


def test_hysteresis_in_arbitrage() -> None:
    """Arbitrage does not top up a nearly full battery inside the band."""
    from custom_components.homebatteryassist.engine.planning.battery_plan import (
        PlanRules,
    )

    slots = _slots([0.0] * 3)
    prices = _prices([0.10, 0.10, 0.60])
    free = plan_batteries([_battery(soc=96.0)], slots, {}, prices, mode=MODE_ARBITRAGE)
    held = plan_batteries(
        [_battery(soc=96.0)],
        slots,
        {},
        prices,
        mode=MODE_ARBITRAGE,
        rules=PlanRules(charge_hysteresis=10.0),
    )
    assert max(s.soc for s in free.slots) > 99  # tops up to full
    assert held.slots[0].power_w == 0.0 and held.slots[1].power_w == 0.0


def test_reach_times() -> None:
    """Empty / full moments are interpolated within the slot they occur in."""

    def slot(hour: int, soc: float) -> PlanSlot:
        return PlanSlot(T0 + hour * H, T0 + (hour + 1) * H, 0.0, soc, 0.0, None)

    # 30% -> 20% -> 5%: the floor (10%) is reached 2/3 into the second hour.
    empty, full = reach_times([slot(0, 20.0), slot(1, 5.0)], 30.0, 10.0, 100.0)
    assert empty == T0 + H + H * (10 / 15)
    assert full is None
    # Charging up to the ceiling, then down to the floor.
    empty, full = reach_times(
        [slot(0, 60.0), slot(1, 100.0), slot(2, 50.0), slot(3, 10.0)],
        20.0,
        10.0,
        100.0,
    )
    assert full == T0 + 2 * H  # 60 -> 100 within the second hour: at its end
    assert empty == T0 + 4 * H
    # Already empty: no moment.
    assert reach_times([slot(0, 10.0)], 10.0, 10.0, 100.0) == (None, None)
    # Halfway the first hour at 30%, 20% at its end: the floor (10%) is
    # reached halfway the second hour (from now, not from the slot start).
    empty, _ = reach_times(
        [slot(0, 20.0), slot(1, 0.0)], 30.0, 10.0, 100.0, now=T0 + H / 2
    )
    assert empty == T0 + H + H / 2
    # From now 30% -> 25% at the end of the first hour (half an hour later).
    empty, _ = reach_times([slot(0, 25.0)], 30.0, 27.5, 100.0, now=T0 + H / 2)
    assert empty == T0 + H / 2 + H / 4


def test_arbitrage_covers_the_house_load_exactly() -> None:
    """A big battery covers a load between two levels exactly, not one whole
    level less (e.g. 331 W of 640 W)."""
    slots = _slots([640.0] * 8)
    plan = plan_batteries(
        [_battery(90.0, capacity=10.0, power=5000.0)],
        slots,
        {},
        _prices([0.45] * 4 + [0.20] * 4),
        mode=MODE_ARBITRAGE,
    )
    dear = plan.slots[:4]
    assert [s.power_w for s in dear] == pytest.approx([-640.0] * 4, abs=1)
    assert all(abs(s.grid_w) < 1 for s in dear)


def test_slot_price_is_the_average_of_its_quarters() -> None:
    """An hour slot with four quarter-hour prices gets their average, not
    the price of the first quarter."""
    from datetime import UTC, datetime, timedelta

    from custom_components.homebatteryassist.engine.planning.battery_plan import (
        _price_over,
    )
    from custom_components.homebatteryassist.engine.sources.prices.price_points import (
        PricePoint,
    )

    start = datetime(2026, 11, 18, 7, tzinfo=UTC)
    quarters = [
        PricePoint(
            start + timedelta(minutes=15 * i),
            start + timedelta(minutes=15 * (i + 1)),
            p,
        )
        for i, p in enumerate((0.20, 0.30, 0.35, 0.35))
    ]
    hour = _price_over(quarters, start, start + timedelta(hours=1))
    assert hour is not None and abs(hour - 0.30) < 1e-9
    assert _price_over(quarters, start, start + timedelta(minutes=15)) == 0.20
    assert (
        _price_over(quarters, start + timedelta(hours=2), start + timedelta(hours=3))
        is None
    )


def test_first_slot_only_counts_the_time_left() -> None:
    """At 00:45 the 00:00 slot has 15 minutes left: a 2 kW discharge takes
    0.5 kWh (10 % of 5 kWh), not 2 kWh."""
    slots = _slots([2000.0, 0.0])
    plan = plan_batteries(
        [_battery(soc=50.0)],
        slots,
        {},
        _prices([0.3, 0.3]),
        mode=MODE_NOM,
        now=T0 + timedelta(minutes=45),
    )
    assert plan.slots[0].power_w == -2000.0
    # 0.5 kWh / 0.9 from the cells = 0.556 kWh = 11.1 % of 5 kWh.
    assert plan.slots[0].soc == pytest.approx(50.0 - 11.1, abs=0.2)


def test_full_charge_is_in_the_state_of_charge() -> None:
    """A forced full charge raises the plan's state of charge (and is not
    stopped by the maximum charge price); afterwards it is full."""
    from custom_components.homebatteryassist.engine.planning.battery_plan import (
        PlanRules,
    )

    slots = _slots([0.0, 0.0, 0.0])
    plan = plan_batteries(
        [_battery(soc=50.0)],
        slots,
        {},
        _prices([0.3, 0.3, 0.3]),
        mode=MODE_NOM,
        rules=PlanRules(max_charge_price=0.05),
        forced={T0: 2500.0, T0 + H: 2500.0},
    )
    assert plan.slots[0].power_w == 2500.0
    assert plan.slots[0].soc > 90.0
    # Only what still fits: full after the second slot.
    assert plan.slots[1].soc == 100.0
    assert plan.slots[1].power_w < 2500.0
    assert plan.slots[2].power_w == 0.0


def test_a_full_battery_takes_no_more_charge() -> None:
    """Two batteries of 2.5 kW, one full and one at 10 %: with 5 kW surplus
    only the empty one charges (2.5 kW), not the pack's 5 kW."""
    full, empty = _battery(soc=100.0), _battery(soc=10.0)
    slots = _slots([0.0])
    plan = plan_batteries(
        [full, empty], slots, {T0: 5000.0}, _prices([0.3]), mode=MODE_NOM
    )
    assert plan.slots[0].power_w == 2500.0
    # Discharging: only the full one gives (the other is at its minimum).
    plan = plan_batteries(
        [full, empty], _slots([5000.0]), {}, _prices([0.3]), mode=MODE_NOM
    )
    assert plan.slots[0].power_w == -2500.0


def test_arbitrage_stores_a_small_surplus() -> None:
    """A solar surplus that is not a whole number of levels is stored, not
    exported (or rounded up with grid power)."""
    slots = _slots([200.0] * 8)
    pv = {T0 + i * H: 350.0 for i in range(4)}  # 150 W surplus
    prices = _prices([0.25] * 4 + [0.40] * 4)
    plan = plan_batteries(
        [_battery(soc=20.0)], slots, pv, prices, mode=MODE_ARBITRAGE, export_factor=0.25
    )
    first = plan.slots[:4]
    assert all(s.power_w > 100 for s in first), [s.power_w for s in first]
    assert all(abs(s.grid_w) < 10 for s in first), [s.grid_w for s in first]


def test_share_sequential_and_forced_first() -> None:
    """Charging one after the other: the emptiest first, up to its power; a
    full charge goes to its own battery first."""
    from custom_components.homebatteryassist.engine.planning.battery_plan import _share
    from custom_components.homebatteryassist.engine.planning.planners.base import (
        PackMember,
    )

    a = PackMember(5000, 4000, 500, 5000, 1.0, 2000, 2000, "a")
    b = PackMember(5000, 1000, 500, 5000, 1.0, 2000, 2000, "b")
    power, new = _share([a, b], [4000.0, 1000.0], 2500.0, 1.0, sequential=True)
    assert power == 2500.0
    assert new == [4500.0, 3000.0]  # b (emptiest) 2000 W, a the rest
    power, new = _share([a, b], [4000.0, 1000.0], 1500.0, 1.0, {"a": 1000.0})
    assert new[0] == 5000.0  # a's full charge first (1000 W), b the rest
    assert new[1] == 1500.0


def test_share_reserves_per_battery() -> None:
    """Discharging: each battery keeps its own night reserve; below its own
    peak reserve only for what the pack still asks."""
    from custom_components.homebatteryassist.engine.planning.battery_plan import _share
    from custom_components.homebatteryassist.engine.planning.planners.base import (
        PackMember,
    )

    # Night reserve 1500 Wh each; a has 4000, b 1600.
    a = PackMember(5000, 4000, 500, 5000, 1.0, 2000, 2000, "a", 1500, 0)
    b = PackMember(5000, 1600, 500, 5000, 1.0, 2000, 2000, "b", 1500, 0)
    power, new = _share([a, b], [4000.0, 1600.0], -2000.0, 1.0, night=True)
    assert power == -2000.0
    assert new[1] >= 1500.0  # b keeps its own night reserve
    assert sum(new) == pytest.approx(5600.0 - 2000.0)
    # By day the same request may go down to the minimum.
    power, new = _share([a, b], [4000.0, 1600.0], -3000.0, 1.0)
    assert power == -3000.0
    # Peak reserve 3000 Wh each: first above it, below only when asked more.
    a = PackMember(5000, 4000, 500, 5000, 1.0, 2000, 2000, "a", 0, 3000)
    b = PackMember(5000, 3500, 500, 5000, 1.0, 2000, 2000, "b", 0, 3000)
    power, new = _share([a, b], [4000.0, 3500.0], -1500.0, 1.0, peak=True)
    assert power == -1500.0
    assert new == [3000.0, 3000.0]
    # More asked, but no import above the peak: not below the peak reserve.
    power, new = _share([a, b], [4000.0, 3500.0], -2000.0, 1.0, peak=True)
    assert power == -1500.0
    # 500 W import above the peak: that part from below the peak reserve.
    power, new = _share(
        [a, b], [4000.0, 3500.0], -2000.0, 1.0, peak=True, peak_excess=500.0
    )
    assert power == -2000.0
    assert min(new) < 3000.0
