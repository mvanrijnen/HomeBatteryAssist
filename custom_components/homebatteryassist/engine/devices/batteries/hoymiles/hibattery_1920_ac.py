"""Type: Hoymiles HiBattery 1920 AC (per unit; up to 6 units in a system)."""

from __future__ import annotations

from .hibattery import HoymilesHiBattery


class HoymilesHiBattery1920Ac(HoymilesHiBattery):
    """Hoymiles HiBattery 1920 AC."""

    type = "HiBattery 1920 AC"
    models = ("HB-1920-AC-SV", "HiBattery 1920 AC", "HiBattery-1920-AC-SV")
    capacity_kwh = 1.92
    max_charge_w = 1000.0
    max_discharge_w = 1000.0
