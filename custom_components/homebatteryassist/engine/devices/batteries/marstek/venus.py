"""Type range: Marstek Venus — plug-in AC batteries on one phase."""

from __future__ import annotations

from . import Marstek


class MarstekVenus(Marstek):
    """The Venus range."""

    range = "Venus"
