"""Reader: Marstek batteries through Marstek Modbus (ViperRNMC/marstek_venus_modbus).

Entity keys verified for reading. The write methods are untested and never
called.
"""

from __future__ import annotations

from typing import ClassVar

from homeassistant.core import HomeAssistant

from .....const import SIGN_DISCHARGING_POSITIVE
from ....measure.batteries import BatteryConfig
from ..base import BatteryProfile, device_entities
from .entities import EntityReader


class MarstekModbusReader(EntityReader):
    """Marstek batteries through Marstek Modbus."""

    key = "marstek_modbus"
    name = "Marstek Modbus"
    verified = True
    can_write = True
    profile = BatteryProfile(
        platform="marstek_modbus",
        label="Marstek Modbus",
        soc="battery_soc",
        power="ac_power",
        power_sign=SIGN_DISCHARGING_POSITIVE,
        capacity=("sensor", "battery_rated_capacity"),
        max_charge=("number", "max_charge_power"),
        max_discharge=("number", "max_discharge_power"),
        efficiency=("sensor", "round_trip_efficiency_total"),
    )
    sensors: ClassVar[dict[str, str]] = {
        "temperature_c": "max_cell_temperature",
        "voltage_v": "battery_voltage",
        "cell_min_v": "min_cell_voltage",
        "cell_max_v": "max_cell_voltage",
        "cycles": "battery_cycle_count",
        "charged_today_kwh": "total_daily_charging_energy",
        "discharged_today_kwh": "total_daily_discharging_energy",
        "efficiency_pct": "round_trip_efficiency_total",
    }

    async def async_set_power(
        self, hass: HomeAssistant, config: BatteryConfig, power_w: float
    ) -> None:
        """Forced charge / discharge at a power (untested, unused)."""
        entities = device_entities(hass, config)
        mode = entities.get(("select", "force_mode"))
        if power_w > 0:
            await self._async_number(hass, config, "set_charge_power", power_w)
        elif power_w < 0:
            await self._async_number(hass, config, "set_discharge_power", -power_w)
        if mode:
            option = "charge" if power_w > 0 else "discharge" if power_w < 0 else "none"
            await hass.services.async_call(
                "select",
                "select_option",
                {"entity_id": mode, "option": option},
                blocking=True,
            )

    async def async_release(self, hass: HomeAssistant, config: BatteryConfig) -> None:
        """No forced mode (untested, unused)."""
        await self.async_set_power(hass, config, 0.0)
