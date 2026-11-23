"""Reader: batteries managed by Omnibattery (ffunes/Omnibattery).

Verified for reading with a Marstek Venus E v3 (the command it gives the
battery too: RS485 control mode, force mode and charge/discharge power). ``ac_power`` is the grid side
of the battery: + discharging / - charging. The write methods follow
Omnibattery's entities but are untested and never called.
"""

from __future__ import annotations

from typing import ClassVar

from homeassistant.core import HomeAssistant

from .....const import SIGN_DISCHARGING_POSITIVE
from ....measure.battery_monitor import BatteryConfig
from ..base import BatteryProfile, device_entities
from .entity_reader import EntityReader


class OmnibatteryReader(EntityReader):
    """Batteries managed by Omnibattery."""

    key = "omnibattery"
    name = "Omnibattery"
    verified = True
    can_write = True
    is_meter = True  # ac_power: the battery's own power at its AC side
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
        verified=True,
    )
    sensors: ClassVar[dict[str, str]] = {
        "temperature_c": "internal_temperature",
        "voltage_v": "battery_voltage",
        "cell_min_v": "min_cell_voltage",
        "cell_max_v": "max_cell_voltage",
        "cycles": "battery_cycle_count",
        "charged_today_kwh": "total_daily_charging_energy",
        "discharged_today_kwh": "total_daily_discharging_energy",
        "efficiency_pct": "round_trip_efficiency_total",
        "cell_delta_v": "cell_delta",
    }

    command_entities: ClassVar[dict[str, tuple[str, str]]] = {
        "external": ("switch", "rs485_control_mode"),
        "mode": ("select", "force_mode"),
        "charge": ("number", "set_charge_power"),
        "discharge": ("number", "set_discharge_power"),
        "allow_charge": ("switch", "battery_allow_charge"),
        "allow_discharge": ("switch", "battery_allow_discharge"),
        "hysteresis": ("binary_sensor", "charge_hysteresis_active"),
    }

    async def async_set_power(
        self, hass: HomeAssistant, config: BatteryConfig, power_w: float
    ) -> None:
        """Manual mode with a charge or discharge power (untested, unused).

        Manual mode first: Omnibattery refuses the setpoints while it
        controls the battery itself (tested 2026-11-23). Then the other
        direction to 0 before the new one, so never both. Without the manual
        mode switch nothing is written (an error: the controller releases)."""
        entities = device_entities(hass, config)
        manual = entities.get(("switch", "battery_manual_mode"))
        if not manual:
            raise RuntimeError(f"{config.name}: no manual mode switch")
        charge, discharge = max(power_w, 0.0), max(-power_w, 0.0)
        first, second = (
            (("set_discharge_power", discharge), ("set_charge_power", charge))
            if power_w > 0
            else (("set_charge_power", charge), ("set_discharge_power", discharge))
        )
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": manual}, blocking=True
        )
        await self._async_number(hass, config, *first)
        await self._async_number(hass, config, *second)

    async def async_release(self, hass: HomeAssistant, config: BatteryConfig) -> None:
        """Back to Omnibattery's own control (untested, unused)."""
        manual = device_entities(hass, config).get(("switch", "battery_manual_mode"))
        if manual:
            await hass.services.async_call(
                "switch", "turn_off", {"entity_id": manual}, blocking=True
            )
