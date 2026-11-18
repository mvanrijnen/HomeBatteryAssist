"""SMA inverters (Sunny Boy, Sunny Tripower) via Modbus TCP, on their own.

Only for an SMA inverter that is NOT managed by a Sunny Home Manager: when a
Sunny Home Manager and the inverter are together in ennexOS / Sunny Portal,
the limit belongs to the Home Manager (``sma_home_manager.py``), never
directly to the inverter.

The registers differ per SMA model. The points below are an example from
SMA's Modbus documentation (active power through communication: 40151 = 802,
"active", 803 = off; setpoint in W: 40149; unit id 3, port 502), not
verified on a device: check them against the Modbus parameter list of your
model. Modbus must be switched on in the inverter. In this phase nothing is
sent.
"""

from __future__ import annotations

from .base import InverterDriver, Point


class SmaModbusInverterDriver(InverterDriver):
    """SMA inverter without a Home Manager, active power setpoint via Modbus."""

    key = "sma_modbus"
    name = "SMA Modbus"
    limits = "power"
    points = (
        Point(40151, "Active power via communication", "802"),
        Point(40149, "Active power setpoint (W)", "{limit_w}"),
    )
