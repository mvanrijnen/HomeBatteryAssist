"""Type: Zendure SolarFlow 2400 AC+ (AC-coupled).

AC charge / discharge limits from Omnibattery's facts; the device's own
``chargeMaxLimit`` can be lower."""

from __future__ import annotations

from .solarflow import ZendureSolarFlow


class ZendureSolarFlow2400AcPlus(ZendureSolarFlow):
    """Zendure SolarFlow 2400 AC+."""

    type = "SolarFlow 2400 AC+"
    models = ("SolarFlow 2400 AC+", "Zendure SolarFlow 2400 AC+")
    max_charge_w = 2400.0
    max_discharge_w = 2400.0
