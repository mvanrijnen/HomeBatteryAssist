"""Button entities: recalculate the forecasts by hand, and per real battery
the test control (switched off in this phase)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from ..models import HomeBatteryAssistConfigEntry
from .control_test import control_test_buttons
from .sensors import HomeBatteryAssistEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeBatteryAssistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    async_add_entities([RecalculateButton(entry)])
    for battery_id in entry.runtime_data.control_test.configs:
        async_add_entities(
            control_test_buttons(entry, battery_id), config_subentry_id=battery_id
        )


class RecalculateButton(HomeBatteryAssistEntity, ButtonEntity):
    """Recalculate HomeBatteryAssist's forecasts now."""

    def __init__(self, entry: HomeBatteryAssistConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "recalculate")
        self._forecast = entry.runtime_data.forecast

    async def async_press(self) -> None:
        """Recalculate; the plan is told in *Why* again, also unchanged."""
        self._forecast.explain_next = True
        await self._forecast.async_refresh()
