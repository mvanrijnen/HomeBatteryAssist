"""Type: Anker SOLIX Solarbank 4 E5000 Pro."""

from __future__ import annotations

from .solarbank import AnkerSolarbank


class AnkerSolarbankE5000Pro(AnkerSolarbank):
    """Anker SOLIX Solarbank 4 E5000 Pro."""

    type = "Solarbank 4 E5000 Pro"
    models = ("Solarbank 4 E5000 Pro", "E5000 Pro", "DN7M", "DPM4")
    dc_coupled = True  # own PV inputs
