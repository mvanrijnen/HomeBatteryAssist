"""Reader: batteries managed by Omnibattery (ffunes/Omnibattery).

Verified for reading with a Marstek Venus E v3. ``ac_power`` is the grid side
of the battery: + discharging / - charging. The write methods follow
Omnibattery's entities but are untested and never called.
"""

from __future__ import annotations

from typing import ClassVar

from homeassistant.core import HomeAssistant

from .....const import SIGN_DISCHARGING_POSITIVE
from ....measure.batteries import BatteryConfig
from ..base import BatteryProfile, device_entities
from .entities import EntityReader


class OmnibatteryReader(EntityReader):
    """Batteries managed by Omnibattery."""

    key = "omnibattery"
    name = "Omnibattery"
    verified = True
    can_write = True
    profile = BatteryProfile(
        platform="omnibattery",
        label="Omnibattery",
        soc="battery_soc",
        power="ac_power",
        power_sign=SIGN_DISCHARGING_POSITIVE,
        capacity=("sensor", "battery_total_energy"),
        max_charge=("number", "max_charge_power"),
        max_discharge=("number", "max_discharge_power"),
        min_soc=("number", "discharging_cutoff_capacity"),
        max_soc=("number", "charging_cutoff_capacity"),
        efficiency=("sensor", "round_trip_efficiency_total"),
        phase=("select", "battery_phase"),
    )
    sensors: ClassVar[dict[str, str]] = {
        "temperature_c": "internal_temperature",
        "voltage_v": "battery_voltage",
        "cell_min_v": "min_cell_voltage",
        "cell_max_v": "max_cell_voltage",
        "cycles": "battery_cycle_count",
        "charged_today_kwh": "total_daily_charging_energy",
        "efficiency_pct": "round_trip_efficiency_total",
        "cell_delta_v": "cell_delta",
    }

    async def async_set_power(
        self, hass: HomeAssistant, config: BatteryConfig, power_w: float
    ) -> None:
        """Manual mode with a charge or discharge power (untested, unused)."""
        entities = device_entities(hass, config)
        manual = entities.get(("switch", "battery_manual_mode"))
        if manual:
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": manual}, blocking=True
            )
        await self._async_number(hass, config, "set_charge_power", max(power_w, 0.0))
        await self._async_number(
            hass, config, "set_discharge_power", max(-power_w, 0.0)
        )

    async def async_release(self, hass: HomeAssistant, config: BatteryConfig) -> None:
        """Back to Omnibattery's own control (untested, unused)."""
        manual = device_entities(hass, config).get(("switch", "battery_manual_mode"))
        if manual:
            await hass.services.async_call(
                "switch", "turn_off", {"entity_id": manual}, blocking=True
            )
