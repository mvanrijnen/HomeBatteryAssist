"""Live measurements and the resulting house consumption.

house consumption = grid (sum of phases) + PV production - excluded loads
                    - battery power (+ charging / - discharging)

Grid power per phase is either one signed sensor (positive = import, negative =
export) or an import sensor minus an optional separate export (return) sensor.
PV sources and excluded loads are taken as absolute values; battery power is
normalised by ``batteries.battery_power``. The result is never below 0 W.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_MAX_CURRENT,
    CONF_PHASE,
    CONF_PHASES,
    CONF_SENSOR,
    NOMINAL_VOLTAGE,
    PHASE_NONE,
    SUBENTRY_EXCLUDED_LOAD,
    SUBENTRY_PV_SOURCE,
    phase_index,
    phase_return_sensor_keys,
    phase_sensor_keys,
)
from ..explain import DecisionLog
from .batteries import battery_configs, battery_power
from .units import state_to_watts

_LOGGER = logging.getLogger(__name__)

type MeasurementListener = Callable[[datetime, float | None], None]


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
        self.max_current: int = entry.data[CONF_MAX_CURRENT]
        # (import or signed sensor, optional return sensor) per phase
        self.grid_phases: list[tuple[str, str | None]] = [
            (entry.data[key], entry.data.get(return_key) or None)
            for key, return_key in zip(
                phase_sensor_keys(phases), phase_return_sensor_keys(phases), strict=True
            )
        ]
        self.pv_sources = _subentry_devices(entry, SUBENTRY_PV_SOURCE)
        self.excluded_loads = _subentry_devices(entry, SUBENTRY_EXCLUDED_LOAD)
        self.pv_sensors = [sensor for sensor, _ in self.pv_sources]
        self.excluded_sensors = [sensor for sensor, _ in self.excluded_loads]
        self.batteries = battery_configs(entry)

        self.power: float | None = None
        self.flow: PowerFlow | None = None
        self.missing: list[str] = []  # grid sensors without a valid value
        self._was_available: bool | None = None
        self._listeners: list[MeasurementListener] = []
        self._unsub: CALLBACK_TYPE | None = None

    @property
    def source_entity_ids(self) -> list[str]:
        """All sensors the calculation depends on."""
        grid = [e for pair in self.grid_phases for e in pair if e is not None]
        batteries = [b.power_sensor for b in self.batteries]
        return [*grid, *self.pv_sensors, *self.excluded_sensors, *batteries]

    @callback
    def async_start(self) -> None:
        """Start following the source sensors."""
        self._unsub = async_track_state_change_event(
            self.hass, self.source_entity_ids, self._async_state_changed
        )
        _LOGGER.debug("Following %s", self.source_entity_ids)
        self._update(dt_util.utcnow())

    @callback
    def async_stop(self) -> None:
        """Stop following the source sensors."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @callback
    def async_add_listener(self, listener: MeasurementListener) -> CALLBACK_TYPE:
        """Call ``listener(time, power)`` whenever the house consumption changes."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def calculate(self) -> tuple[PowerFlow | None, list[str]]:
        """Compute all power flows and the grid sensors without a value.

        Unknown if any grid measurement is unknown; unknown PV sources,
        excluded loads and batteries count as 0 W.
        """
        phase_w: list[float] = []
        missing: list[str] = []
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
        pv = round(self._sum_abs(self.pv_sensors), 1)
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

        for sensor, phase in self.pv_sources:
            value = abs(self._watts(sensor) or 0.0)
            add(phase_pv, phase, value)
            add(phase_house, phase, value)
        for sensor, phase in self.excluded_loads:
            add(phase_house, phase, -abs(self._watts(sensor) or 0.0))
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


def _subentry_devices(entry: ConfigEntry, subentry_type: str) -> list[tuple[str, str]]:
    """(sensor, phase) of every subentry of the type."""
    return [
        (subentry.data[CONF_SENSOR], subentry.data.get(CONF_PHASE, PHASE_NONE))
        for subentry in entry.subentries.values()
        if subentry.subentry_type == subentry_type
    ]
