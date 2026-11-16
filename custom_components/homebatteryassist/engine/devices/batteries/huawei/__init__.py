"""Brand: Huawei. Ranges and types inherit from it
(``luna2000.py`` → ``luna2000_e1.py``).
Read directly over Modbus TCP through the SUN2000 hybrid inverter the battery
is connected to: ``sun2000_direct_modbus.py`` (prepared, not used)."""

from __future__ import annotations

from ..base import BatteryModel


class Huawei(BatteryModel):
    """Huawei batteries."""

    brand = "Huawei"
