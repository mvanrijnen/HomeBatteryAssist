"""Button entities: recalculate the forecasts by hand."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from ..models import HomeBatteryAssistConfigEntry
from .sensors import HomeBatteryAssistEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeBatteryAssistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    async_add_entities([RecalculateButton(entry)])


class RecalculateButton(HomeBatteryAssistEntity, ButtonEntity):
    """Recalculate HomeBatteryAssist's forecasts now."""

    def __init__(self, entry: HomeBatteryAssistConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "recalculate")
        self._forecast = entry.runtime_data.forecast

    async def async_press(self) -> None:
        """Recalculate."""
        await self._forecast.async_refresh()
