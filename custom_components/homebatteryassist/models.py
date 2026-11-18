"""Runtime data of a HomeBatteryAssist config entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .engine.coordinator import ForecastCoordinator
from .engine.evaluation.plan_check import PlanVerification
from .engine.explain import DecisionLog
from .engine.history import ConsumptionHistory
from .engine.measure.battery_monitor import BatteryInput
from .engine.measure.house_measurement import MeasurementInput


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
    commands: Any = None  # CommandMonitor (does each battery follow its command)
    control_test: Any = None  # ControlTest (switched off in this phase)
    export_limit: Any = None  # ExportLimiter (shown and explained only)


type HomeBatteryAssistConfigEntry = ConfigEntry[HomeBatteryAssistData]
