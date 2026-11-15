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
    CONF_PHASES,
    CONF_SENSOR,
    SUBENTRY_EXCLUDED_LOAD,
    SUBENTRY_PV_SOURCE,
    phase_return_sensor_keys,
    phase_sensor_keys,
)
from ..explain import DecisionLog
from .batteries import battery_configs, battery_power
from .units import state_to_watts

_LOGGER = logging.getLogger(__name__)

type MeasurementListener = Callable[[datetime, float | None], None]


class MeasurementInput:
    """Tracks the source sensors and computes the house consumption."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, decisions: DecisionLog
    ) -> None:
        """Initialize from the config entry and its subentries."""
        self.hass = hass
        self._decisions = decisions
        phases = entry.data[CONF_PHASES]
        # (import or signed sensor, optional return sensor) per phase
        self.grid_phases: list[tuple[str, str | None]] = [
            (entry.data[key], entry.data.get(return_key) or None)
            for key, return_key in zip(
                phase_sensor_keys(phases), phase_return_sensor_keys(phases), strict=True
            )
        ]
        self.pv_sensors = _subentry_sensors(entry, SUBENTRY_PV_SOURCE)
        self.excluded_sensors = _subentry_sensors(entry, SUBENTRY_EXCLUDED_LOAD)
        self.batteries = battery_configs(entry)

        self.power: float | None = None
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

    def calculate(self) -> tuple[float | None, list[str]]:
        """Compute house consumption in W and the grid sensors without a value.

        Unknown if any grid measurement is unknown; unknown PV sources,
        excluded loads and batteries count as 0 W.
        """
        grid = 0.0
        missing: list[str] = []
        for main, ret in self.grid_phases:
            value = self._watts(main)
            returned = self._watts(ret) if ret is not None else 0.0
            if value is None:
                missing.append(main)
            if returned is None:
                missing.append(ret)  # type: ignore[arg-type]
            if value is not None and returned is not None:
                grid += value - abs(returned)
        if missing:
            return None, missing
        pv = self._sum_abs(self.pv_sensors)
        excluded = self._sum_abs(self.excluded_sensors)
        charging = sum(battery_power(self.hass, b) or 0.0 for b in self.batteries)
        return max(round(grid + pv - excluded - charging, 1), 0.0), []

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
        self.power, self.missing = self.calculate()
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


def _subentry_sensors(entry: ConfigEntry, subentry_type: str) -> list[str]:
    return [
        subentry.data[CONF_SENSOR]
        for subentry in entry.subentries.values()
        if subentry.subentry_type == subentry_type
    ]
