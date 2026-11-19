"""Conversion of sensor states to physical values."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfElectricCurrent,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import PowerConverter

from ..const import NOMINAL_VOLTAGE

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
    if not math.isfinite(value):  # "nan" / "inf" would poison every average
        return None

    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    if not unit:
        return value  # a power sensor without a unit: taken as W
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
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None  # no nan / inf


def state_to_celsius(state: State | None) -> float | None:
    """The state of a temperature sensor in °C (°F converted), or None."""
    if state is None:
        return None
    value = parse_float(state.state)
    if value is None or not math.isfinite(value):
        return None
    if state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.FAHRENHEIT:
        return (value - 32) / 1.8
    return value


# Sub-units of a currency (a hundredth): cent, öre, øre, pence, ...
_SUB_UNITS = {
    "ct": "EUR",
    "c": "EUR",
    "cent": "EUR",
    "cents": "EUR",
    "eurocent": "EUR",
    "€ct": "EUR",
    "€cent": "EUR",
    "öre": "SEK",
    "øre": "NOK",
    "ore": "SEK",
    "p": "GBP",
    "pence": "GBP",
}
_ENERGY = {"wh": 1000.0, "kwh": 1.0, "mwh": 0.001}


# Hundredths that name no currency of their own: Home Assistant's currency.
_GENERIC_SUB_UNITS = {"c", "ct", "cent", "cents"}


def price_unit_factor(
    unit: str | None, currency: str | None = None
) -> tuple[float, str | None]:
    """The factor that turns a price in ``unit`` into a price per kWh in the
    main currency, and that unit: ``ct/kWh`` -> (0.01, "EUR/kWh"),
    ``EUR/MWh`` -> (0.001, "EUR/kWh"). Cents without a currency of their own
    ("c", "ct", "cent") are hundredths of ``currency`` (Home Assistant's; EUR
    without one). Unknown or missing units: (1, unit) (taken as they are)."""
    if not unit or "/" not in unit:
        return 1.0, unit
    money, _, energy = unit.replace(" ", "").rpartition("/")
    per = _ENERGY.get(energy.lower())
    if per is None or not money:
        return 1.0, unit
    sub = _SUB_UNITS.get(money.lower())
    if currency and money.lower() in _GENERIC_SUB_UNITS:
        sub = currency.upper()
    if sub is not None:
        return per / 100, f"{sub}/kWh"
    return per, f"{money}/kWh"
