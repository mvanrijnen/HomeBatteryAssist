"""Type: Anker SOLIX Solarbank Max."""

from __future__ import annotations

from .solarbank import AnkerSolarbank


class AnkerSolarbankMax(AnkerSolarbank):
    """Anker SOLIX Solarbank Max."""

    type = "Solarbank Max"
    models = ("Solarbank Max", "DMY6", "DN9U", "DPTK")
