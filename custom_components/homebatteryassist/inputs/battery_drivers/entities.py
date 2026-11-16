"""Battery drivers that read (and could write) a battery through its entities.

Omnibattery and Marstek Modbus expose every battery as a device with sensors,
numbers, selects and switches. The translation keys below were verified on a
real installation (Marstek Venus E v3) for reading. The write methods follow
the entities those integrations offer, but are untested and **never called by
HomeBatteryAssist** while it is read-only.
"""

from __future__ import annotations

from typing import ClassVar

from homeassistant.core import HomeAssistant

from ..batteries import BatteryConfig
from ..units import parse_float
from .base import BatteryDriver, BatteryTelemetry, device_entities

TELEMETRY_FIELDS = (
    "temperature_c",
    "voltage_v",
    "cell_min_v",
    "cell_max_v",
    "cycles",
    "charged_today_kwh",
    "discharged_today_kwh",
    "efficiency_pct",
)


class EntityBatteryDriver(BatteryDriver):
    """Reads telemetry from sensors on the battery's device, by translation key."""

    # telemetry field -> translation key of a sensor on the battery's device
    sensors: ClassVar[dict[str, str]] = {}

    def telemetry(self, hass: HomeAssistant, config: BatteryConfig) -> BatteryTelemetry:
        """Values of the mapped sensors that have a number."""
        entities = device_entities(hass, config)
        values: dict[str, float] = {}
        for name, key in self.sensors.items():
            entity_id = entities.get(("sensor", key))
            state = hass.states.get(entity_id) if entity_id else None
            value = parse_float(state.state) if state else None
            if value is not None:
                values[name] = value
        return BatteryTelemetry(
            **{k: values.get(k) for k in TELEMETRY_FIELDS},
            extra={k: v for k, v in values.items() if k not in TELEMETRY_FIELDS},
        )

    async def _async_number(
        self, hass: HomeAssistant, config: BatteryConfig, key: str, value: float
    ) -> None:
        entity_id = device_entities(hass, config).get(("number", key))
        if entity_id is None:
            raise ValueError(f"no number entity {key} for {config.name}")
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=True,
        )


class OmnibatteryDriver(EntityBatteryDriver):
    """Batteries managed by Omnibattery (ffunes/Omnibattery)."""

    key = "omnibattery"
    name = "Omnibattery"
    verified = True
    can_write = True
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


class MarstekModbusDriver(EntityBatteryDriver):
    """Marstek batteries through Marstek Modbus (ViperRNMC/marstek_venus_modbus)."""

    key = "marstek_modbus"
    name = "Marstek Modbus"
    verified = True
    can_write = True
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
