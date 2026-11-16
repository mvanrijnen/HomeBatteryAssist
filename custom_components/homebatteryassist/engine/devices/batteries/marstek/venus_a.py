"""Type: Marstek Venus A (with DC PV inputs, up to several battery packs).

Only the power ceiling of the hardware is set (1500 W charge and discharge).
Direct driver: ``modbus.py`` (prepared, not used).
"""

from __future__ import annotations

from .venus import MarstekVenus


class MarstekVenusA(MarstekVenus):
    """Marstek Venus A."""

    type = "Venus A"
    models = ("Venus A",)
    max_charge_w = 1500.0
    max_discharge_w = 1500.0
