"""Type: Zendure SolarFlow 1600 AC+ (AC-coupled).

AC charge / discharge limits from Omnibattery's facts; the device's own
``chargeMaxLimit`` can be lower."""

from __future__ import annotations

from .solarflow import ZendureSolarFlow


class ZendureSolarFlow1600AcPlus(ZendureSolarFlow):
    """Zendure SolarFlow 1600 AC+."""

    type = "SolarFlow 1600 AC+"
    models = ("SolarFlow 1600 AC+", "Zendure SolarFlow 1600 AC+")
    max_charge_w = 1600.0
    max_discharge_w = 1600.0
