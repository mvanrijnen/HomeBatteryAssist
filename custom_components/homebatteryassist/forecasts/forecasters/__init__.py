"""Consumption forecaster modules: the built-in ones and the user's own.

Built-in forecasters live in this folder (updated with the integration). Own
forecasters are Python files in ``/config/homebatteryassist/forecasters/``
(see ``template.py``), keyed ``custom_<key>``. All forecasters run every
cycle so their accuracy can be compared; the chosen one is used for the plan.
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant

from ...user_modules import async_load_modules, load_modules_from
from .base import Forecaster, ForecasterInput, ForecasterResult
from .profile import ProfileForecaster
from .recent import LastWeeksForecaster

DEFAULT_FORECASTER = "profile"
BUILTIN: dict[str, Forecaster] = {
    f.key: f for f in (ProfileForecaster(), LastWeeksForecaster())
}

__all__ = [
    "BUILTIN",
    "DEFAULT_FORECASTER",
    "Forecaster",
    "ForecasterInput",
    "ForecasterResult",
    "async_load_user_forecasters",
    "load_forecasters_from",
]


def _usable(found: dict[str, Forecaster]) -> dict[str, Forecaster]:
    return {
        k: f for k, f in found.items() if type(f).forecast is not Forecaster.forecast
    }


def load_forecasters_from(folder: Path) -> dict[str, Forecaster]:
    """Forecasters defined in the Python files of ``folder`` (blocking)."""
    return _usable(load_modules_from(folder, Forecaster, "forecasters"))


async def async_load_user_forecasters(hass: HomeAssistant) -> dict[str, Forecaster]:
    """The user's own forecasters from ``/config/homebatteryassist/forecasters``."""
    return _usable(await async_load_modules(hass, "forecasters", Forecaster))
