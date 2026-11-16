"""Type: Anker SOLIX Solarbank XE."""

from __future__ import annotations

from .solarbank import AnkerSolarbank


class AnkerSolarbankXe(AnkerSolarbank):
    """Anker SOLIX Solarbank XE."""

    type = "Solarbank XE"
    models = ("Solarbank XE", "DNMT", "DPP5", "DNN4", "DRE4", "E3DS")
