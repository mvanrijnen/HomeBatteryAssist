"""Test control of one battery — BUILT, SWITCHED OFF in this phase.

To test controlling a battery by hand, before any automatic control: per real
battery *Test: charge*, *Test: discharge* and *Test: stop* (buttons), with a
test power and a test duration (numbers). A test charges or discharges at
that power for that long through the battery's integration
(``ReaderDriver``: e.g. Omnibattery's manual mode) and then always hands the
battery back to its own control.

**Switched off**: ``CONTROL_TEST_ALLOWED`` is False by decision of the project
owner (HomeBatteryAssist is read-only in this phase). While it is False a
button only tells *Why* that the test is switched off; nothing is sent
(``tests/test_read_only.py`` checks it stays False). Switching it on is the
owner's call; then the steps are: set it to True (later an option), test on a
real installation with the user present, mark the reader ``verified`` for
writing.

Safety, on top of ``BatteryController`` (watchdog, always release, throttle,
limits): never charging at or above the battery's max state of charge, never
discharging at or below max(min SoC, reserve SoC); the test stops at once
when the battery does not follow the command (``CommandMonitor``), on any
error, at the end of its time, by *Test: stop*, and when HomeBatteryAssist
stops or reloads.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from ..devices.batteries import reader_for
from ..explain import DecisionLog
from ..measure.battery_monitor import BatteryConfig, BatteryInput
from .battery_controller import BatteryController
from .reader_driver import ReaderDriver

_LOGGER = logging.getLogger(__name__)

# The owner's decision: while False, a test sends nothing.
CONTROL_TEST_ALLOWED: Final = False

DEFAULT_POWER_W: Final = 300
DEFAULT_MINUTES: Final = 5
TICK = timedelta(seconds=5)

STATUS_READ_ONLY = "read_only"
STATUS_NOT_POSSIBLE = "not_possible"
STATUS_READY = "ready"
STATUS_CHARGING = "charging"
STATUS_DISCHARGING = "discharging"
STATUSES = (
    STATUS_READ_ONLY,
    STATUS_NOT_POSSIBLE,
    STATUS_READY,
    STATUS_CHARGING,
    STATUS_DISCHARGING,
)


@dataclass
class TestRun:
    """One running test."""

    power_w: float  # + charging / - discharging
    start: datetime
    until: datetime
    charged_kwh: float  # the battery's counters at the start
    discharged_kwh: float
    controller: BatteryController


class ControlTest:
    """Test control per real battery (switched off while not allowed)."""

    def __init__(
        self,
        hass: HomeAssistant,
        batteries: BatteryInput,
        decisions: DecisionLog,
        reserve_soc: Callable[[], float] = lambda: 0.0,
        commands: Any = None,  # CommandMonitor: stop when not followed
        allowed: bool = CONTROL_TEST_ALLOWED,
    ) -> None:
        """Initialize."""
        self.hass = hass
        self._batteries = batteries
        self._decisions = decisions
        self._reserve_soc = reserve_soc
        self._commands = commands
        self.allowed = allowed
        self.configs = {c.id: c for c in batteries.configs if not c.virtual}
        # Per battery: the test power (W) and duration (min), set by numbers.
        self.power_w = dict.fromkeys(self.configs, float(DEFAULT_POWER_W))
        self.minutes = dict.fromkeys(self.configs, float(DEFAULT_MINUTES))
        self.runs: dict[str, TestRun] = {}
        self._listeners: list[Callable[[], None]] = []
        self._unsub: CALLBACK_TYPE | None = None

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call ``listener`` when a test starts or stops."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _changed(self) -> None:
        for listener in list(self._listeners):
            listener()

    def status(self, battery_id: str) -> str:
        """What the test control of a battery can do / does now."""
        if not self.allowed:
            return STATUS_READ_ONLY
        run = self.runs.get(battery_id)
        if run is not None:
            return STATUS_CHARGING if run.power_w > 0 else STATUS_DISCHARGING
        reader = reader_for(self.hass, self.configs[battery_id])
        if reader is None or not reader.can_write:
            return STATUS_NOT_POSSIBLE
        return STATUS_READY

    def details(self, battery_id: str) -> dict[str, Any]:
        """The running test, for the status sensor."""
        run = self.runs.get(battery_id)
        return {
            "test_power": self.power_w[battery_id],
            "test_minutes": self.minutes[battery_id],
            "power": run.power_w if run else None,
            "since": run.start.isoformat() if run else None,
            "until": run.until.isoformat() if run else None,
        }

    def _floor(self, config: BatteryConfig) -> float:
        return max(config.min_soc, self._reserve_soc())

    def _refusal(self, config: BatteryConfig, charge: bool) -> str | None:
        """Why a test cannot start (or must stop) now, if so."""
        soc = self._batteries.states[config.id].soc
        if soc is None:
            return "unknown"
        if charge and soc >= config.max_soc:
            return "full"
        if not charge and soc <= self._floor(config):
            return "empty"
        return None

    async def async_start(self, battery_id: str, charge: bool) -> None:
        """Start a test: charge (or discharge) at the test power for the test
        duration. Only tells *Why* while the test control is switched off."""
        config = self.configs[battery_id]
        if not self.allowed:
            self._decisions.async_log(
                "battery", "control_test_blocked", name=config.name
            )
            return
        reader = reader_for(self.hass, config)
        reason = (
            "no_writer"
            if reader is None or not reader.can_write
            else self._refusal(config, charge)
        )
        if reason is not None:
            self._decisions.async_log(
                "battery",
                "control_test_refused",
                name=config.name,
                reason=f"@test_{reason}",
            )
            return
        assert reader is not None
        if battery_id in self.runs:
            await self.async_stop(battery_id, "stopped")
        limit = max(self.power_w[battery_id], 0.0)
        power = limit if charge else -limit
        now = dt_util.utcnow()
        stats = self._batteries.stats[battery_id]
        controller = BatteryController(
            ReaderDriver(self.hass, reader, config),
            enabled=self.allowed,
            limits=(
                min(limit, config.max_charge_w),
                min(limit, config.max_discharge_w),
            ),
        )
        run = TestRun(
            power,
            now,
            now + timedelta(minutes=self.minutes[battery_id]),
            stats.get("charged_kwh", 0.0),
            stats.get("discharged_kwh", 0.0),
            controller,
        )
        self.runs[battery_id] = run
        self._decisions.async_log(
            "battery",
            "control_test_started",
            name=config.name,
            direction="@dir_charge" if charge else "@dir_discharge",
            power=f"{abs(power):.0f} W",
            minutes=f"{self.minutes[battery_id]:.0f}",
            until=run.until,
            integration=reader.name,
        )
        if self._unsub is None:
            self._unsub = async_track_time_interval(self.hass, self._async_tick, TICK)
        self._changed()
        await controller.async_command(power, now)
        if controller.errors:
            await self.async_stop(battery_id, "error")

    async def _async_tick(self, now: datetime) -> None:
        for battery_id in list(self.runs):
            run = self.runs[battery_id]
            config = self.configs[battery_id]
            check = self._commands.checks.get(battery_id) if self._commands else None
            reason = (
                "done"
                if now >= run.until
                else "error"
                if run.controller.errors
                else "not_following"
                if check is not None and check.problem
                else self._refusal(config, run.power_w > 0)
            )
            if reason is not None:
                await self.async_stop(battery_id, reason)
                continue
            # A fresh target keeps the watchdog quiet; the controller sends
            # only what changed (and refreshes when the driver needs it).
            await run.controller.async_command(run.power_w, now)

    async def async_stop(self, battery_id: str, reason: str = "stopped") -> None:
        """Stop a test (if any) and hand the battery back to its own control."""
        run = self.runs.pop(battery_id, None)
        if run is None:
            return
        await run.controller.async_stop()
        if not self.runs and self._unsub is not None:
            self._unsub()
            self._unsub = None
        stats = self._batteries.stats[battery_id]
        minutes = (dt_util.utcnow() - run.start).total_seconds() / 60
        self._decisions.async_log(
            "battery",
            "control_test_stopped",
            name=self.configs[battery_id].name,
            reason=f"@test_{reason}",
            minutes=f"{minutes:.0f}",
            charged=self._kwh(stats.get("charged_kwh", 0.0) - run.charged_kwh),
            discharged=self._kwh(stats.get("discharged_kwh", 0.0) - run.discharged_kwh),
        )
        self._changed()

    def _kwh(self, kwh: float) -> str:
        text = f"{kwh:.2f}"
        comma = (self.hass.config.language or "").startswith("nl")
        return text.replace(".", ",") if comma else text

    async def async_stop_all(self) -> None:
        """Stop every test (HomeBatteryAssist stops or reloads)."""
        for battery_id in list(self.runs):
            await self.async_stop(battery_id, "unload")
