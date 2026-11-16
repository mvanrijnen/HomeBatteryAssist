"""Type: Indevolt SolidFlex 3600 (model code ``YZ-E3600``)."""

from __future__ import annotations

from .flex import IndevoltFlex


class IndevoltSolidFlex3600(IndevoltFlex):
    """Indevolt SolidFlex 3600."""

    type = "SolidFlex 3600"
    models = ("YZ-E3600", "SolidFlex 3600")
