"""Type: Marstek Venus D (with DC PV inputs, up to several battery packs).

Power ceiling 2500 W with EMS firmware 149 or later; older firmware allows
only 2200 W, which the direct driver (``modbus.py``) takes into account.
"""

from __future__ import annotations

from .venus import MarstekVenus


class MarstekVenusD(MarstekVenus):
    """Marstek Venus D."""

    type = "Venus D"
    models = ("Venus D",)
    max_charge_w = 2500.0
    max_discharge_w = 2500.0
