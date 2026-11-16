"""Type range: Sessy home battery (AC-coupled, controlled through a dongle
with a local HTTP API)."""

from __future__ import annotations

from . import SessyBrand


class SessyHomeBattery(SessyBrand):
    """The Sessy home battery range."""

    range = "Home battery"
