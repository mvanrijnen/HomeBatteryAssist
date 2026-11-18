"""SMA inverters (Sunny Boy, Sunny Tripower) via Modbus TCP.

From SMA's Modbus documentation, not verified on a device: the active power
is set through communication (register 40151 = 802, "active"; 803 = off)
with the setpoint in W in register 40149 (unit id 3, port 502). Modbus must
be switched on in the inverter. In this phase nothing is sent.

The Sunny Home Manager 2.0 can limit the export of all SMA inverters too,
but that limit is set in Sunny Portal / ennexOS; no local interface to
change it is known, so there is no driver for it.
"""

from __future__ import annotations

from .base import InverterDriver, Point


class SmaModbusInverterDriver(InverterDriver):
    """SMA inverter, active power setpoint via Modbus TCP."""

    key = "sma_modbus"
    name = "SMA Modbus"
    limits = "power"
    points = (
        Point(40151, "Active power via communication", "802"),
        Point(40149, "Active power setpoint (W)", "{limit_w}"),
    )
