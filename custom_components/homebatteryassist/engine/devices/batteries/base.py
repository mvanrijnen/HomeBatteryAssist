"""The contract of a battery driver: read a battery the same way, whatever brand.

A battery is linked to HomeBatteryAssist through the entities of its own
integration (state of charge and power sensors in the battery sub-entry). A
battery driver knows one such integration and adds:

- ``find(hass)``: batteries of the integration that are not linked yet, with
  suggested sub-entry values (see ``inputs.profiles``);
- ``telemetry(hass, config)``: extra live details (temperature, voltages,
  cycles, energy today, efficiency) read from the entities on the battery's
  device — nothing is sent to the battery;
- write methods (``async_set_power``, ``async_release``): how the battery
  *would* be controlled. They are part of the driver model so control can be
  added later, but **HomeBatteryAssist never calls them** while it is
  read-only. ``can_write`` says whether a driver implements them.

Add a driver: copy ``template.py``, fill it in and add it to ``DRIVERS`` in
``__init__.py``. Mark it ``verified`` only after testing on a real
installation (reading); writing stays untested until control is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ...measure.batteries import BatteryConfig


@dataclass(slots=True)
class BatteryTelemetry:
    """Extra live details of a battery; None = not known."""

    temperature_c: float | None = None
    voltage_v: float | None = None
    cell_min_v: float | None = None
    cell_max_v: float | None = None
    cycles: float | None = None
    charged_today_kwh: float | None = None
    discharged_today_kwh: float | None = None
    efficiency_pct: float | None = None
    extra: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, float]:
        """Known values only."""
        values = {
            "temperature_c": self.temperature_c,
            "voltage_v": self.voltage_v,
            "cell_min_v": self.cell_min_v,
            "cell_max_v": self.cell_max_v,
            "cycles": self.cycles,
            "charged_today_kwh": self.charged_today_kwh,
            "discharged_today_kwh": self.discharged_today_kwh,
            "efficiency_pct": self.efficiency_pct,
            **self.extra,
        }
        return {k: v for k, v in values.items() if v is not None}


class BatteryDriver:
    """A kind of battery (one integration that exposes batteries)."""

    key: str = ""  # the integration domain (platform of its entities)
    name: str = ""
    verified: bool = False  # reading tested on a real installation
    can_write: bool = False  # write methods implemented (never used yet)

    def telemetry(self, hass: HomeAssistant, config: BatteryConfig) -> BatteryTelemetry:
        """Extra live details of the battery (default: none)."""
        return BatteryTelemetry()

    async def async_set_power(
        self, hass: HomeAssistant, config: BatteryConfig, power_w: float
    ) -> None:
        """Charge (+) or discharge (-) at ``power_w``. Not used yet."""
        raise NotImplementedError

    async def async_release(self, hass: HomeAssistant, config: BatteryConfig) -> None:
        """Give control back to the battery / its own integration. Not used yet."""
        raise NotImplementedError


def device_entities(
    hass: HomeAssistant, config: BatteryConfig
) -> dict[tuple[str, str], str]:
    """(domain, translation key) -> entity id, for the battery's device.

    The device is the one of the battery's state of charge sensor.
    """
    registry = er.async_get(hass)
    soc = registry.async_get(config.soc_sensor) if config.soc_sensor else None
    if soc is None or soc.device_id is None:
        return {}
    return {
        (e.domain, e.translation_key or ""): e.entity_id
        for e in er.async_entries_for_device(registry, soc.device_id)
        if not e.disabled_by
    }


def platform_of(hass: HomeAssistant, config: BatteryConfig) -> str | None:
    """The integration that provides the battery's state of charge sensor."""
    entry = (
        er.async_get(hass).async_get(config.soc_sensor) if config.soc_sensor else None
    )
    return entry.platform if entry else None
