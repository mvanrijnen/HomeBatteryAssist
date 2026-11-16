"""Type: Zendure SolarFlow 800 Plus (PV input).

AC charge / discharge limits from Omnibattery's facts; the device's own
``chargeMaxLimit`` can be lower."""

from __future__ import annotations

from .solarflow import ZendureSolarFlow


class ZendureSolarFlow800Plus(ZendureSolarFlow):
    """Zendure SolarFlow 800 Plus."""

    type = "SolarFlow 800 Plus"
    models = ("SolarFlow 800 Plus", "Zendure SolarFlow 800 Plus")
    max_charge_w = 1000.0
    max_discharge_w = 800.0
