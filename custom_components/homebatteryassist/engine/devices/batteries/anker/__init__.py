"""Brand: Anker SOLIX. Ranges and types inherit from it
(``solarbank.py`` → ``solarbank_*.py``).
Read directly over Modbus TCP: ``modbus.py`` (prepared, not used)."""

from __future__ import annotations

from ..base import BatteryModel


class Anker(BatteryModel):
    """Anker SOLIX batteries."""

    brand = "Anker SOLIX"
    # DC-coupled: the unit has its own PV inputs, so its battery power
    # register is the pack's power, not its AC contribution.
    dc_coupled: bool = False
