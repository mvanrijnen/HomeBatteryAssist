"""PV forecast source modules: the built-in one and the user's own.

A chosen forecast is stored as ``<source key>:<id>``; a plain id (older
settings) means the built-in ``energy`` source. Own sources are Python files
in ``/config/homebatteryassist/pv_forecasts/`` (see ``template.py``), keyed
``custom_<key>``.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path

from homeassistant.core import HomeAssistant

from ...user_modules import async_load_modules, load_modules_from
from .base import MAX_WH, PvForecastOption, PvForecastSource
from .energy import EnergyPlatformSource

_LOGGER = logging.getLogger(__name__)

DEFAULT_SOURCE = "energy"
BUILTIN: dict[str, PvForecastSource] = {s.key: s for s in (EnergyPlatformSource(),)}

__all__ = [
    "BUILTIN",
    "PvForecastOption",
    "PvForecastSource",
    "async_find_pv_forecasts",
    "async_load_user_pv_sources",
    "async_read_pv_forecasts",
    "load_pv_sources_from",
    "split_choice",
]


def _usable(found: dict[str, PvForecastSource]) -> dict[str, PvForecastSource]:
    return {
        k: s
        for k, s in found.items()
        if type(s).async_read is not PvForecastSource.async_read
        and type(s).async_find is not PvForecastSource.async_find
    }


def load_pv_sources_from(folder: Path) -> dict[str, PvForecastSource]:
    """PV forecast sources defined in the Python files of ``folder`` (blocking)."""
    return _usable(load_modules_from(folder, PvForecastSource, "pv_forecasts"))


async def async_load_user_pv_sources(
    hass: HomeAssistant,
) -> dict[str, PvForecastSource]:
    """The user's own sources from ``/config/homebatteryassist/pv_forecasts``."""
    return _usable(await async_load_modules(hass, "pv_forecasts", PvForecastSource))


def split_choice(choice: str) -> tuple[str, str]:
    """(source key, id) of a stored choice; a plain id is the energy source."""
    key, sep, option_id = choice.partition(":")
    return (key, option_id) if sep else (DEFAULT_SOURCE, choice)


def choice_value(key: str, option_id: str) -> str:
    """How a choice is stored (plain id for the built-in energy source)."""
    return option_id if key == DEFAULT_SOURCE else f"{key}:{option_id}"


async def async_find_pv_forecasts(
    hass: HomeAssistant, own: Mapping[str, PvForecastSource]
) -> list[tuple[str, str]]:
    """(stored value, label) of every forecast offered now."""
    found: list[tuple[str, str]] = []
    for key, source in (*BUILTIN.items(), *own.items()):
        try:
            options = await source.async_find(hass)
        except Exception:
            _LOGGER.exception("PV forecast source %s failed to list its forecasts", key)
            continue
        suffix = "" if key == DEFAULT_SOURCE else f" ({source.name or key})"
        found.extend(
            (choice_value(key, option.id), f"{option.label}{suffix}")
            for option in options
        )
    return found


async def async_read_pv_forecasts(
    hass: HomeAssistant,
    choices: Iterable[str],
    own: Mapping[str, PvForecastSource],
) -> dict[datetime, float]:
    """The chosen forecasts summed per hour (Wh), checked."""
    total: dict[datetime, float] = {}
    for choice in choices:
        key, option_id = split_choice(choice)
        source = own.get(key) or BUILTIN.get(key)
        if source is None:
            _LOGGER.debug("PV forecast source %s is not available", key)
            continue
        try:
            hours = await source.async_read(hass, option_id)
        except Exception:
            _LOGGER.exception("PV forecast %s failed", choice)
            continue
        for start, wh in (hours or {}).items():
            try:
                value = float(wh)
            except (TypeError, ValueError):
                continue
            if (
                not isinstance(start, datetime)
                or start.tzinfo is None
                or not math.isfinite(value)
                or not 0 <= value <= MAX_WH
            ):
                continue
            total[start] = total.get(start, 0.0) + value
    return dict(sorted(total.items()))
