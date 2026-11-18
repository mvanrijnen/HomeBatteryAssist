"""SMA inverters managed by a Sunny Home Manager 2.0 (ennexOS / Sunny Portal).

There the export limit belongs to the Home Manager, which limits all its SMA
inverters itself; an inverter must not be limited directly (Modbus) beside
it. How the Home Manager's limit can be changed locally is not known yet (it
is set in Sunny Portal / ennexOS), so this driver has no points: it only
says the limit would go through the Home Manager. In this phase nothing is
sent. The Home Manager is read as a grid meter already.
"""

from __future__ import annotations

from .base import InverterDriver


class SmaHomeManagerInverterDriver(InverterDriver):
    """SMA inverters through their Sunny Home Manager (export limit)."""

    key = "sma_home_manager"
    name = "SMA Sunny Home Manager"
    limits = "export"
    points = ()

    def describe(self, address: str, limit_w: float) -> str:
        """The export limit the Home Manager would get."""
        where = f" {address}" if address else ""
        return f"{self.name}{where}: export limit {round(limit_w)} W"
