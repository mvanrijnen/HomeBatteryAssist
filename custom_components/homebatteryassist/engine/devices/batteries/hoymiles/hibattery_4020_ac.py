"""Type: Hoymiles HiBattery 4020 AC (per unit; up to 4 units)."""

from __future__ import annotations

from .hibattery import HoymilesHiBattery


class HoymilesHiBattery4020Ac(HoymilesHiBattery):
    """Hoymiles HiBattery 4020 AC."""

    type = "HiBattery 4020 AC"
    models = ("HB-4020-AC", "HB-4020-ACM", "HiBattery 4020 AC")
    capacity_kwh = 4.02
    max_charge_w = 2000.0
    max_discharge_w = 2000.0
