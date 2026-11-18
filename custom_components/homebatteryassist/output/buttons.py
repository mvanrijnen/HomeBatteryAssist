"""Button entities: recalculate the forecasts by hand, and per real battery
the test control (switched off in this phase)."""

from __future__ import annotations

import asyncio

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from ..const import DOMAIN
from ..engine.devices.meters import SOURCE_NAMES
from ..engine.explain.input_report import input_report
from ..models import HomeBatteryAssistConfigEntry
from .control_test import control_test_buttons
from .sensors import HomeBatteryAssistEntity, grid_device_info

TEST_SECONDS = 10


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeBatteryAssistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    async_add_entities([RecalculateButton(entry), InputTestButton(entry)])
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


class InputTestButton(HomeBatteryAssistEntity, ButtonEntity):
    """Test the inputs: listen to the grid meter for a few seconds, then show
    everything that is read (a persistent notification)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: HomeBatteryAssistConfigEntry) -> None:
        """Initialize, on the grid connection device."""
        super().__init__(entry, "input_test")
        self._attr_device_info = grid_device_info(entry)
        self._entry = entry
        self._running = False

    async def async_press(self) -> None:
        """Start the test; the report follows after ``TEST_SECONDS``."""
        if not self._running:
            self._running = True
            self._entry.async_create_background_task(
                self.hass, self._async_run(), "homebatteryassist_input_test"
            )

    async def _async_run(self) -> None:
        data = self._entry.runtime_data
        measurements = data.measurements
        updates = 0
        last = None

        @callback
        def _measured(when, _power) -> None:
            nonlocal updates, last
            updates += 1
            last = when

        direct = measurements.direct
        before = direct.count if direct is not None else 0
        unsub = measurements.async_add_listener(_measured)
        try:
            await asyncio.sleep(TEST_SECONDS)
        finally:
            unsub()
            self._running = False
        if direct is not None:
            # Every value the meter sent (not only the ones that changed).
            updates, last = direct.count - before, direct.updated
        title, message = input_report(
            self.hass,
            measurements,
            SOURCE_NAMES.get(measurements.source, measurements.source),
            TEST_SECONDS,
            updates,
            last,
            list(data.batteries.states.values()),
        )
        persistent_notification.async_create(
            self.hass, message, title, f"{DOMAIN}_input_test"
        )
