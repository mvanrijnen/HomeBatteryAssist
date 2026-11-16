"""Type: Zendure SolarFlow 2400 Pro (DC PV input).

AC charge / discharge limits from Omnibattery's facts; the device's own
``chargeMaxLimit`` can be lower."""

from __future__ import annotations

from .solarflow import ZendureSolarFlow


class ZendureSolarFlow2400Pro(ZendureSolarFlow):
    """Zendure SolarFlow 2400 Pro."""

    type = "SolarFlow 2400 Pro"
    models = ("SolarFlow 2400 Pro", "Zendure SolarFlow 2400 Pro")
    max_charge_w = 2400.0
    max_discharge_w = 2400.0
