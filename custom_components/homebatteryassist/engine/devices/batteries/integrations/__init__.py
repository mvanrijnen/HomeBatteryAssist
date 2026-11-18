"""HA integrations through which batteries are read (one reader per integration).

One file per integration. A reader whose entity keys were not verified on a
real installation keeps ``verified = False`` and is shown as "not tested".
"""

from __future__ import annotations

from ..base import BatteryReader
from .marstek_modbus_integration import MarstekModbusReader
from .omnibattery_integration import OmnibatteryReader
from .victron_gx_integration import VictronGxReader

READERS: tuple[BatteryReader, ...] = (
    OmnibatteryReader(),
    MarstekModbusReader(),
    VictronGxReader(),
)

__all__ = ["READERS", "MarstekModbusReader", "OmnibatteryReader", "VictronGxReader"]
