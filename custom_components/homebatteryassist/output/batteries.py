"""Battery sensors: one device per battery, plus totals over all batteries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from ..inputs.batteries import BatteryInput, BatteryState, BatteryStatus
from ..models import HomeBatteryAssistConfigEntry


@dataclass(frozen=True, kw_only=True)
class BatterySensorDescription(SensorEntityDescription):
    """A sensor of one battery."""

    value_fn: Callable[[BatteryInput, BatteryState], Any]
    attrs_fn: Callable[[BatteryInput, BatteryState], dict[str, Any]] | None = None


def _stat(key: str) -> Callable[[BatteryInput, BatteryState], Any]:
    return lambda batteries, state: batteries.stats[state.config.id][key]


def _last_full(batteries: BatteryInput, state: BatteryState) -> datetime | None:
    last = batteries.stats[state.config.id]["last_full_charge"]
    return dt_util.parse_datetime(last) if last else None


def _status_attrs(batteries: BatteryInput, state: BatteryState) -> dict[str, Any]:
    config = state.config
    return {
        "capacity_kwh": config.capacity_kwh,
        "max_charge_power": config.max_charge_w,
        "max_discharge_power": config.max_discharge_w,
        "min_soc": config.min_soc,
        "max_soc": config.max_soc,
        "round_trip_efficiency": round(config.efficiency * 100),
        "phase": config.phase,
    }


def _full_charge_attrs(batteries: BatteryInput, state: BatteryState) -> dict[str, Any]:
    now = dt_util.utcnow()
    due = batteries.full_charge_due(state.config.id, now)
    return {
        "interval_days": state.config.full_charge_interval_days,
        "next_due": due,
        "due": due is not None and due <= now,
    }


ENERGY_STORAGE = {
    "device_class": SensorDeviceClass.ENERGY_STORAGE,
    "state_class": SensorStateClass.MEASUREMENT,
    "native_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
    "suggested_display_precision": 2,
}
ENERGY_TOTAL = {
    "device_class": SensorDeviceClass.ENERGY,
    "state_class": SensorStateClass.TOTAL_INCREASING,
    "native_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
    "suggested_display_precision": 2,
}

BATTERY_SENSORS: tuple[BatterySensorDescription, ...] = (
    BatterySensorDescription(
        key="battery_soc",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda b, s: s.soc,
    ),
    BatterySensorDescription(
        key="battery_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda b, s: s.power_w,
    ),
    BatterySensorDescription(
        key="battery_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in BatteryStatus],
        value_fn=lambda b, s: s.status.value if s.status else None,
        attrs_fn=_status_attrs,
    ),
    BatterySensorDescription(
        key="battery_stored_energy",
        value_fn=lambda b, s: s.stored_kwh,
        **ENERGY_STORAGE,
    ),
    BatterySensorDescription(
        key="battery_usable_energy",
        value_fn=lambda b, s: s.usable_kwh,
        **ENERGY_STORAGE,
    ),
    BatterySensorDescription(
        key="battery_room", value_fn=lambda b, s: s.room_kwh, **ENERGY_STORAGE
    ),
    BatterySensorDescription(
        key="battery_time_to_target",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda b, s: s.time_to_target(dt_util.utcnow()),
    ),
    BatterySensorDescription(
        key="battery_charged_energy", value_fn=_stat("charged_kwh"), **ENERGY_TOTAL
    ),
    BatterySensorDescription(
        key="battery_discharged_energy",
        value_fn=_stat("discharged_kwh"),
        **ENERGY_TOTAL,
    ),
    BatterySensorDescription(
        key="battery_last_full_charge",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_full,
        attrs_fn=_full_charge_attrs,
    ),
    BatterySensorDescription(
        key="battery_capacity",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b, s: s.config.capacity_kwh,
        **ENERGY_STORAGE,
    ),
)
# Values that are always known (configuration or persisted counters).
ALWAYS_AVAILABLE = {
    "battery_capacity",
    "battery_charged_energy",
    "battery_discharged_energy",
    "battery_last_full_charge",
}


@dataclass(frozen=True, kw_only=True)
class BatteriesTotalDescription(SensorEntityDescription):
    """A sensor over all batteries."""

    value_fn: Callable[[list[BatteryState]], Any]


def _sum(values: list[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return round(sum(known), 3) if known else None


def _weighted_soc(states: list[BatteryState]) -> float | None:
    known = [s for s in states if s.soc is not None]
    capacity = sum(s.config.capacity_kwh for s in known)
    if not capacity:
        return None
    return round(sum(s.soc * s.config.capacity_kwh for s in known) / capacity, 1)  # type: ignore[operator]


TOTAL_SENSORS: tuple[BatteriesTotalDescription, ...] = (
    BatteriesTotalDescription(
        key="batteries_soc",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_weighted_soc,
    ),
    BatteriesTotalDescription(
        key="batteries_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda states: _sum([s.power_w for s in states]),
    ),
    BatteriesTotalDescription(
        key="batteries_stored_energy",
        value_fn=lambda states: _sum([s.stored_kwh for s in states]),
        **ENERGY_STORAGE,
    ),
    BatteriesTotalDescription(
        key="batteries_usable_energy",
        value_fn=lambda states: _sum([s.usable_kwh for s in states]),
        **ENERGY_STORAGE,
    ),
    BatteriesTotalDescription(
        key="batteries_capacity",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda states: _sum([s.config.capacity_kwh for s in states]),
        **ENERGY_STORAGE,
    ),
)


class _BatteryEntityBase(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, batteries: BatteryInput) -> None:
        self._batteries = batteries

    async def async_added_to_hass(self) -> None:
        """Follow battery updates."""
        self.async_on_remove(
            self._batteries.async_add_listener(self.async_write_ha_state)
        )


class BatterySensor(_BatteryEntityBase):
    """One value of one battery; each battery is its own device (per subentry)."""

    entity_description: BatterySensorDescription

    def __init__(
        self,
        entry: HomeBatteryAssistConfigEntry,
        battery_id: str,
        description: BatterySensorDescription,
    ) -> None:
        """Initialize."""
        super().__init__(entry.runtime_data.batteries)
        self.entity_description = description
        self._battery_id = battery_id
        self._attr_translation_key = description.key
        self._attr_unique_id = f"{battery_id}_{description.key}"
        name = self._state.config.name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, battery_id)},
            name=name,
            model="Home battery",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _state(self) -> BatteryState:
        return self._batteries.states[self._battery_id]

    @property
    def available(self) -> bool:
        """Live values need the battery's sensors."""
        return self.entity_description.key in ALWAYS_AVAILABLE or self._state.available

    @property
    def native_value(self) -> Any:
        """Return the value."""
        return self.entity_description.value_fn(self._batteries, self._state)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes, if any."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self._batteries, self._state)


class BatteriesTotalSensor(_BatteryEntityBase):
    """A total over all batteries, on the main device."""

    entity_description: BatteriesTotalDescription

    def __init__(
        self,
        entry: HomeBatteryAssistConfigEntry,
        description: BatteriesTotalDescription,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize."""
        super().__init__(entry.runtime_data.batteries)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> Any:
        """Return the total."""
        return self.entity_description.value_fn(list(self._batteries.states.values()))
