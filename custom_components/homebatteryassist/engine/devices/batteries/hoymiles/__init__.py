"""Brand: Hoymiles micro-storage. Ranges and types inherit from it
(``ms.py`` → ``ms_a2.py``; ``hibattery.py`` → ``hibattery_*.py``).
Read directly over MQTT: ``mqtt.py`` (prepared, not used)."""

from __future__ import annotations

from ..base import BatteryModel


class Hoymiles(BatteryModel):
    """Hoymiles batteries."""

    brand = "Hoymiles"
