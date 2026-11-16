"""Runtime data of a HomeBatteryAssist config entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .engine.batteries.monitor import BatteryInput
from .engine.explain import DecisionLog
from .engine.forecasts.coordinator import ForecastCoordinator
from .engine.history import ConsumptionHistory
from .engine.inputs.measurements import MeasurementInput
from .engine.planning.verification import PlanVerification


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
