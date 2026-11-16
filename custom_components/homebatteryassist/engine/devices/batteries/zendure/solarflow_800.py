"""Type: Zendure SolarFlow 800 (PV input).

AC charge / discharge limits from Omnibattery's facts; the device's own
``chargeMaxLimit`` can be lower."""

from __future__ import annotations

from .solarflow import ZendureSolarFlow


class ZendureSolarFlow800(ZendureSolarFlow):
    """Zendure SolarFlow 800."""

    type = "SolarFlow 800"
    models = ("SolarFlow 800", "Zendure SolarFlow 800")
    max_charge_w = 1000.0
    max_discharge_w = 800.0
