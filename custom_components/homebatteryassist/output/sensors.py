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
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from ..const import DOMAIN, NAME
from ..engine.coordinator import ForecastCoordinator
from ..engine.devices.batteries.control_quality import (
    STATES as CONTROL_QUALITY_STATES,
)
from ..engine.devices.meters import SOURCE_NAMES
from ..engine.explain.plan_phases import KINDS as PHASE_KINDS
from ..engine.explain.plan_phases import current_and_next, phase_attributes
from ..engine.explain.plan_summary import state_text
from ..engine.measure.house_measurement import MeasurementInput, PowerFlow
from ..models import HomeBatteryAssistConfigEntry
from .batteries import (
    BATTERY_SENSORS,
    TOTAL_SENSORS,
    TWIN_SENSOR,
    BatteriesTotalSensor,
    BatterySensor,
    source_device,
)
from .control_test import ControlTestStatus
from .registry_cleanup import tracked

MAX_STATE_LENGTH = 255
RECENT_DECISIONS = 10


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HomeBatteryAssistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors: main device, battery totals and one device per battery."""
    async_add_entities = tracked(entry, async_add_entities, "sensor")
    phases = entry.runtime_data.measurements.phases
    main: list[SensorEntity] = [
        HouseConsumptionSensor(entry),
        *(FlowSensor(entry, description) for description in FLOW_SENSORS),
        *(FlowSensor(entry, phase_load_description(i)) for i in range(phases)),
        ExportLimitSensor(entry),
        PlanningHorizonSensor(entry),
        ConsumptionForecastSensor(entry),
        *(
            ForecastAccuracySensor(entry, kind)
            for kind in ("consumption", "pv", "price")
        ),
        LastDecisionSensor(entry),
    ]
    batteries = entry.runtime_data.batteries
    if any(c.virtual for c in batteries.configs):
        main.append(ControlQualitySensor(entry))
    if batteries.configs:
        main.append(BatteryForecastSensor(entry))
        # The plan as phases: discharging, charging (grid / solar), grid only.
        main += [PlanPhaseSensor(entry, kind) for kind in PHASE_KINDS]
        main.append(PlanSummarySensor(entry))
    if any(not c.virtual for c in batteries.configs):
        main += [
            BatteriesTotalSensor(entry, description, main_device_info(entry))
            for description in TOTAL_SENSORS
        ]
    async_add_entities(main)

    for config in batteries.configs:
        async_add_entities(
            [
                *(
                    BatterySensor(
                        entry, config.id, d, source_device(hass, config.soc_sensor)
                    )
                    for d in BATTERY_SENSORS
                ),
                # A twin: compared with its real battery.
                *(
                    [BatterySensor(entry, config.id, TWIN_SENSOR)]
                    if config.twin_of
                    else []
                ),
                # Its share of the battery phases of the plan.
                *(
                    PlanPhaseSensor(entry, kind, config.id)
                    for kind in PHASE_KINDS
                    if kind != "grid_only"
                ),
                # The test control's status (real batteries).
                *(
                    [ControlTestStatus(entry, config.id)]
                    if config.id in entry.runtime_data.control_test.configs
                    else []
                ),
            ],
            config_subentry_id=config.id,
        )


# Flow sensors on the grid connection device (the rest on the main device).
GRID_KEYS = ("grid_power", "grid_import_power", "grid_export_power")


def grid_device_info(entry: HomeBatteryAssistConfigEntry) -> DeviceInfo:
    """The grid connection: its own device, with the meter as model."""
    measurements = entry.runtime_data.measurements
    direct = measurements.direct is not None
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_grid")},
        translation_key="grid",
        manufacturer=NAME,
        model=SOURCE_NAMES.get(measurements.source) if direct else None,
        model_id=f"{measurements.phases} x {measurements.max_current} A",
        entry_type=DeviceEntryType.SERVICE,
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
        self.async_on_remove(
            self._measurements.async_add_listener(self._updated, entity=True)
        )

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


class ExportLimitSensor(HomeBatteryAssistEntity, SensorEntity):
    """The most that may be exported now (W): 0 = no export, else the limit;
    the grid connection's maximum when not limited. Shown and explained in
    this phase; nothing is sent to an inverter."""

    # Long lists: kept out of the recorder.
    _unrecorded_attributes = frozenset({"expected", "would_send"})

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_should_poll = False

    def __init__(self, entry: HomeBatteryAssistConfigEntry) -> None:
        """Initialize, on the grid connection device."""
        super().__init__(entry, "export_limit")
        self._limiter = entry.runtime_data.export_limit
        self._measurements = entry.runtime_data.measurements
        self._phases = entry.runtime_data.measurements.phases
        self._attr_device_info = grid_device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Follow the limiter."""
        self.async_on_remove(
            self._limiter.async_add_listener(self.async_write_ha_state)
        )

    @property
    def native_value(self) -> float:
        """The limit in W."""
        return round(self._limiter.limit.limit_w)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Why, per phase, the export now and what would be curtailed."""
        limiter = self._limiter
        limit = limiter.limit
        return {
            "limited": limit.limited,
            "reason": limit.reason,
            "max_current_per_phase": round(limit.amps_per_phase(self._phases), 1),
            "export_price": limiter.price,
            "export_limit_price": limiter.threshold if limiter.enabled else None,
            "export_cost": limiter.cost,
            "net_export_price": (
                None
                if limiter.price is None
                else round(limiter.price - limiter.cost, 5)
            ),
            "fixed_limit_w": limiter.fixed_w or None,
            "export_w": None if limiter.export_w is None else round(limiter.export_w),
            "curtailed_w": round(limiter.curtailed_w),
            "curtailed_today_kwh": round(limiter.today_kwh, 3),
            "would_send": limiter.would_send(addresses=False) if limit.limited else [],
            # What the inverters that limit their own output may produce
            # (house + batteries + the export allowed).
            "production_limit_w": (
                None
                if not limit.limited or limiter.production_limit_w is None
                else round(limiter.production_limit_w)
            ),
            # The most that can be exported (not limited): connection,
            # or the sum of the inverter breakers when lower.
            "max_possible_w": round(limiter.connection),
            **limiter.capacity,
            # Coming periods in which export would be limited (plan).
            "expected": [
                {
                    "start": p.start.isoformat(),
                    "end": p.end.isoformat(),
                    "kwh": p.kwh,
                    "lowest_net_price": p.lowest_price,
                }
                for p in limiter.expected
            ],
            # PV the inverters hold back now (possible - measured), when a PV
            # source has a sensor for what it could produce.
            "pv_curtailed_now_w": (
                round(flow.pv_curtailed_w)
                if (flow := self._measurements.flow) is not None
                and flow.pv_possible_w is not None
                else None
            ),
            "controlled": False,
        }


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
        if description.key in GRID_KEYS or description.key.startswith("phase_l"):
            self._attr_device_info = grid_device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Follow updates of the measurements."""
        self.async_on_remove(
            self._measurements.async_add_listener(self._updated, entity=True)
        )

    @callback
    def _updated(self, when: datetime, power: float | None) -> None:
        self.async_write_ha_state()

    def _flow(self) -> PowerFlow | None:
        """Grid and phase loads as the meter sees them (also while a battery
        sensor drops out); PV too while it is known; the rest needs all."""
        m = self._measurements
        key = self.entity_description.key
        if key in GRID_KEYS or key.startswith("phase_l"):
            return m.meter_flow
        if key == "pv_power" and m.pv_known:
            return m.meter_flow
        return m.flow

    @property
    def available(self) -> bool:
        """Unavailable while a measurement it needs is unknown (the grid)."""
        return self._flow() is not None

    @property
    def native_value(self) -> float | None:
        """Return the value."""
        if (flow := self._flow()) is None:
            return None
        value = self.entity_description.value_fn(flow)
        if self.entity_description.native_unit_of_measurement == PERCENTAGE:
            return round(value / self._measurements.max_current * 100, 1)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes, if any."""
        flow = self._flow()
        if self.entity_description.attrs_fn is None or flow is None:
            return None
        return self.entity_description.attrs_fn(flow, self._measurements)


class ControlQualitySensor(HomeBatteryAssistEntity, SensorEntity):
    """How well zero on the meter of the virtual batteries holds the grid
    at its target: stable, oscillating, sluggish or idle (last 10 min)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = True  # the simulator steps every few seconds

    def __init__(self, entry: HomeBatteryAssistConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "control_quality")
        self._entry = entry
        self._attr_options = list(CONTROL_QUALITY_STATES)

    def _summary(self) -> dict[str, Any] | None:
        simulator = self._entry.runtime_data.simulator
        if simulator is None:
            return None
        return simulator.quality.summary(dt_util.utcnow())

    @property
    def native_value(self) -> str | None:
        """The state."""
        summary = self._summary()
        return str(summary["state"]) if summary else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The figures behind it."""
        summary = self._summary() or {}
        return {k: v for k, v in summary.items() if k != "state"}


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


class BatteryForecastSensor(
    HomeBatteryAssistEntity, CoordinatorEntity[ForecastCoordinator], SensorEntity
):
    """Planned battery power now (advice); the whole plan and alternatives in attributes."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _unrecorded_attributes = frozenset({"forecast"})

    def __init__(self, entry: HomeBatteryAssistConfigEntry) -> None:
        """Initialize."""
        CoordinatorEntity.__init__(self, entry.runtime_data.forecast)
        HomeBatteryAssistEntity.__init__(self, entry, "battery_forecast")

    @property
    def native_value(self) -> float | None:
        """Expected battery power in the current slot (+ charging / - discharging)."""
        now = dt_util.utcnow()
        slot = next(
            (s for s in self.coordinator.data.battery if s.start <= now < s.end), None
        )
        return slot.power_w if slot else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The plan per slot, its expected saving and the other modes."""
        data = self.coordinator.data
        slots = data.battery
        plan = data.selected_plan
        return {
            "mode": data.plan_mode,
            "strategy": plan.strategy if plan else None,
            "expected_cost": plan.cost if plan else None,
            "expected_cost_without_battery": plan.cost_without if plan else None,
            "expected_saving": round(plan.saving, 2)
            if plan and plan.saving is not None
            else None,
            "alternatives": {
                mode: round(p.saving, 2) if p.saving is not None else None
                for mode, p in data.plans.items()
                if mode != data.plan_mode
            },
            "soc_end": slots[-1].soc if slots else None,
            "soc_min": min((s.soc for s in slots), default=None),
            "soc_max": max((s.soc for s in slots), default=None),
            "forecast": [
                {
                    "start": s.start.isoformat(),
                    "power_w": s.power_w,
                    "soc": s.soc,
                    "grid_w": s.grid_w,
                }
                for s in slots
            ],
        }


class PlanPhaseSensor(
    HomeBatteryAssistEntity, CoordinatorEntity[ForecastCoordinator], SensorEntity
):
    """One kind of phase of the plan (discharging, charging from the grid,
    charging with solar, grid only): running now, planned or not; the current
    and the next phase (start, end, minutes, kWh, price, reason) in the
    attributes. With ``battery_id``: that battery's share, on its device."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(
        self,
        entry: HomeBatteryAssistConfigEntry,
        kind: str,
        battery_id: str | None = None,
    ) -> None:
        """Initialize."""
        CoordinatorEntity.__init__(self, entry.runtime_data.forecast)
        HomeBatteryAssistEntity.__init__(self, entry, f"phase_{kind}")
        self._attr_options = ["active", "planned", "none"]
        self._kind = kind
        self._battery_id = battery_id
        self._batteries = entry.runtime_data.batteries
        if battery_id is not None:
            self._attr_unique_id = f"{battery_id}_phase_{kind}"
            self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, battery_id)})

    def _phases(self):
        data = self.coordinator.data
        # The planned batteries (a real battery with a twin is not planned).
        configs = [s.config for s in self._batteries.plan_states() if s.soc is not None]
        capacity = sum(c.capacity_kwh for c in configs) or 1.0
        # The floor the plan holds now: the reserve, the night reserve at
        # night, the peak reserve with a peak limit.
        floor = self.coordinator.plan_floor(configs, dt_util.utcnow())
        current, following = current_and_next(
            data.battery,
            self._kind,
            dt_util.utcnow(),
            data.selected_plan.strategy if data.selected_plan else data.plan_mode,
            floor,
            self.hass.config.language if self.hass else None,
            self.hass.config.currency if self.hass else None,
        )
        shares = {c.id: (c.name, c.capacity_kwh / capacity) for c in configs}
        return current, following, shares

    @property
    def native_value(self) -> str:
        """Running now, planned later, or not in the planning window."""
        current, following, shares = self._phases()
        if (
            self._battery_id is not None
            and not shares.get(self._battery_id, ("", 0.0))[1]
        ):
            return "none"  # not planned (e.g. a real battery with a twin)
        return "active" if current else "planned" if following else "none"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The current and the next phase."""
        current, following, shares = self._phases()
        share = 1.0
        if self._battery_id is not None:
            share = shares.get(self._battery_id, ("", 0.0))[1]
            if share <= 0:  # not planned (e.g. a real battery with a twin)
                return {"current_start": None, "next_start": None}
        return {
            **phase_attributes(current, "current_", shares, share),
            **phase_attributes(following, "next_", shares, share),
        }


class PlanSummarySensor(
    HomeBatteryAssistEntity, CoordinatorEntity[ForecastCoordinator], SensorEntity
):
    """The plan at a glance: what the batteries do now and why (state), the
    next change, the plan in one line, the sun, the cheapest price and the
    price thresholds of now (attributes)."""

    # Text that changes with every plan: not worth keeping in the history.
    _unrecorded_attributes = frozenset(
        {
            "now",
            "power",
            "next",
            "plan",
            "sun",
            "cheapest",
            "use_above",
            "charge_below",
        }
    )

    def __init__(self, entry: HomeBatteryAssistConfigEntry) -> None:
        """Initialize."""
        CoordinatorEntity.__init__(self, entry.runtime_data.forecast)
        HomeBatteryAssistEntity.__init__(self, entry, "plan_summary")
        self._batteries = entry.runtime_data.batteries

    def _summary(self) -> dict[str, Any]:
        configs = [s.config for s in self._batteries.plan_states() if s.soc is not None]
        return self.coordinator.plan_summary(configs)

    @property
    def native_value(self) -> str:
        """What the batteries do now, the price now and the thresholds."""
        return state_text(self._summary())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The other lines and the thresholds of now."""
        summary = self._summary()
        return {
            key: summary.get(key)
            for key in (
                "now",
                "power",
                "next",
                "plan",
                "sun",
                "cheapest",
                "use_above",
                "charge_below",
            )
        }


class ForecastAccuracySensor(
    HomeBatteryAssistEntity, CoordinatorEntity[ForecastCoordinator], SensorEntity
):
    """Running mean absolute error of one forecast, per lead time in attributes."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: HomeBatteryAssistConfigEntry, kind: str) -> None:
        """Initialize for ``kind``: consumption, pv or price."""
        CoordinatorEntity.__init__(self, entry.runtime_data.forecast)
        HomeBatteryAssistEntity.__init__(self, entry, f"{kind}_forecast_accuracy")
        self._kind = kind
        # The error of: consumption in W, PV energy per hour in Wh (an error,
        # not a meter reading, so no energy device class), price in its unit.
        if kind == "consumption":
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
        elif kind == "pv":
            self._attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
        else:
            self._attr_suggested_display_precision = 4

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Price errors are in the unit of the price sensor; the last known
        one while the price source gives nothing (a unit dropping away for a
        cycle would stop the long-term statistics)."""
        if self._kind == "price":
            unit = getattr(self.coordinator.data, "price_unit", None)
            if unit:
                self._price_unit = unit
            return getattr(self, "_price_unit", None)
        return self._attr_native_unit_of_measurement

    @property
    def native_value(self) -> float | None:
        """Mean absolute error of the shortest lead time with samples."""
        headline = self.coordinator.accuracy.headline(self._kind)
        if headline is None or headline.mae is None:
            return None
        return round(headline.mae, 4 if self._kind == "price" else 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Mode and running accuracy and correction per lead time."""
        accuracy = self.coordinator.accuracy
        return {
            "mode": accuracy.mode(self._kind, dt_util.utcnow()),
            "manual": accuracy.settings[self._kind]["manual"] or None,
            "manual_until": accuracy.settings[self._kind]["until"],
            "lead_times": accuracy.summary(self._kind),
        }


class LastDecisionSensor(HomeBatteryAssistEntity, SensorEntity):
    """The most recent decision, explained; recent ones in the attributes."""

    # Long lists: kept out of the recorder.
    _unrecorded_attributes = frozenset({"recent"})

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
