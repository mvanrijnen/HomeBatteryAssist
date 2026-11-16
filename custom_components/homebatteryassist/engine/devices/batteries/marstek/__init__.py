"""Brand: Marstek. What all Marstek batteries share; type ranges and types
inherit from it (``venus.py`` → ``venus_e_v2.py``, ``venus_e_v3.py``,
``venus_a.py``, ``venus_d.py``). Read directly over Modbus TCP: ``modbus.py``
(prepared, not used)."""

from __future__ import annotations

from ..base import BatteryModel


class Marstek(BatteryModel):
    """Marstek home batteries."""

    brand = "Marstek"
