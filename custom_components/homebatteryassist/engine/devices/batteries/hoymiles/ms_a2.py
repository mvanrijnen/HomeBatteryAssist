"""Type: Hoymiles MS-A2 (per unit; up to 2 units in a system)."""

from __future__ import annotations

from .ms import HoymilesMs


class HoymilesMsA2(HoymilesMs):
    """Hoymiles MS-A2."""

    type = "MS-A2"
    models = ("MS-A2", "MS-A2-FX", "MS-A2-ZZ", "MSA2")
    capacity_kwh = 2.24
    max_charge_w = 1000.0
    max_discharge_w = 1000.0
