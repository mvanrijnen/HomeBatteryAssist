"""Type: Indevolt SolidFlex/PowerFlex 1200 (model code ``YZ-E2000G2-SE``)."""

from __future__ import annotations

from .flex import IndevoltFlex


class IndevoltFlex1200(IndevoltFlex):
    """Indevolt SolidFlex/PowerFlex 1200."""

    type = "SolidFlex/PowerFlex 1200"
    models = ("YZ-E2000G2-SE", "SolidFlex/PowerFlex 1200")
    min_firmware = "V1407.07.202E"
