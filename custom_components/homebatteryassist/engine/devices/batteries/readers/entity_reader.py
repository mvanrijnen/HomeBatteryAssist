"""Common reader for integrations that expose a battery as a device with
sensors: telemetry by translation key, and writing through number entities
(never called while HomeBatteryAssist is read-only)."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.core import HomeAssistant

from ....measure.battery_monitor import BatteryConfig
from ....units import parse_float
from ..base import BatteryReader, BatteryTelemetry, device_entities

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


class EntityReader(BatteryReader):
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
