"""Brand: Sessy (Netherlands). Ranges and types inherit from it
(``home_battery.py`` → ``sessy.py``). Read directly over the local HTTP API:
``http.py`` (prepared, not used)."""

from __future__ import annotations

from ..base import BatteryModel


class SessyBrand(BatteryModel):
    """Sessy batteries."""

    brand = "Sessy"
