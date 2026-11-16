"""Planner modules: the built-in ones and the user's own.

Built-in planners live in this folder (updated with the integration). Own
planners are Python files in ``/config/homebatteryassist/planners/``; each
defines one or more ``Planner`` subclasses (see ``template.py``). They are
loaded when the integration starts or reloads, get the key ``custom_<key>``
and appear in the settings next to the built-in ones. A file that fails to
load is skipped and logged. HomeBatteryAssist checks every plan afterwards
(``battery_plan.finalise``) and inserts full charges after that.
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant

from ...user_modules import CUSTOM_PREFIX, async_load_modules, load_modules_from
from .arbitrage import ArbitrageFullPlanner, ArbitragePlanner
from .base import Planner, PlannerBattery, PlannerInput, PlannerResult, PlannerSlot
from .nom import ManualPlanner, NomPlanner, TimeSlotsPlanner

BUILTIN: dict[str, Planner] = {
    p.key: p
    for p in (
        NomPlanner(),
        ArbitragePlanner(),
        ArbitrageFullPlanner(),
        TimeSlotsPlanner(),
        ManualPlanner(),
    )
}

__all__ = [
    "BUILTIN",
    "CUSTOM_PREFIX",
    "Planner",
    "PlannerBattery",
    "PlannerInput",
    "PlannerResult",
    "PlannerSlot",
    "async_load_user_planners",
]


def load_planners_from(folder: Path) -> dict[str, Planner]:
    """Planners defined in the Python files of ``folder`` (blocking)."""
    planners = load_modules_from(folder, Planner, "planners")
    return {k: p for k, p in planners.items() if type(p).plan is not Planner.plan}


async def async_load_user_planners(hass: HomeAssistant) -> dict[str, Planner]:
    """The user's own planners from ``/config/homebatteryassist/planners``."""
    planners = await async_load_modules(hass, "planners", Planner)
    return {k: p for k, p in planners.items() if type(p).plan is not Planner.plan}
