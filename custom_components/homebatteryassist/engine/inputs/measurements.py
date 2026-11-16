"""Live measurements and the resulting house consumption.

house consumption = grid (sum of phases) + PV production - excluded loads
                    - battery power (+ charging / - discharging)

Grid power per phase is either one signed sensor (positive = import, negative =
export) or an import sensor minus an optional separate export (return) sensor.
PV sources and excluded loads are taken as absolute values; battery power is
normalised by ``batteries.battery_power``. The result is never below 0 W.

Instead of grid sensors, the grid power per phase can come from a meter that
is read directly about once a second (``direct.py``: HomeWizard P1 API, SMA
Speedwire). Listeners can then ask to be called at most every
``ENTITY_INTERVAL`` (entities), so the recorder does not store a state per
second; the history still gets every value.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from ...const import (
    CONF_DEVICE_PHASE_SENSORS,
    CONF_MAX_CURRENT,
    CONF_METER_ADDRESS,
    CONF_METER_SOURCE,
    CONF_PHASE,
    CONF_PHASES,
    CONF_PV_ADDRESS,
    CONF_PV_DRIVER,
    CONF_SENSOR,
    NOMINAL_VOLTAGE,
    PHASE_NONE,
    PV_DRIVER_SENSOR,
    SUBENTRY_EXCLUDED_LOAD,
    SUBENTRY_PV_SOURCE,
    phase_index,
    phase_return_sensor_keys,
    phase_sensor_keys,
)
from ..batteries.monitor import battery_configs, battery_power
from ..explain import DecisionLog
from ..meters import get_driver as get_meter_driver
from ..meters.direct import DIRECT_SOURCES, SOURCE_SENSORS, DirectMeter, create_meter
from .units import state_to_watts

_LOGGER = logging.getLogger(__name__)

type MeasurementListener = Callable[[datetime, float | None], None]

ENTITY_INTERVAL = timedelta(seconds=10)  # entities with a direct meter


@dataclass(frozen=True, slots=True)
class PowerFlow:
    """All power flows at one moment, in W.

    grid: net over all phases, + import / - export. battery: + charging /
    - discharging. pv, excluded and house are never negative.
    """

    grid_w: float
    pv_w: float
    excluded_w: float
    battery_w: float
    house_w: float
    phase_w: tuple[float, ...]  # net grid power per phase, + import / - export
    # House consumption and PV production per phase (devices without a phase
    # spread evenly), to learn how the consumption is spread over the phases.
    phase_house_w: tuple[float, ...] = ()
    phase_pv_w: tuple[float, ...] = ()

    @property
    def import_w(self) -> float:
        """Power taken from the grid."""
        return max(self.grid_w, 0.0)

    @property
    def export_w(self) -> float:
        """Power returned to the grid."""
        return max(-self.grid_w, 0.0)

    def phase_current(self, index: int) -> float:
        """Absolute current on a phase in A (at nominal voltage)."""
        return abs(self.phase_w[index]) / NOMINAL_VOLTAGE


class MeasurementInput:
    """Tracks the source sensors and computes the house consumption."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, decisions: DecisionLog
    ) -> None:
        """Initialize from the config entry and its subentries."""
        self.hass = hass
        self._decisions = decisions
        phases = entry.data[CONF_PHASES]
        self.phases: int = phases
        self.max_current: int = entry.data[CONF_MAX_CURRENT]
        self.source: str = entry.data.get(CONF_METER_SOURCE, SOURCE_SENSORS)
        self.direct: DirectMeter | None = (
            create_meter(hass, self.source, entry.data[CONF_METER_ADDRESS])
            if self.source in DIRECT_SOURCES
            else None
        )
        # (import or signed sensor, optional return sensor) per phase
        self.grid_phases: list[tuple[str, str | None]] = (
            []
            if self.direct
            else [
                (entry.data[key], entry.data.get(return_key) or None)
                for key, return_key in zip(
                    phase_sensor_keys(phases),
                    phase_return_sensor_keys(phases),
                    strict=True,
                )
            ]
        )
        self._unsub_direct: CALLBACK_TYPE | None = None
        self.pv_sources = _subentry_devices(entry, SUBENTRY_PV_SOURCE)
        self.excluded_loads = _subentry_devices(entry, SUBENTRY_EXCLUDED_LOAD)
        # PV sources read directly by a meter driver (e.g. a kWh meter)
        self.pv_meters: list[tuple[DirectMeter, str]] = []
        for driver_key, address, phase in _pv_meters(entry):
            if (driver := get_meter_driver(driver_key)) is not None:
                self.pv_meters.append((driver.create(hass, address), phase))
        self.pv_sensors = [sensor for sensor, _, _ in self.pv_sources]
        self.excluded_sensors = [sensor for sensor, _, _ in self.excluded_loads]
        # per-phase sensors also trigger a recalculation
        self._phase_device_sensors = [
            s
            for _, _, sensors in (*self.pv_sources, *self.excluded_loads)
            for s in sensors
            if s
        ]
        self.batteries = battery_configs(entry)

        self.power: float | None = None
        self.flow: PowerFlow | None = None
        self.missing: list[str] = []  # grid sensors without a valid value
        self._was_available: bool | None = None
        self._listeners: list[MeasurementListener] = []
        self._pending: dict[int, CALLBACK_TYPE] = {}
        self._unsub: CALLBACK_TYPE | None = None

    @property
    def source_entity_ids(self) -> list[str]:
        """All sensors the calculation depends on."""
        grid = [e for pair in self.grid_phases for e in pair if e is not None]
        batteries = [b.power_sensor for b in self.batteries]
        return [
            *grid,
            *self.pv_sensors,
            *self.excluded_sensors,
            *self._phase_device_sensors,
            *batteries,
        ]

    @callback
    def async_start(self) -> None:
        """Start following the source sensors."""
        self._unsub = async_track_state_change_event(
            self.hass, self.source_entity_ids, self._async_state_changed
        )
        _LOGGER.debug("Following %s", self.source_entity_ids)
        if self.direct is not None:
            self._unsub_direct = self.direct.async_add_listener(self._update)
        self._unsub_pv = [m.async_add_listener(self._update) for m, _ in self.pv_meters]
        self._update(dt_util.utcnow())

    async def async_start_meter(self) -> None:
        """Start reading the direct meters (grid and PV, if any)."""
        if self.direct is not None:
            await self.direct.async_start()
        for meter, _ in self.pv_meters:
            await meter.async_start()

    @callback
    def async_stop(self) -> None:
        """Stop following the source sensors."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self._unsub_direct is not None:
            self._unsub_direct()
            self._unsub_direct = None
        for unsub in getattr(self, "_unsub_pv", []):
            unsub()
        self._unsub_pv = []
        for cancel in self._pending.values():
            cancel()
        self._pending.clear()

    async def async_stop_meter(self) -> None:
        """Stop reading the direct meters (if any)."""
        if self.direct is not None:
            self.direct.cancel_stale()
            await self.direct.async_stop()
        for meter, _ in self.pv_meters:
            meter.cancel_stale()
            await meter.async_stop()

    @callback
    def async_add_listener(
        self, listener: MeasurementListener, *, entity: bool = False
    ) -> CALLBACK_TYPE:
        """Call ``listener(time, power)`` whenever the house consumption changes.

        ``entity``: with a direct meter, at most every ``ENTITY_INTERVAL``
        (and once more with the latest value after a quiet period).
        """
        if entity and self.direct is not None:
            listener = self._throttled(listener)
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _throttled(self, listener: MeasurementListener) -> MeasurementListener:
        key = id(listener)
        last: list[datetime | None] = [None]

        @callback
        def call(when: datetime, power: float | None) -> None:
            if key in self._pending:
                return  # a delayed call follows anyway
            if last[0] is None or when - last[0] >= ENTITY_INTERVAL:
                last[0] = when
                listener(when, power)
                return

            @callback
            def later(_now: datetime) -> None:
                self._pending.pop(key, None)
                last[0] = dt_util.utcnow()
                listener(last[0], self.power)

            delay = (ENTITY_INTERVAL - (when - last[0])).total_seconds()
            self._pending[key] = async_call_later(self.hass, delay, later)

        return call

    def calculate(self) -> tuple[PowerFlow | None, list[str]]:
        """Compute all power flows and the grid sensors without a value.

        Unknown if any grid measurement is unknown; unknown PV sources,
        excluded loads and batteries count as 0 W.
        """
        phase_w: list[float] = []
        missing: list[str] = []
        if self.direct is not None:
            if self.direct.available and self.direct.phase_w:
                phase_w = list(self.direct.phase_w[: self.phases])
            else:
                missing.append(f"{self.direct.label} {self.direct.address}")
        for main, ret in self.grid_phases:
            value = self._watts(main)
            returned = self._watts(ret) if ret is not None else 0.0
            if value is None:
                missing.append(main)
            if returned is None:
                missing.append(ret)  # type: ignore[arg-type]
            if value is not None and returned is not None:
                phase_w.append(round(value - abs(returned), 1))
        if missing:
            return None, missing
        grid = round(sum(phase_w), 1)
        pv = round(
            self._sum_abs(self.pv_sensors)
            + sum(
                abs(sum(m.phase_w))
                for m, _ in self.pv_meters
                if m.available and m.phase_w
            ),
            1,
        )
        excluded = round(self._sum_abs(self.excluded_sensors), 1)
        battery = round(
            sum(battery_power(self.hass, b) or 0.0 for b in self.batteries), 1
        )
        house = max(round(grid + pv - excluded - battery, 1), 0.0)
        count = len(phase_w)
        phase_pv = [0.0] * count
        phase_house = list(phase_w)

        def add(target: list[float], phase: str, value: float) -> None:
            index = phase_index(phase, count)
            for i in range(count) if index is None else (index,):
                target[i] += value / (count if index is None else 1)

        def per_phase(
            sensor: str, phase: str, sensors: tuple[str | None, ...]
        ) -> list[tuple[str, float]]:
            """(phase, W) parts of a device: measured per phase, or its total."""
            if count > 1 and any(sensors):
                return [
                    (f"l{i + 1}", abs(self._watts(s) or 0.0))
                    for i, s in enumerate(sensors[:count])
                    if s
                ]
            return [(phase, abs(self._watts(sensor) or 0.0))]

        for sensor, phase, sensors in self.pv_sources:
            for part, value in per_phase(sensor, phase, sensors):
                add(phase_pv, part, value)
                add(phase_house, part, value)
        for meter, phase in self.pv_meters:
            if not meter.available or not meter.phase_w:
                continue
            values = meter.phase_w
            if count > 1 and len(values) == count:
                parts = [(f"l{i + 1}", abs(v)) for i, v in enumerate(values)]
            else:
                parts = [(phase, abs(sum(values)))]
            for part, value in parts:
                add(phase_pv, part, value)
                add(phase_house, part, value)
        for sensor, phase, sensors in self.excluded_loads:
            for part, value in per_phase(sensor, phase, sensors):
                add(phase_house, part, -value)
        for b in self.batteries:
            add(phase_house, b.phase, -(battery_power(self.hass, b) or 0.0))
        return PowerFlow(
            grid,
            pv,
            excluded,
            battery,
            house,
            tuple(phase_w),
            tuple(round(v, 1) for v in phase_house),
            tuple(round(v, 1) for v in phase_pv),
        ), []

    def _watts(self, entity_id: str) -> float | None:
        return state_to_watts(self.hass.states.get(entity_id))

    def _sum_abs(self, entity_ids: list[str]) -> float:
        values = (self._watts(e) for e in entity_ids)
        return sum(abs(v) for v in values if v is not None)

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        self._update(event.time_fired)

    @callback
    def _update(self, when: datetime) -> None:
        self.flow, self.missing = self.calculate()
        self.power = self.flow.house_w if self.flow else None
        self._explain_availability()
        for listener in list(self._listeners):
            listener(when, self.power)

    def _explain_availability(self) -> None:
        """Record why the consumption became unknown, or that it is back.

        The first state after start-up is not logged: source sensors are often
        still starting then.
        """
        available = self.power is not None
        if self._was_available is not None and available != self._was_available:
            if available:
                self._decisions.async_log("measurement", "consumption_restored")
            else:
                self._decisions.async_log(
                    "measurement",
                    "consumption_unavailable",
                    sensors=", ".join(self.missing),
                )
        if available or self._was_available is not None:
            self._was_available = available


def _subentry_devices(
    entry: ConfigEntry, subentry_type: str
) -> list[tuple[str, str, tuple[str | None, ...]]]:
    """Devices measured by sensors (directly read PV meters: ``_pv_meters``)."""
    return [
        device
        for device, driver, _ in _subentry_devices_all(entry, subentry_type)
        if driver == PV_DRIVER_SENSOR
    ]


def _pv_meters(entry: ConfigEntry) -> list[tuple[str, str, str]]:
    """(driver, address, phase) of PV sources read directly by a meter driver."""
    return [
        (driver, address, device[1])
        for device, driver, address in _subentry_devices_all(entry, SUBENTRY_PV_SOURCE)
        if driver != PV_DRIVER_SENSOR and address
    ]


def _subentry_devices_all(
    entry: ConfigEntry, subentry_type: str
) -> list[tuple[tuple[str, str, tuple[str | None, ...]], str, str]]:
    """(sensor, phase, per-phase sensors) of every subentry of the type.

    A device on one phase has ``phase`` l1-l3; a 3-phase device has phase
    "none" (spread evenly) or, more precisely, a sensor per phase.
    """
    return [
        (
            (
                subentry.data.get(CONF_SENSOR) or "",
                subentry.data.get(CONF_PHASE, PHASE_NONE),
                tuple(
                    subentry.data.get(key) or None for key in CONF_DEVICE_PHASE_SENSORS
                ),
            ),
            subentry.data.get(CONF_PV_DRIVER, PV_DRIVER_SENSOR),
            subentry.data.get(CONF_PV_ADDRESS, ""),
        )
        for subentry in entry.subentries.values()
        if subentry.subentry_type == subentry_type
    ]
