"""Brand: Marstek. What all Marstek batteries share; type ranges and types
inherit from it (``venus.py`` → ``venus_e_v3.py``)."""

from __future__ import annotations

from ..base import BatteryModel


class Marstek(BatteryModel):
    """Marstek home batteries."""

    brand = "Marstek"
