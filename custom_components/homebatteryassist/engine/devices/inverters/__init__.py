"""PV inverter drivers (prepared, not used: nothing is sent in this phase)."""

from __future__ import annotations

from .base import InverterDriver, Point
from .sma_home_manager import SmaHomeManagerInverterDriver
from .sma_modbus import SmaModbusInverterDriver

DRIVERS: tuple[InverterDriver, ...] = (
    SmaHomeManagerInverterDriver(),
    SmaModbusInverterDriver(),
)


def get_driver(key: str | None) -> InverterDriver | None:
    """The driver with this key, if any."""
    return next((d for d in DRIVERS if d.key == key), None)


__all__ = ["DRIVERS", "InverterDriver", "Point", "get_driver"]
