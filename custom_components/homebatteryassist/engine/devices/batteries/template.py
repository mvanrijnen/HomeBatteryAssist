"""Template for battery drivers — a code example only, never registered.

A battery driver has two parts (see ``base.py``):

1. A **model** per brand → type range → type, by inheritance. Put each in its
   own file: ``<brand>/__init__.py`` (brand), ``<brand>/<range>.py`` and
   ``<brand>/<type>.py``; add the type to ``MODELS`` in ``__init__.py``. Set
   only specifications you know for sure.
2. A **reader** per integration that exposes such batteries, in
   ``readers/<integration>.py``; add it to ``READERS`` in
   ``readers/__init__.py``. Its ``profile`` recognises the batteries of that
   integration (state of charge and power sensor, starting values).

Rules:

- Reading only uses Home Assistant's states and registries (the entities of
  the battery's own integration). Never open an own connection to the battery
  that could compete with its integration.
- The write methods describe how the battery *would* be controlled. They are
  never called by HomeBatteryAssist while it is read-only; keep
  ``can_write = False`` until they are implemented and tested.
- Mark a reader ``verified`` only after testing it on a real installation.
"""

from __future__ import annotations

from typing import ClassVar

from homeassistant.core import HomeAssistant

from ....const import SIGN_CHARGING_POSITIVE
from ...measure.batteries import BatteryConfig
from .base import BatteryModel, BatteryProfile
from .readers.entities import EntityReader

# -- 1. Model: brand -> type range -> type (normally three files) -------------


class ExampleBrand(BatteryModel):
    """Brand (``example/__init__.py``)."""

    brand = "Example"


class ExampleHome(ExampleBrand):
    """Type range (``example/home.py``)."""

    range = "Home"


class ExampleHome10(ExampleHome):
    """Type (``example/home_10.py``)."""

    type = "Home 10"
    models = ("Home 10", "HOME10")  # model names as integrations report them
    capacity_kwh = 10.0
    max_charge_w = 5000.0
    max_discharge_w = 5000.0
    usable_pct = 90.0
    rated_cycles = 6000
    warranty_years = 10


# -- 2. Reader: one integration (``readers/my_battery.py``) --------------------


class TemplateBatteryReader(EntityReader):
    """Example: batteries of the integration ``my_battery`` (does not exist)."""

    key = "my_battery"  # the integration domain of the battery's entities
    name = "My battery"
    verified = False  # reading tested on a real installation?
    can_write = False  # write methods implemented?
    profile = BatteryProfile(
        platform="my_battery",
        label="My battery",
        soc="battery_level",  # translation key of the state of charge sensor
        power="battery_power",  # translation key of the power sensor
        power_sign=SIGN_CHARGING_POSITIVE,
        capacity=("sensor", "capacity"),
    )

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
