"""Type range: Indevolt BK (local API generation 1: other data points;
monitored only, never to be controlled with the generation 2 points)."""

from __future__ import annotations

from . import Indevolt


class IndevoltBk(Indevolt):
    """The BK range."""

    range = "BK"
    api_generation = 1
