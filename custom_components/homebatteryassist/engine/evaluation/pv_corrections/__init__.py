"""PV correction modules: the built-in ones and the user's own.

Built-in corrections live in this folder (updated with the integration); the
original one (per lead time) always stays available. Own corrections are
Python files in ``/config/homebatteryassist/pv_corrections/`` (see
``template.py``), keyed ``custom_<key>``. All corrections run every cycle so
their accuracy can be compared; the chosen one is used for the plans.
``apply_pv_correction`` runs one with HomeBatteryAssist's final check.
"""

from __future__ import annotations

import math
from pathlib import Path

from homeassistant.core import HomeAssistant

from ...own_modules import async_load_modules, load_modules_from
from .base import (
    MAX_EXTRA_WH,
    MAX_FACTOR,
    PvCorrectionInput,
    PvCorrector,
    PvResult,
)
from .hour_and_level import HourAndLevelCorrector
from .lead_time import LeadTimeCorrector

DEFAULT_PV_CORRECTOR = "hour_and_level"
BUILTIN: dict[str, PvCorrector] = {
    c.key: c for c in (HourAndLevelCorrector(), LeadTimeCorrector())
}

__all__ = [
    "BUILTIN",
    "DEFAULT_PV_CORRECTOR",
    "PvCorrectionInput",
    "PvCorrector",
    "PvResult",
    "apply_pv_correction",
    "async_load_user_pv_correctors",
    "load_pv_correctors_from",
]


def _usable(found: dict[str, PvCorrector]) -> dict[str, PvCorrector]:
    return {
        k: c for k, c in found.items() if type(c).correct is not PvCorrector.correct
    }


def load_pv_correctors_from(folder: Path) -> dict[str, PvCorrector]:
    """PV corrections defined in the Python files of ``folder`` (blocking)."""
    return _usable(load_modules_from(folder, PvCorrector, "pv_corrections"))


async def async_load_user_pv_correctors(
    hass: HomeAssistant,
) -> dict[str, PvCorrector]:
    """The user's own PV corrections (``/config/homebatteryassist/pv_corrections``)."""
    return _usable(await async_load_modules(hass, "pv_corrections", PvCorrector))


def apply_pv_correction(corrector: PvCorrector, data: PvCorrectionInput) -> list[float]:
    """Corrected Wh per slot; values that fail the final check get the
    built-in correction per lead time. Raises what the module raises."""
    result = list(corrector.correct(data))
    out = []
    for i, (start, raw) in enumerate(data.slots):
        value = result[i] if i < len(result) else None
        try:
            number = float(value) if value is not None else None
        except (TypeError, ValueError):
            number = None
        if (
            number is None
            or not math.isfinite(number)
            or number < 0
            or number > max(raw, 0.0) * MAX_FACTOR + MAX_EXTRA_WH
        ):
            number = max(raw * data.lead_factor(start), 0.0)
        out.append(number)
    return out
