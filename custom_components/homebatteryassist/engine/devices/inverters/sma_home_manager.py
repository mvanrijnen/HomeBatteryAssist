"""SMA inverters managed by a Sunny Home Manager 2.0 (ennexOS / Sunny Portal).

There the limit belongs to the Home Manager, which limits all its SMA
inverters itself; an inverter must not be written directly beside it (SMA:
a second controller competes with it, the inverter logs event 8708).

The Home Manager 2.0 (software package >= 2.10) is a Modbus TCP server for
grid management services (SMA "HM-20-Modbus-NSD-TI"): port 502, **unit 2**,
register **40016** = active power setpoint in % of the system's PMAX (S16,
write only, -100..100). The Home Manager takes the house consumption into
account, so this limits the **export**, not the production. A setpoint is
valid for 60 minutes and falls back to 100 % (or the limit set in the Home
Manager) when it is not renewed; at most one write per second; cyclic writes
are allowed (grid management value, no flash wear).

Needed in Sunny Portal / ennexOS: *Grid management services via Ethernet
based communication* = Yes, and *Limitation of active power feed-in* on
(*Implement external setpoints only* if there is no fixed limit). SMA writes
this for grid operators; evcc uses the same register as its curtailer. From
SMA's documentation, *not verified on a device*. In this phase nothing is
sent. The Home Manager is read as a grid meter already.
"""

from __future__ import annotations

from .base import InverterDriver, Point


class SmaHomeManagerInverterDriver(InverterDriver):
    """SMA inverters through their Sunny Home Manager 2.0 (export limit)."""

    key = "sma_home_manager"
    name = "SMA Sunny Home Manager"
    limits = "export"
    points = (
        Point(
            40016, "Active power setpoint (% of PMAX)", "{limit_w} W as % of PMAX", 2
        ),
    )
