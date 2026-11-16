"""Type: Anker SOLIX Solarbank Max AC."""

from __future__ import annotations

from .solarbank import AnkerSolarbank


class AnkerSolarbankMaxAc(AnkerSolarbank):
    """Anker SOLIX Solarbank Max AC."""

    type = "Solarbank Max AC"
    models = ("Solarbank Max AC", "DMWH", "DMXU", "E25H")
