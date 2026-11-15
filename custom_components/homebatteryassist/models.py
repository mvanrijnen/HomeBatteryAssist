"""Runtime data of a HomeBatteryAssist config entry."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .consumption import HouseConsumption
from .forecast import ForecastCoordinator


@dataclass(slots=True)
class HomeBatteryAssistData:
    """Objects shared by the platforms of one config entry."""

    consumption: HouseConsumption
    forecast: ForecastCoordinator


type HomeBatteryAssistConfigEntry = ConfigEntry[HomeBatteryAssistData]
