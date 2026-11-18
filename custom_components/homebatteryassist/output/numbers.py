"""Number entities: per real battery the test power and duration of the test
control (switched off in this phase)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from ..models import HomeBatteryAssistConfigEntry
from .control_test import control_test_numbers


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeBatteryAssistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the numbers, on each real battery's device."""
    for battery_id in entry.runtime_data.control_test.configs:
        async_add_entities(
            control_test_numbers(entry, battery_id), config_subentry_id=battery_id
        )
