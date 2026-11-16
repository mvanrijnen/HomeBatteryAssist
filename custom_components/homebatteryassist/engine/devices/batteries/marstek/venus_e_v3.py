"""Type: Marstek Venus E v3.

Capacity and power as reported by the battery on a real installation; rated
cycles, warranty and usable part as given by an owner. Read through
Omnibattery or Marstek Modbus (``readers/``).
"""

from __future__ import annotations

from .venus import MarstekVenus


class MarstekVenusEV3(MarstekVenus):
    """Marstek Venus E v3."""

    type = "Venus E v3"
    models = ("Venus E v3", "VenusE 3.0", "Venus E 3.0")
    capacity_kwh = 5.12
    max_charge_w = 2500.0
    max_discharge_w = 2500.0
    usable_pct = 80.0
    rated_cycles = 6000
    warranty_years = 10
