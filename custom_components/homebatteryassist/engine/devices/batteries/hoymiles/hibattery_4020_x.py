"""Type: Hoymiles HiBattery 4020 X (per unit; PV inputs; up to 4 units)."""

from __future__ import annotations

from .hibattery import HoymilesHiBattery


class HoymilesHiBattery4020X(HoymilesHiBattery):
    """Hoymiles HiBattery 4020 X (with PV inputs)."""

    type = "HiBattery 4020 X"
    models = ("HB-4020-X", "HB-4020-XM", "HiBattery 4020 X")
    capacity_kwh = 4.02
    max_charge_w = 2000.0
    max_discharge_w = 2000.0
