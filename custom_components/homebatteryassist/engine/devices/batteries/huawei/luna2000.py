"""Type range: Huawei LUNA2000 (read through the SUN2000 inverter)."""

from __future__ import annotations

from . import Huawei


class HuaweiLuna2000(Huawei):
    """The LUNA2000 range: battery packs on a power module, DC-coupled to a
    SUN2000 hybrid inverter. Capacity and power limits depend on the number
    of packs; the inverter reports both (rated capacity, max charge /
    discharge power)."""

    range = "LUNA2000"
