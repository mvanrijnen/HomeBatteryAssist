"""Heating/cooling zones: a heating/cooling device with, optionally, the
temperature of the room it heats or cools and its own outdoor temperature.

Several devices (an airco per room, a heat pump) are several zones; each is
learned on its own (``engine/forecast/temperature_effect.py``). Only reads.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant

from ...const import (
    CONF_INDOOR_TEMPERATURE,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_SENSOR,
    SUBENTRY_HEATING_COOLING,
)
from ..sources.weather import valid_indoor, valid_temperature
from ..units import state_to_celsius, state_to_watts

ZoneSample = tuple[float | None, float | None, float | None]  # W, indoor, outdoor


@dataclass(frozen=True, slots=True)
class HeatingZone:
    """One heating/cooling device and its temperature sensors."""

    zone_id: str  # the subentry id
    name: str
    power_sensor: str
    indoor_sensor: str | None = None
    outdoor_sensor: str | None = None

    @property
    def temperature_sensors(self) -> list[str]:
        return [s for s in (self.indoor_sensor, self.outdoor_sensor) if s]

    def read(self, hass: HomeAssistant) -> ZoneSample:
        """Power (W), room temperature and outdoor temperature (°C) now."""
        power = state_to_watts(hass.states.get(self.power_sensor))
        indoor = outdoor = None
        if self.indoor_sensor:
            indoor = valid_indoor(state_to_celsius(hass.states.get(self.indoor_sensor)))
        if self.outdoor_sensor:
            outdoor = valid_temperature(
                state_to_celsius(hass.states.get(self.outdoor_sensor))
            )
        return (abs(power) if power is not None else None, indoor, outdoor)


def heating_zones(entry: ConfigEntry) -> list[HeatingZone]:
    """The heating/cooling devices of the config entry."""
    return [
        HeatingZone(
            subentry.subentry_id,
            subentry.data.get(CONF_NAME) or subentry.title,
            subentry.data[CONF_SENSOR],
            subentry.data.get(CONF_INDOOR_TEMPERATURE) or None,
            subentry.data.get(CONF_OUTDOOR_TEMPERATURE) or None,
        )
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_HEATING_COOLING
        and subentry.data.get(CONF_SENSOR)
    ]
