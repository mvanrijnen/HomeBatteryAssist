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

import importlib.util
import inspect
import logging
import sys
from pathlib import Path

from homeassistant.core import HomeAssistant

from .arbitrage import ArbitrageFullPlanner, ArbitragePlanner
from .base import Planner, PlannerBattery, PlannerInput, PlannerResult, PlannerSlot
from .nom import ManualPlanner, NomPlanner, TimeSlotsPlanner

_LOGGER = logging.getLogger(__name__)

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
CUSTOM_PREFIX = "custom_"
USER_FOLDER = ("homebatteryassist", "planners")

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
    planners: dict[str, Planner] = {}
    if not folder.is_dir():
        return planners
    for path in sorted(folder.glob("*.py")):
        if path.name.startswith("_"):
            continue
        name = f"homebatteryassist_planner_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        except Exception:
            _LOGGER.exception("Planner file %s could not be loaded", path)
            continue
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(cls, Planner)
                and cls.__module__ == name
                and cls.key
                and cls.plan is not Planner.plan
            ):
                key = f"{CUSTOM_PREFIX}{cls.key}"
                if key in planners:
                    _LOGGER.warning(
                        "Planner key %s defined twice; %s skipped", key, path
                    )
                    continue
                try:
                    planners[key] = cls()
                except Exception:
                    _LOGGER.exception(
                        "Planner %s in %s could not be created", cls, path
                    )
    return planners


async def async_load_user_planners(hass: HomeAssistant) -> dict[str, Planner]:
    """The user's own planners from ``/config/homebatteryassist/planners``."""
    folder = Path(hass.config.path(*USER_FOLDER))
    planners = await hass.async_add_executor_job(load_planners_from, folder)
    if planners:
        _LOGGER.info("Own planners loaded: %s", ", ".join(planners))
    return planners
