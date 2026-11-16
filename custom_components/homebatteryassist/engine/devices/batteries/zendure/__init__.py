"""Brand: Zendure. Ranges and types inherit from it (``solarflow.py`` →
``solarflow_*.py``). Read directly over the local HTTP API: ``solarflow_direct_http.py``
(prepared, not used)."""

from __future__ import annotations

from ..base import BatteryModel


class Zendure(BatteryModel):
    """Zendure batteries."""

    brand = "Zendure"
