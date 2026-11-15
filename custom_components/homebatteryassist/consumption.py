"""House consumption calculation.

house consumption = grid (sum of phases) + PV production - excluded loads

Grid power per phase is either one signed sensor (positive = import, negative =
export) or an import sensor minus an optional separate export (return) sensor.
PV sources and excluded loads are taken as absolute values. Current (A) sensors
are converted to power with ``NOMINAL_VOLTAGE``. The result is never below 0 W.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfElectricCurrent,
    UnitOfPower,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_utc_time_change,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import PowerConverter

from .const import (
    CONF_HISTORY_INTERVAL,
    CONF_PHASES,
    CONF_SENSOR,
    DEFAULT_HISTORY_INTERVAL,
    NOMINAL_VOLTAGE,
    SUBENTRY_EXCLUDED_LOAD,
    SUBENTRY_PV_SOURCE,
    phase_return_sensor_keys,
    phase_sensor_keys,
)
from .history import ConsumptionHistory

_CURRENT_TO_AMPERE = {
    UnitOfElectricCurrent.AMPERE: 1.0,
    UnitOfElectricCurrent.MILLIAMPERE: 0.001,
}


def state_to_watts(state: State | None) -> float | None:
    """Return the state of a power or current sensor in W, or None if unusable."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    try:
        value = float(state.state)
    except ValueError:
        return None

    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    if unit in _CURRENT_TO_AMPERE:
        return value * _CURRENT_TO_AMPERE[unit] * NOMINAL_VOLTAGE
    if unit not in PowerConverter.VALID_UNITS:
        return None
    try:
        return PowerConverter.convert(value, unit, UnitOfPower.WATT)
    except HomeAssistantError:
        return None


class HouseConsumption:
    """Tracks the source sensors, computes house consumption and records it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize from the config entry and its subentries."""
        self.hass = hass
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
        minutes = entry.options.get(CONF_HISTORY_INTERVAL, DEFAULT_HISTORY_INTERVAL)
        self.history = ConsumptionHistory(hass, entry.entry_id, minutes)

        self.power: float | None = None
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[CALLBACK_TYPE] = []

    async def async_start(self) -> None:
        """Load history and start listening to sensors and interval boundaries."""
        await self.history.async_load()
        self._unsubs.append(
            async_track_state_change_event(
                self.hass,
                self.source_entity_ids,
                self._async_state_changed,
            )
        )
        minute = "/" + str(self.history.minutes) if self.history.minutes < 60 else 0
        self._unsubs.append(
            async_track_utc_time_change(
                self.hass, self._async_interval_boundary, minute=minute, second=0
            )
        )
        self._recalculate(dt_util.utcnow())

    async def async_stop(self) -> None:
        """Stop listening and persist the history."""
        while self._unsubs:
            self._unsubs.pop()()
        await self.history.async_save()

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> CALLBACK_TYPE:
        """Call ``update_callback`` whenever the house consumption changes."""
        self._listeners.append(update_callback)
        return lambda: self._listeners.remove(update_callback)

    @property
    def source_entity_ids(self) -> list[str]:
        """All sensors the calculation depends on."""
        grid = [e for pair in self.grid_phases for e in pair if e is not None]
        return [*grid, *self.pv_sensors, *self.excluded_sensors]

    def calculate(self) -> float | None:
        """Compute house consumption in W from the current sensor states.

        Unknown if any grid measurement is unknown; unknown PV sources and
        excluded loads count as 0 W.
        """
        grid = 0.0
        for main, ret in self.grid_phases:
            value = self._watts(main)
            returned = self._watts(ret) if ret is not None else 0.0
            if value is None or returned is None:
                return None
            grid += value - abs(returned)
        pv = self._sum_abs(self.pv_sensors)
        excluded = self._sum_abs(self.excluded_sensors)
        return max(round(grid + pv - excluded, 1), 0.0)

    def _watts(self, entity_id: str) -> float | None:
        return state_to_watts(self.hass.states.get(entity_id))

    def _sum_abs(self, entity_ids: list[str]) -> float:
        values = (self._watts(e) for e in entity_ids)
        return sum(abs(v) for v in values if v is not None)

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        self._recalculate(event.time_fired)

    @callback
    def _async_interval_boundary(self, now: datetime) -> None:
        self.history.close_interval(now)

    @callback
    def _recalculate(self, when: datetime) -> None:
        self.power = self.calculate()
        self.history.add_sample(when, self.power)
        for update_callback in list(self._listeners):
            update_callback()


def _subentry_sensors(entry: ConfigEntry, subentry_type: str) -> list[str]:
    return [
        subentry.data[CONF_SENSOR]
        for subentry in entry.subentries.values()
        if subentry.subentry_type == subentry_type
    ]
