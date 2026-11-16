"""Template for a new battery driver — a code example only.

Never registered and never offered. Copy this file, rename the class, fill
it in, and add an instance to ``DRIVERS`` in ``__init__.py``. Also add a
``BatteryProfile`` to ``inputs/profiles.py`` so the battery is recognised when
it is added (state of charge and power sensor, properties).

Rules:

- Reading only uses Home Assistant's states and registries (the entities of the
  battery's own integration). Never open an own connection to the battery
  that could compete with its integration.
- The write methods describe how the battery *would* be controlled. They are
  never called by HomeBatteryAssist while it is read-only; keep
  ``can_write = False`` until they are implemented and tested.
"""

from __future__ import annotations

from typing import ClassVar

from homeassistant.core import HomeAssistant

from ..batteries import BatteryConfig
from .entities import EntityBatteryDriver


class TemplateBatteryDriver(EntityBatteryDriver):
    """Example: batteries of the integration ``my_battery`` (does not exist)."""

    key = "my_battery"  # the integration domain of the battery's entities
    name = "My battery"
    verified = False  # reading tested on a real installation?
    can_write = False  # write methods implemented?

    # telemetry field -> translation key of a sensor on the battery's device
    sensors: ClassVar[dict[str, str]] = {
        "temperature_c": "temperature",
        "voltage_v": "voltage",
        "cell_min_v": "cell_voltage_min",
        "cell_max_v": "cell_voltage_max",
        "cycles": "cycles",
        "charged_today_kwh": "energy_charged_today",
        "discharged_today_kwh": "energy_discharged_today",
        "efficiency_pct": "efficiency",
    }

    async def async_set_power(
        self, hass: HomeAssistant, config: BatteryConfig, power_w: float
    ) -> None:
        """Charge (+) / discharge (-) at ``power_w``, e.g. with number.set_value
        on the integration's power entities. Never called yet."""
        raise NotImplementedError

    async def async_release(self, hass: HomeAssistant, config: BatteryConfig) -> None:
        """Hand control back to the battery's own logic. Never called yet."""
        raise NotImplementedError
