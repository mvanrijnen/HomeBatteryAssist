"""Sensor entities of HomeBatteryAssist."""

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
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from ..const import DOMAIN, NAME
from ..forecasts.coordinator import ForecastCoordinator
from ..inputs.measurements import MeasurementInput, PowerFlow
from ..models import HomeBatteryAssistConfigEntry
from .batteries import (
    BATTERY_SENSORS,
    TOTAL_SENSORS,
    BatteriesTotalSensor,
    BatterySensor,
    source_device,
)

MAX_STATE_LENGTH = 255
RECENT_DECISIONS = 10


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeBatteryAssistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors: main device, battery totals and one device per battery."""
    phases = len(entry.runtime_data.measurements.grid_phases)
    main: list[SensorEntity] = [
        HouseConsumptionSensor(entry),
        *(FlowSensor(entry, description) for description in FLOW_SENSORS),
        *(FlowSensor(entry, phase_load_description(i)) for i in range(phases)),
        PlanningHorizonSensor(entry),
        ConsumptionForecastSensor(entry),
        ConsumptionForecastAccuracySensor(entry),
        LastDecisionSensor(entry),
    ]
    batteries = entry.runtime_data.batteries
    if batteries.configs:
        main += [
            BatteriesTotalSensor(entry, description, main_device_info(entry))
            for description in TOTAL_SENSORS
        ]
    async_add_entities(main)

    for config in batteries.configs:
        async_add_entities(
            [
                BatterySensor(
                    entry, config.id, d, source_device(hass, config.soc_sensor)
                )
                for d in BATTERY_SENSORS
            ],
            config_subentry_id=config.id,
        )


def main_device_info(entry: HomeBatteryAssistConfigEntry) -> DeviceInfo:
    """The HomeBatteryAssist service device of the config entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=NAME,
        entry_type=DeviceEntryType.SERVICE,
    )


class HomeBatteryAssistEntity(Entity):
    """Common base: one service device per config entry."""

    _attr_has_entity_name = True

    def __init__(self, entry: HomeBatteryAssistConfigEntry, key: str) -> None:
        """Initialize."""
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = main_device_info(entry)


class HouseConsumptionSensor(HomeBatteryAssistEntity, SensorEntity):
    """House consumption: grid + PV - excluded loads - battery charging."""

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


@dataclass(frozen=True, kw_only=True)
class FlowSensorDescription(SensorEntityDescription):
    """A value derived from the current power flows."""

    value_fn: Callable[[PowerFlow], float]
    attrs_fn: Callable[[PowerFlow, MeasurementInput], dict[str, Any]] | None = None


POWER = {
    "device_class": SensorDeviceClass.POWER,
    "state_class": SensorStateClass.MEASUREMENT,
    "native_unit_of_measurement": UnitOfPower.WATT,
}

FLOW_SENSORS: tuple[FlowSensorDescription, ...] = (
    FlowSensorDescription(key="grid_power", value_fn=lambda f: f.grid_w, **POWER),
    FlowSensorDescription(
        key="grid_import_power", value_fn=lambda f: f.import_w, **POWER
    ),
    FlowSensorDescription(
        key="grid_export_power", value_fn=lambda f: f.export_w, **POWER
    ),
    FlowSensorDescription(key="pv_power", value_fn=lambda f: f.pv_w, **POWER),
    FlowSensorDescription(
        key="excluded_power", value_fn=lambda f: f.excluded_w, **POWER
    ),
)


def phase_load_description(index: int) -> FlowSensorDescription:
    """Load of one phase; ``value_fn`` gives A, shown as % of the fuse rating."""
    return FlowSensorDescription(
        key=f"phase_l{index + 1}_load",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda f: f.phase_current(index),
        attrs_fn=lambda f, m: {
            "current": round(f.phase_current(index), 1),
            "power": f.phase_w[index],
            "max_current": m.max_current,
        },
    )


class FlowSensor(HomeBatteryAssistEntity, SensorEntity):
    """Grid, PV, excluded load or phase load, from the current power flows."""

    entity_description: FlowSensorDescription
    _attr_should_poll = False

    def __init__(
        self, entry: HomeBatteryAssistConfigEntry, description: FlowSensorDescription
    ) -> None:
        """Initialize."""
        super().__init__(entry, description.key)
        self.entity_description = description
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
        return self._measurements.flow is not None

    @property
    def native_value(self) -> float | None:
        """Return the value."""
        if (flow := self._measurements.flow) is None:
            return None
        value = self.entity_description.value_fn(flow)
        if self.entity_description.native_unit_of_measurement == PERCENTAGE:
            return round(value / self._measurements.max_current * 100, 1)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes, if any."""
        flow = self._measurements.flow
        if self.entity_description.attrs_fn is None or flow is None:
            return None
        return self.entity_description.attrs_fn(flow, self._measurements)


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
            "price_points_estimated": sum(p.estimated for p in data.prices),
            "published_prices_end": max(
                (p.end for p in data.prices if not p.estimated), default=None
            ),
            "price_unit": data.price_unit,
            "pv_forecast_end": data.pv_end,
            "pv_forecast_hours": len(data.pv_wh),
        }


class ConsumptionForecastSensor(
    HomeBatteryAssistEntity, CoordinatorEntity[ForecastCoordinator], SensorEntity
):
    """Expected house consumption now; the full forecast in the attributes."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    # The forecast list is large and changes every cycle: keep it out of the DB.
    _unrecorded_attributes = frozenset({"forecast", "adjustments"})

    def __init__(self, entry: HomeBatteryAssistConfigEntry) -> None:
        """Initialize."""
        CoordinatorEntity.__init__(self, entry.runtime_data.forecast)
        HomeBatteryAssistEntity.__init__(self, entry, "consumption_forecast")

    @property
    def native_value(self) -> float | None:
        """Expected consumption in the current slot (W)."""
        slot = self.coordinator.data.consumption_at(dt_util.utcnow())
        return slot.power_w if slot else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The forecast per slot, for scripts, automations and charts."""
        data = self.coordinator.data
        slots = data.consumption
        return {
            "method": data.consumption_method,
            "slots": len(slots),
            "total_kwh": round(
                sum(s.power_w * (s.end - s.start).total_seconds() for s in slots)
                / 3_600_000,
                2,
            ),
            "adjustments": [dict(a) for a in self.coordinator.adjustments.items],
            "forecast": [
                {
                    "start": s.start.isoformat(),
                    "end": s.end.isoformat(),
                    "power_w": s.power_w,
                    **(
                        {"base_w": s.base_w, "adjusted_by": list(s.adjustments)}
                        if s.adjustments
                        else {}
                    ),
                }
                for s in slots
            ],
        }


class ConsumptionForecastAccuracySensor(
    HomeBatteryAssistEntity, CoordinatorEntity[ForecastCoordinator], SensorEntity
):
    """Mean absolute error of the consumption forecast over the last 7 days."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: HomeBatteryAssistConfigEntry) -> None:
        """Initialize."""
        CoordinatorEntity.__init__(self, entry.runtime_data.forecast)
        HomeBatteryAssistEntity.__init__(self, entry, "consumption_forecast_accuracy")

    @property
    def native_value(self) -> float | None:
        """Mean absolute error (W) of the latest predictions."""
        return self.coordinator.verification.summary(dt_util.utcnow())["latest"][
            "mae_w"
        ]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Bias, MAPE and the day-ahead accuracy."""
        summary = self.coordinator.verification.summary(dt_util.utcnow())
        latest, day_ahead = summary["latest"], summary["day_ahead"]
        return {
            "period_days": summary["period_days"],
            "samples": latest["samples"],
            "bias_w": latest["bias_w"],
            "mape": latest["mape"],
            "day_ahead_mae_w": day_ahead["mae_w"],
            "day_ahead_bias_w": day_ahead["bias_w"],
            "day_ahead_mape": day_ahead["mape"],
            "day_ahead_samples": day_ahead["samples"],
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
