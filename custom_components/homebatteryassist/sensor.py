"""Sensors for HomeBatteryAssist."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .forecast import ForecastCoordinator
from .models import HomeBatteryAssistConfigEntry


def _device_info(entry: HomeBatteryAssistConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=NAME,
        entry_type=DeviceEntryType.SERVICE,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeBatteryAssistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    async_add_entities([HouseConsumptionSensor(entry), PlanningHorizonSensor(entry)])


class HouseConsumptionSensor(SensorEntity):
    """House consumption: grid + PV - excluded loads."""

    _attr_has_entity_name = True
    _attr_translation_key = "house_consumption"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_should_poll = False

    def __init__(self, entry: HomeBatteryAssistConfigEntry) -> None:
        """Initialize."""
        self._consumption = entry.runtime_data.consumption
        self._attr_unique_id = f"{entry.entry_id}_house_consumption"
        self._attr_device_info = _device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Follow updates of the consumption calculation."""
        self.async_on_remove(
            self._consumption.async_add_listener(self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        """Unavailable while a grid phase measurement is unknown."""
        return self._consumption.power is not None

    @property
    def native_value(self) -> float | None:
        """Return the house consumption in W."""
        return self._consumption.power


class PlanningHorizonSensor(CoordinatorEntity[ForecastCoordinator], SensorEntity):
    """Until when the system can plan, given the setting and the forecasts."""

    _attr_has_entity_name = True
    _attr_translation_key = "planning_horizon"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: HomeBatteryAssistConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry.runtime_data.forecast)
        self._attr_unique_id = f"{entry.entry_id}_planning_horizon"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> datetime | None:
        """Return the end of the effective planning horizon."""
        return self.coordinator.data.horizon_end

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the inputs that limit the horizon."""
        data = self.coordinator.data
        return {
            "max_days": self.coordinator.max_days,
            "price_forecast_end": data.price_end,
            "price_points": len(data.prices),
            "price_unit": data.price_unit,
            "pv_forecast_end": data.pv_end,
            "pv_forecast_hours": len(data.pv_wh),
        }
