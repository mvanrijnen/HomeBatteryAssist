"""Common reader for integrations that expose a battery as a device with
sensors: telemetry by translation key, and writing through number entities
(never called while HomeBatteryAssist is read-only)."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.core import HomeAssistant

from ....measure.battery_monitor import BatteryConfig
from ....units import parse_float
from ..base import BatteryCommand, BatteryReader, BatteryTelemetry, device_entities

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
    # The command the battery has now, by (domain, translation key) on its
    # device: ``external`` (switch: external control on), ``mode`` (select:
    # none / charge / discharge), ``charge`` / ``discharge`` (number, W);
    # optional ``allow_charge`` / ``allow_discharge`` (switch) and
    # ``hysteresis`` (binary sensor: charging held back after full).
    command_entities: ClassVar[dict[str, tuple[str, str]]] = {}

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

    def command(
        self, hass: HomeAssistant, config: BatteryConfig
    ) -> BatteryCommand | None:
        """The forced charge / discharge the battery has now, if any."""
        keys = self.command_entities
        if not all(k in keys for k in ("external", "mode", "charge", "discharge")):
            return None
        entities = device_entities(hass, config)

        def state(name: str) -> str | None:
            entity_id = entities.get(keys[name]) if name in keys else None
            value = hass.states.get(entity_id) if entity_id else None
            if value is None or value.state in ("unknown", "unavailable"):
                return None
            return value.state

        if state("external") != "on":
            return None  # the battery controls itself
        mode = (state("mode") or "").lower()
        if mode == "charge":
            power = parse_float(state("charge"))
        elif mode == "discharge":
            power = parse_float(state("discharge"))
            power = -power if power is not None else None
        elif mode in ("none", "stop", "idle"):
            power = 0.0
        else:
            return None
        if power is None:
            return None
        return BatteryCommand(
            power_w=power,
            charge_allowed=state("allow_charge") != "off",
            discharge_allowed=state("allow_discharge") != "off",
            hysteresis=state("hysteresis") == "on",
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
