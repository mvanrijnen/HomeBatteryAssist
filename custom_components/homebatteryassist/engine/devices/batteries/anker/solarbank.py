"""Type range: Anker SOLIX Solarbank."""

from __future__ import annotations

from . import Anker


class AnkerSolarbank(Anker):
    """The Solarbank range.

    ``models`` hold the product names and the 4-character product codes found
    in the device's model / serial registers (see ``modbus.product_code``).
    """

    range = "Solarbank"
