"""Type: Zendure SolarFlow 800 Pro (PV input).

AC charge / discharge limits from Omnibattery's facts; the device's own
``chargeMaxLimit`` can be lower."""

from __future__ import annotations

from .solarflow import ZendureSolarFlow


class ZendureSolarFlow800Pro(ZendureSolarFlow):
    """Zendure SolarFlow 800 Pro."""

    type = "SolarFlow 800 Pro"
    models = ("SolarFlow 800 Pro", "Zendure SolarFlow 800 Pro")
    max_charge_w = 1000.0
    max_discharge_w = 800.0
