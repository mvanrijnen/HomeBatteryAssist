"""Runtime data of a HomeBatteryAssist config entry."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .explain import DecisionLog
from .forecasts.coordinator import ForecastCoordinator
from .history import ConsumptionHistory
from .inputs.batteries import BatteryInput
from .inputs.measurements import MeasurementInput


@dataclass(slots=True)
class HomeBatteryAssistData:
    """The modules of one config entry, wired together in ``__init__.py``."""

    decisions: DecisionLog
    measurements: MeasurementInput
    batteries: BatteryInput
    history: ConsumptionHistory
    forecast: ForecastCoordinator


type HomeBatteryAssistConfigEntry = ConfigEntry[HomeBatteryAssistData]
