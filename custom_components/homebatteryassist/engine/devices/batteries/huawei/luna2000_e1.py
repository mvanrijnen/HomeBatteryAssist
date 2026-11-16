"""Type: Huawei LUNA2000 with -E1 packs (LUNA2000-7-E1 packs on a
LUNA2000-10KW-C1 power module; 1-3 packs)."""

from __future__ import annotations

from .luna2000 import HuaweiLuna2000


class HuaweiLuna2000E1(HuaweiLuna2000):
    """Huawei LUNA2000 (-E1 packs). Capacity and limits depend on the number
    of packs, so they are left to the inverter's readings."""

    type = "LUNA2000 E1"
    models = ("LUNA2000-7-E1", "LUNA2000-10KW-C1", "LUNA2000 E1")
