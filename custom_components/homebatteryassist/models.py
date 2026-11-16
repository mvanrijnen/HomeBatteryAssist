"""Runtime data of a HomeBatteryAssist config entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .explain import DecisionLog
from .forecasts.coordinator import ForecastCoordinator
from .history import ConsumptionHistory
from .inputs.batteries import BatteryInput
from .inputs.measurements import MeasurementInput
from .planning.verification import PlanVerification


@dataclass(slots=True)
class HomeBatteryAssistData:
    """The modules of one config entry, wired together in ``__init__.py``."""

    decisions: DecisionLog
    measurements: MeasurementInput
    batteries: BatteryInput
    history: ConsumptionHistory
    forecast: ForecastCoordinator
    plan_check: PlanVerification
    simulator: Any = None  # VirtualBatterySimulator (live protections)


type HomeBatteryAssistConfigEntry = ConfigEntry[HomeBatteryAssistData]
