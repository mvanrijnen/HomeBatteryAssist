"""Conversion of sensor states to physical values."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfElectricCurrent,
    UnitOfPower,
)
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import PowerConverter

from ...const import NOMINAL_VOLTAGE

_CURRENT_TO_AMPERE = {
    UnitOfElectricCurrent.AMPERE: 1.0,
    UnitOfElectricCurrent.MILLIAMPERE: 0.001,
}


def state_to_watts(state: State | None) -> float | None:
    """Return the state of a power or current sensor in W, or None if unusable.

    Current (A) is converted with ``NOMINAL_VOLTAGE``.
    """
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    try:
        value = float(state.state)
    except ValueError:
        return None

    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    if unit in _CURRENT_TO_AMPERE:
        return value * _CURRENT_TO_AMPERE[unit] * NOMINAL_VOLTAGE
    if unit not in PowerConverter.VALID_UNITS:
        return None
    try:
        return PowerConverter.convert(value, unit, UnitOfPower.WATT)
    except HomeAssistantError:
        return None


def parse_time(value: Any) -> datetime | None:
    """Parse a timezone-aware timestamp (datetime or ISO string) to UTC."""
    if isinstance(value, datetime):
        return dt_util.as_utc(value) if value.tzinfo else None
    if isinstance(value, str):
        parsed = dt_util.parse_datetime(value)
        if parsed is not None and parsed.tzinfo is not None:
            return dt_util.as_utc(parsed)
    return None


def parse_float(value: Any) -> float | None:
    """Parse a number, or None."""
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
