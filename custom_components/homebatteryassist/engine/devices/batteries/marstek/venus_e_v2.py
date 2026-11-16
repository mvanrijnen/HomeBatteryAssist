"""Type: Marstek Venus E v2 (second hardware version of the Venus E).

Only the power ceiling of the hardware is set (2500 W charge and discharge);
the capacity is read from the battery (register 32105) when read directly.
Direct driver: ``venus_direct_modbus.py`` (prepared, not used).
"""

from __future__ import annotations

from .venus import MarstekVenus


class MarstekVenusEV2(MarstekVenus):
    """Marstek Venus E v2."""

    type = "Venus E v2"
    models = ("Venus E v2",)
    max_charge_w = 2500.0
    max_discharge_w = 2500.0
