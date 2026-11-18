"""Binary sensors: per real battery, whether it does not follow its command."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from ..const import DOMAIN
from ..models import HomeBatteryAssistConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeBatteryAssistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """One problem sensor per real battery (on its device)."""
    commands = entry.runtime_data.commands
    if commands is None:
        return
    for battery_id in commands.checks:
        # On the battery's device, which belongs to its subentry.
        async_add_entities(
            [BatteryCommandProblem(entry, battery_id)],
            config_subentry_id=battery_id,
        )


class BatteryCommandProblem(BinarySensorEntity):
    """On while the battery does not follow its command and that is not
    explainable (full, empty, switched off, hysteresis)."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "battery_not_following"

    def __init__(self, entry: HomeBatteryAssistConfigEntry, battery_id: str) -> None:
        """Initialize."""
        self._commands = entry.runtime_data.commands
        self._battery_id = battery_id
        self._attr_unique_id = f"{battery_id}_battery_not_following"
        # The battery's device (created with its sensors).
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, battery_id)})

    async def async_added_to_hass(self) -> None:
        """Follow every look of the check."""
        self.async_on_remove(
            self._commands.async_add_listener(self.async_write_ha_state)
        )

    @property
    def is_on(self) -> bool:
        """A problem: not following, not explainable."""
        return self._commands.checks[self._battery_id].problem

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The command, the power, and since when / why not followed."""
        state = self._commands.checks[self._battery_id].as_dict()
        return {
            "command_power": state["command_w"],
            "battery_power": state["actual_w"],
            "not_following": state["not_following"],
            "reason": state["reason"],
            "since": state["since"],
        }
