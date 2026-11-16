"""Type: Indevolt BK1600 (model code ``YZ-E1600``)."""

from __future__ import annotations

from .bk import IndevoltBk


class IndevoltBk1600(IndevoltBk):
    """Indevolt BK1600."""

    type = "BK1600"
    models = ("YZ-E1600", "BK1600")
