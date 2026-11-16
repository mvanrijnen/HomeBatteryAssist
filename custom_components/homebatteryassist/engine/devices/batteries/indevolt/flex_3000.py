"""Type: Indevolt SolidFlex/PowerFlex 3000 (model code ``YZ-E3000``)."""

from __future__ import annotations

from .flex import IndevoltFlex


class IndevoltFlex3000(IndevoltFlex):
    """Indevolt SolidFlex/PowerFlex 3000."""

    type = "SolidFlex/PowerFlex 3000"
    models = ("YZ-E3000", "SolidFlex/PowerFlex 3000")
    min_firmware = "V1409.08.3034"
