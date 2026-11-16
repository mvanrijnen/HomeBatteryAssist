"""Type: Sessy (the API reports no model; one type is known).

Charge / discharge ceilings as Omnibattery uses them (facts only); the
capacity is not readable locally and must be entered by the user.
"""

from __future__ import annotations

from .home_battery import SessyHomeBattery


class Sessy(SessyHomeBattery):
    """Sessy home battery."""

    type = "Home battery"
    models = ("Sessy", "Sessy Home battery")
    max_charge_w = 2200.0
    max_discharge_w = 1700.0
