"""SMA Sunny Tripower Storage X / Sunny Island X (ennexOS) via Modbus TCP.

From SMA's "SMAModbus-STPS-X-SI-X-TI": the mode **40210** (U32: 303 off,
1077 manual in W, 1078 manual in %, 1079 external = default), the limit in W
**40212** (U32, 0..60000), the fallback **41193** (2506 keep the values =
default, 2507 use the fallback values) and the timeout **41195** (s, 1..1800,
default 600). Unit 3, port 502. The energy management of the System Manager
must be switched off when it is controlled over unit 3, and with a Sunny
Home Manager the limit belongs to the Home Manager. *Not verified on a
device*. In this phase nothing is sent.
"""

from __future__ import annotations

from .base import InverterDriver, Point

TIMEOUT_S = 60  # back to the fallback values after 60 s without a write


class SmaStorageXInverterDriver(InverterDriver):
    """SMA Sunny Tripower Storage X / Sunny Island X, limit in W."""

    key = "sma_storage_x"
    name = "SMA Storage X"
    limits = "power"
    points = (
        Point(41193, "Fallback: use the fallback values", "2507", 3),
        Point(41195, "Timeout (s)", str(TIMEOUT_S), 3),
        Point(40210, "Active power limit: manual in W", "1077", 3),
        Point(40212, "Active power limit (W)", "{limit_w}", 3),
    )
