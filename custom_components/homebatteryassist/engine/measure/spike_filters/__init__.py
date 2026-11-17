"""Spike filter modules: the built-in one and the user's own.

The built-in filter lives in this folder (updated with the integration) and
always stays available. Own filters are Python files in
``/config/homebatteryassist/spike_filters/`` (see ``template.py``), keyed
``custom_<key>``. ``checked`` applies HomeBatteryAssist's final check to what a
filter says.
"""

from __future__ import annotations

import math
from pathlib import Path

from homeassistant.core import HomeAssistant

from ...own_modules import async_load_modules, load_modules_from
from .base import MAX_SPIKE_WH, SpikeFilter, SpikeState
from .short_peaks import ShortPeakFilter

DEFAULT_SPIKE_FILTER = "short_peaks"
BUILTIN: dict[str, type[SpikeFilter]] = {ShortPeakFilter.key: ShortPeakFilter}

__all__ = [
    "BUILTIN",
    "DEFAULT_SPIKE_FILTER",
    "SpikeFilter",
    "SpikeState",
    "async_load_user_spike_filters",
    "checked",
    "create_spike_filter",
    "load_spike_filters_from",
]


def _usable(found: dict[str, SpikeFilter]) -> dict[str, SpikeFilter]:
    return {k: f for k, f in found.items() if type(f).update is not SpikeFilter.update}


def load_spike_filters_from(folder: Path) -> dict[str, SpikeFilter]:
    """Spike filters defined in the Python files of ``folder`` (blocking)."""
    return _usable(load_modules_from(folder, SpikeFilter, "spike_filters"))


async def async_load_user_spike_filters(
    hass: HomeAssistant,
) -> dict[str, SpikeFilter]:
    """The user's own spike filters (``/config/homebatteryassist/spike_filters``)."""
    return _usable(await async_load_modules(hass, "spike_filters", SpikeFilter))


def _number(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def checked(state: object, house_w: float | None) -> SpikeState:
    """``state`` within limits: ignore 0..consumption, ended 0..MAX_SPIKE_WH."""
    if not isinstance(state, SpikeState) or house_w is None:
        return SpikeState()
    ignore = _number(state.ignore_w)
    ended = _number(state.ended_wh)
    return SpikeState(
        min(max(ignore, 0.0), max(house_w, 0.0)) if ignore is not None else 0.0,
        ended if ended is not None and 0.0 <= ended <= MAX_SPIKE_WH else 0.0,
    )


def create_spike_filter(
    key: str,
    own: dict[str, SpikeFilter],
    threshold_w: float,
    max_duration_s: float,
) -> SpikeFilter:
    """A fresh filter for ``key`` (an own one, else built-in, else the
    default), with the settings."""
    spike_filter = own.get(key)
    if spike_filter is None:
        spike_filter = BUILTIN.get(key, BUILTIN[DEFAULT_SPIKE_FILTER])()
    spike_filter.threshold_w = float(threshold_w)
    spike_filter.max_duration_s = float(max_duration_s)
    return spike_filter
