"""Readers: how batteries are read through another integration's entities.

One file per integration. Only add a reader whose entity keys were verified on
a real installation.
"""

from __future__ import annotations

from ..base import BatteryReader
from .marstek_modbus import MarstekModbusReader
from .omnibattery import OmnibatteryReader

READERS: tuple[BatteryReader, ...] = (OmnibatteryReader(), MarstekModbusReader())

__all__ = ["READERS", "MarstekModbusReader", "OmnibatteryReader"]
