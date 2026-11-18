"""Test control entities per real battery (on its device): buttons to start
charging / discharging and to stop, the test power and duration, and the
status. While the test control is switched off (``CONTROL_TEST_ALLOWED``)
the buttons only tell *Why* so; nothing is sent."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory, UnitOfPower, UnitOfTime
from homeassistant.helpers.device_registry import DeviceInfo

from ..const import DOMAIN
from ..engine.control.control_test import STATUSES, ControlTest
from ..models import HomeBatteryAssistConfigEntry


class _TestEntity:
    """On the battery's device (created with its sensors)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def _setup(
        self, entry: HomeBatteryAssistConfigEntry, battery_id: str, key: str
    ) -> None:
        self._test: ControlTest = entry.runtime_data.control_test
        self._battery_id = battery_id
        self._attr_translation_key = key
        self._attr_unique_id = f"{battery_id}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, battery_id)})


class ControlTestButton(_TestEntity, ButtonEntity):
    """Test: charge / discharge / stop."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, entry: HomeBatteryAssistConfigEntry, battery_id: str, action: str
    ) -> None:
        """``action``: charge, discharge or stop."""
        self._setup(entry, battery_id, f"control_test_{action}")
        self._action = action

    async def async_press(self) -> None:
        """Start or stop the test."""
        if self._action == "stop":
            await self._test.async_stop(self._battery_id, "stopped")
        else:
            await self._test.async_start(self._battery_id, self._action == "charge")


class ControlTestNumber(_TestEntity, RestoreNumber):
    """The test power (W) or duration (min)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        entry: HomeBatteryAssistConfigEntry,
        battery_id: str,
        key: str,
        maximum: float,
    ) -> None:
        """``key``: control_test_power or control_test_minutes."""
        self._setup(entry, battery_id, key)
        self._values = (
            self._test.power_w if key == "control_test_power" else self._test.minutes
        )
        if key == "control_test_power":
            self._attr_native_min_value = 50
            self._attr_native_step = 50
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
        else:
            self._attr_native_min_value = 1
            self._attr_native_step = 1
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_native_max_value = maximum

    async def async_added_to_hass(self) -> None:
        """Restore the last value."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            value = min(
                max(last.native_value, self.native_min_value), self.native_max_value
            )
            self._values[self._battery_id] = value

    @property
    def native_value(self) -> float:
        """The value."""
        return self._values[self._battery_id]

    async def async_set_native_value(self, value: float) -> None:
        """Set the value (used by the next test)."""
        self._values[self._battery_id] = value
        self.async_write_ha_state()


class ControlTestStatus(_TestEntity, SensorEntity):
    """What the test control of the battery can do / does now."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: HomeBatteryAssistConfigEntry, battery_id: str) -> None:
        """Initialize."""
        self._setup(entry, battery_id, "control_test_status")
        self._attr_options = list(STATUSES)

    async def async_added_to_hass(self) -> None:
        """Follow tests starting and stopping."""
        self.async_on_remove(self._test.async_add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> str:
        """The status."""
        return self._test.status(self._battery_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The test settings and the running test."""
        return self._test.details(self._battery_id)


def control_test_buttons(entry: HomeBatteryAssistConfigEntry, battery_id: str) -> list:
    """The three buttons of a battery."""
    return [
        ControlTestButton(entry, battery_id, action)
        for action in ("charge", "discharge", "stop")
    ]


def control_test_numbers(entry: HomeBatteryAssistConfigEntry, battery_id: str) -> list:
    """The test power (up to the battery's max power) and duration."""
    config = entry.runtime_data.control_test.configs[battery_id]
    return [
        ControlTestNumber(
            entry,
            battery_id,
            "control_test_power",
            max(config.max_charge_w, config.max_discharge_w, 50),
        ),
        ControlTestNumber(entry, battery_id, "control_test_minutes", 30),
    ]
