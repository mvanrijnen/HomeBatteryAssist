"""Tests for planner modules: own planners and HomeBatteryAssist's final check."""

from datetime import datetime, timedelta
from pathlib import Path

from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.forecasts.consumption import ForecastSlot
from custom_components.homebatteryassist.inputs.prices import PricePoint
from custom_components.homebatteryassist.planning.battery_plan import (
    PlanRules,
    plan_batteries,
)
from custom_components.homebatteryassist.planning.planners import (
    BUILTIN,
    Planner,
    PlannerInput,
    PlannerResult,
    load_planners_from,
)

from .test_battery_plan import _battery

T0 = datetime(2026, 11, 16, 0, 0, tzinfo=dt_util.UTC)
H = timedelta(hours=1)
TEMPLATE = (
    Path(__file__).parent.parent
    / "custom_components/homebatteryassist/planning/planners/template.py"
)


def _slots(watts: list[float]) -> list[ForecastSlot]:
    return [
        ForecastSlot(T0 + i * H, T0 + (i + 1) * H, w, w, "hour")
        for i, w in enumerate(watts)
    ]


def _prices(values: list[float]) -> list[PricePoint]:
    return [PricePoint(T0 + i * H, T0 + (i + 1) * H, p) for i, p in enumerate(values)]


class Greedy(Planner):
    """Asks for far more than possible, and for nonsense."""

    key = "greedy"
    name = "Greedy"

    def plan(self, data: PlannerInput) -> PlannerResult:
        return PlannerResult([50000.0, -50000.0, float("nan")])


def test_builtin_planners() -> None:
    """The built-in modes are planner modules."""
    assert set(BUILTIN) == {
        "nom",
        "arbitrage",
        "arbitrage_full",
        "time_slots",
        "manual",
    }


def test_final_check_cuts_back() -> None:
    """Whatever a planner asks, HomeBatteryAssist keeps it within the limits."""
    battery = _battery(soc=50.0, capacity=5.0, power=2500.0)  # min 10 %, max 100 %
    plan = plan_batteries(
        [battery],
        _slots([500.0, 500.0, 500.0]),
        {},
        _prices([0.3, 0.3, 0.3]),
        planner=Greedy(),
    )
    first, second, third = plan.slots
    # Charging: the battery's power, never above the maximum state of charge.
    assert first.power_w == 2500.0
    # Discharging: never more than the battery can, never below the minimum.
    assert -2500.0 <= second.power_w < 0
    assert second.soc >= 10.0
    # Nonsense counts as idle.
    assert third.power_w == 0.0
    assert plan.mode == plan.strategy  # strategy defaults to the mode


def test_final_check_price_rules() -> None:
    """Price rules hold for every planner: no discharging below the minimum
    discharge price, no charging from the grid above the maximum charge price."""
    rules = PlanRules(min_discharge_price=0.40, max_charge_price=0.25)
    plan = plan_batteries(
        [_battery(soc=50.0)],
        _slots([500.0, 500.0, 500.0]),
        {},
        _prices([0.30, 0.30, 0.30]),
        planner=Greedy(),
        rules=rules,
    )
    assert plan.slots[0].power_w == 0.0  # 0.30 > 0.25: no grid charging
    assert plan.slots[1].power_w == 0.0  # 0.30 < 0.40: no discharging


def test_load_own_planners(tmp_path: Path) -> None:
    """Own planner files are loaded; a broken file is skipped."""
    (tmp_path / "cheap.py").write_text(
        TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "broken.py").write_text("this is not python", encoding="utf-8")
    (tmp_path / "_private.py").write_text("raise RuntimeError", encoding="utf-8")
    planners = load_planners_from(tmp_path)
    assert list(planners) == ["custom_cheapest_hours"]
    planner = planners["custom_cheapest_hours"]
    assert planner.name == "Cheapest hours"

    # The example charges in the cheapest slots and uses it in the dearest.
    plan = plan_batteries(
        [_battery(soc=20.0)],
        _slots([500.0] * 8),
        {},
        _prices([0.20, 0.20, 0.30, 0.30, 0.30, 0.30, 0.45, 0.45]),
        planner=planner,
        mode="custom_cheapest_hours",
    )
    assert plan.mode == "custom_cheapest_hours"
    assert plan.slots[0].power_w > 0
    assert plan.slots[-1].power_w < 0
    assert load_planners_from(tmp_path / "missing") == {}


class Broken(Planner):
    """Fails."""

    key = "broken"
    name = "Broken"

    def plan(self, data: PlannerInput) -> PlannerResult:
        raise ZeroDivisionError


async def test_failing_own_planner_falls_back(hass) -> None:
    """A failing own planner is explained and zero on the meter is used."""
    from unittest.mock import patch

    from custom_components.homebatteryassist.const import CONF_PLAN_MODE

    from .test_dashboard import _set, _setup

    async def planners(_hass):
        return {"custom_broken": Broken()}

    _set(hass, "sensor.bat_soc", "50", "%")
    _set(hass, "sensor.bat_power", "0")
    with patch(
        "custom_components.homebatteryassist.async_load_user_planners", planners
    ):
        entry = await _setup(hass)
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_PLAN_MODE: "custom_broken"}
        )
        await hass.async_block_till_done()
    data = entry.runtime_data
    forecast = data.forecast
    # Two days of history, so there is a consumption forecast to plan with.
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    data.history.records = [
        {
            "start": (now - timedelta(hours=h)).isoformat(),
            "minutes": 60,
            "avg_w": 500.0,
            "coverage": 1.0,
        }
        for h in range(1, 49)
    ]
    await forecast.async_refresh()
    assert forecast.plan_mode == "custom_broken"
    assert "custom_broken" not in forecast.data.plans
    assert forecast.data.battery  # zero on the meter instead
    keys = [d["key"] for d in data.decisions.entries]
    assert "planner_failed" in keys
