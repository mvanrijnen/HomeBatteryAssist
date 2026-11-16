"""Type range: Zendure SolarFlow (capacity depends on the packs connected)."""

from __future__ import annotations

from . import Zendure


class ZendureSolarFlow(Zendure):
    """The SolarFlow range."""

    range = "SolarFlow"
