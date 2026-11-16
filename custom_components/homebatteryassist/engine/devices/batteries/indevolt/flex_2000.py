"""Type: Indevolt SolidFlex/PowerFlex 2000 (model code ``YZ-E2000G2``)."""

from __future__ import annotations

from .flex import IndevoltFlex


class IndevoltFlex2000(IndevoltFlex):
    """Indevolt SolidFlex/PowerFlex 2000."""

    type = "SolidFlex/PowerFlex 2000"
    models = ("YZ-E2000G2", "SolidFlex/PowerFlex 2000")
    min_firmware = "V1406.07.002E"
