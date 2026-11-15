"""Sensor entities of HomeBatteryAssist."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN, NAME
from ..forecasts.coordinator import ForecastCoordinator
from ..models import HomeBatteryAssistConfigEntry

MAX_STATE_LENGTH = 255
RECENT_DECISIONS = 10


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeBatteryAssistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    async_add_entities(
        [
            HouseConsumptionSensor(entry),
            PlanningHorizonSensor(entry),
            LastDecisionSensor(entry),
        ]
    )


class HomeBatteryAssistEntity(Entity):
    """Common base: one service device per config entry."""

    _attr_has_entity_name = True

    def __init__(self, entry: HomeBatteryAssistConfigEntry, key: str) -> None:
        """Initialize."""
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            entry_type=DeviceEntryType.SERVICE,
        )


class HouseConsumptionSensor(HomeBatteryAssistEntity, SensorEntity):
    """House consumption: grid + PV - excluded loads."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_should_poll = False

    def __init__(self, entry: HomeBatteryAssistConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "house_consumption")
        self._measurements = entry.runtime_data.measurements

    async def async_added_to_hass(self) -> None:
        """Follow updates of the measurements."""
        self.async_on_remove(self._measurements.async_add_listener(self._updated))

    @callback
    def _updated(self, when: datetime, power: float | None) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Unavailable while a grid phase measurement is unknown."""
        return self._measurements.power is not None

    @property
    def native_value(self) -> float | None:
        """Return the house consumption in W."""
        return self._measurements.power


class PlanningHorizonSensor(
    HomeBatteryAssistEntity, CoordinatorEntity[ForecastCoordinator], SensorEntity
):
    """Until when the system can plan, given the setting and the forecasts."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: HomeBatteryAssistConfigEntry) -> None:
        """Initialize."""
        CoordinatorEntity.__init__(self, entry.runtime_data.forecast)
        HomeBatteryAssistEntity.__init__(self, entry, "planning_horizon")

    @property
    def native_value(self) -> datetime | None:
        """Return the end of the planning window."""
        return self.coordinator.data.window.end

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose how far ahead we can calculate and what limits it."""
        data = self.coordinator.data
        return {
            "hours_ahead": round(data.window.hours, 1),
            "days_ahead": round(data.window.hours / 24, 2),
            "limited_by": data.window.limited_by.value,
            "max_days": self.coordinator.max_days,
            "price_forecast_end": data.price_end,
            "price_points": len(data.prices),
            "price_unit": data.price_unit,
            "pv_forecast_end": data.pv_end,
            "pv_forecast_hours": len(data.pv_wh),
        }


class LastDecisionSensor(HomeBatteryAssistEntity, SensorEntity):
    """The most recent decision, explained; recent ones in the attributes."""

    _attr_should_poll = False

    def __init__(self, entry: HomeBatteryAssistConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "last_decision")
        self._decisions = entry.runtime_data.decisions

    async def async_added_to_hass(self) -> None:
        """Follow new decisions."""
        self.async_on_remove(
            self._decisions.async_add_listener(self.async_write_ha_state)
        )

    @property
    def native_value(self) -> str | None:
        """Return the explanation of the latest decision."""
        if (latest := self._decisions.latest) is None:
            return None
        return latest["message"][:MAX_STATE_LENGTH]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose details of the latest and a list of recent decisions."""
        latest = self._decisions.latest
        return {
            "time": latest["time"] if latest else None,
            "category": latest["category"] if latest else None,
            "key": latest["key"] if latest else None,
            "recent": [
                {"time": d["time"], "message": d["message"]}
                for d in reversed(self._decisions.entries[-RECENT_DECISIONS:])
            ],
        }
