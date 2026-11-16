"""Type: Anker SOLIX Solarbank XE AC."""

from __future__ import annotations

from .solarbank import AnkerSolarbank


class AnkerSolarbankXeAc(AnkerSolarbank):
    """Anker SOLIX Solarbank XE AC."""

    type = "Solarbank XE AC"
    models = ("Solarbank XE AC", "DNMS", "DPP4", "DNN3")
