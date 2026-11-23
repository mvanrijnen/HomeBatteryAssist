"""Test control of one battery — BUILT, OFF unless the user switches it on.

To test controlling a battery by hand, before any automatic control: per real
battery *Test: charge*, *Test: discharge* and *Test: stop* (buttons), with a
test power and a test duration (numbers). A test charges or discharges at
that power for that long and then always hands the battery back to its own
control. It goes through the battery's direct connection when it has one
(``LinkDriver``: e.g. the Marstek Venus over Modbus TCP, with Omnibattery
switched off), else through the integration it is read with
(``ReaderDriver``: e.g. Omnibattery's manual mode).

**Off by default**: the setting *Test control* (option ``control_test``,
default off; ``CONTROL_TEST_ALLOWED`` is that default and stays False,
checked by ``tests/test_read_only.py``). While off, a button only tells
*Why* that the test is switched off; nothing is sent. Steps: switch it on,
test on a real installation with the user present, mark the driver
``verified`` for writing.

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
from ..measure.battery_monitor import BatteryConfig, BatteryInput, direct_link
from .battery_controller import BatteryController
from .reader_driver import LinkDriver, ReaderDriver

_LOGGER = logging.getLogger(__name__)

# The default of the setting *Test control*: off, a test sends nothing.
CONTROL_TEST_ALLOWED: Final = False

DEFAULT_POWER_W: Final = 300
DEFAULT_MINUTES: Final = 5
# Test: charge full — at the battery's max charge power until full, then on
# a little for the cells to balance: until it takes less than FULL_DONE_W,
# at most FULL_TOP_UP; never longer than FULL_MAX in all.
FULL_MAX: Final = timedelta(hours=6)
FULL_TOP_UP: Final = timedelta(minutes=30)
FULL_DONE_W: Final = 100.0
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
    full: bool = False  # Test: charge full
    full_since: datetime | None = None  # when it reached its max SoC


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
        # Stopped tests whose release failed: retried every tick until the
        # battery is back under its own control.
        self.releasing: dict[str, BatteryController] = {}
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

    def writer(self, config: BatteryConfig) -> tuple[Any, str] | None:
        """How a battery can be controlled: (driver for the controller, its
        name for *Why*), or None. Its direct connection first."""
        link = direct_link(self.hass, config)
        if link is not None:
            if not link.can_write:
                return None
            return LinkDriver(self.hass, link, config), link.driver.name
        reader = reader_for(self.hass, config)
        if reader is None or not reader.can_write:
            return None
        return ReaderDriver(self.hass, reader, config), reader.name

    def status(self, battery_id: str) -> str:
        """What the test control of a battery can do / does now."""
        if not self.allowed:
            return STATUS_READ_ONLY
        run = self.runs.get(battery_id)
        if run is not None:
            return STATUS_CHARGING if run.power_w > 0 else STATUS_DISCHARGING
        if self.writer(self.configs[battery_id]) is None:
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

    def _refusal(
        self, config: BatteryConfig, charge: bool, topping_up: bool = False
    ) -> str | None:
        """Why a test cannot start (or must stop) now, if so; ``topping_up``:
        a full charge that may go on at its max SoC for the cells."""
        soc = self._batteries.states[config.id].soc
        if soc is None:
            return "unknown"
        if charge and soc >= config.max_soc and not topping_up:
            return "full"
        if not charge and soc <= self._floor(config):
            return "empty"
        return None

    async def async_start(
        self, battery_id: str, charge: bool, full: bool = False
    ) -> None:
        """Start a test: charge (or discharge) at the test power for the test
        duration; ``full``: charge at the battery's max charge power until it
        is full (``FULL_MAX`` at most). Only tells *Why* while the test
        control is switched off."""
        config = self.configs[battery_id]
        if not self.allowed:
            self._decisions.async_log(
                "battery", "control_test_blocked", name=config.name
            )
            return
        writer = self.writer(config)
        reason = "no_writer" if writer is None else self._refusal(config, charge)
        if reason is not None:
            self._decisions.async_log(
                "battery",
                "control_test_refused",
                name=config.name,
                reason=f"@test_{reason}",
            )
            return
        assert writer is not None
        driver, writer_name = writer
        if battery_id in self.runs:
            await self.async_stop(battery_id, "stopped")
        if (old := self.releasing.pop(battery_id, None)) is not None:
            # An earlier test is still being handed back: first that (its
            # retry would otherwise undo this test's command, or this one
            # would run while the battery is under its own control).
            await old.async_release("retry")
            if old.state.release_pending or old.sending:
                self.releasing[battery_id] = old
                self._decisions.async_log(
                    "battery",
                    "control_test_refused",
                    name=config.name,
                    reason="@test_error",
                )
                return
        limit = config.max_charge_w if full else max(self.power_w[battery_id], 0.0)
        power = limit if charge else -limit
        now = dt_util.utcnow()
        stats = self._batteries.stats[battery_id]
        controller = BatteryController(
            driver,
            enabled=self.allowed,
            limits=(
                min(limit, config.max_charge_w),
                min(limit, config.max_discharge_w),
            ),
        )
        run = TestRun(
            power,
            now,
            now + (FULL_MAX if full else timedelta(minutes=self.minutes[battery_id])),
            stats.get("charged_kwh", 0.0),
            stats.get("discharged_kwh", 0.0),
            controller,
            full=full,
        )
        self.runs[battery_id] = run
        # A new command: an earlier one not followed (e.g. a refused
        # discharge test) must not stop this test at once.
        if self._commands is not None and (
            check := self._commands.checks.get(battery_id)
        ):
            check.restart()
        if full:
            self._decisions.async_log(
                "battery",
                "control_test_full_started",
                name=config.name,
                power=f"{abs(power):.0f} W",
                integration=writer_name,
            )
        else:
            self._decisions.async_log(
                "battery",
                "control_test_started",
                name=config.name,
                direction="@dir_charge" if charge else "@dir_discharge",
                power=f"{abs(power):.0f} W",
                minutes=f"{self.minutes[battery_id]:.0f}",
                until=run.until,
                integration=writer_name,
            )
        if self._unsub is None:
            self._unsub = async_track_time_interval(self.hass, self._async_tick, TICK)
        self._changed()
        await controller.async_command(power, now)
        if controller.errors:
            await self.async_stop(battery_id, "error")

    async def _async_tick(self, now: datetime) -> None:
        for battery_id, controller in list(self.releasing.items()):
            if controller.state.release_pending:
                await controller.async_tick(now)  # retries the release
            if not controller.state.release_pending and not controller.sending:
                # (pop: a tick that overlaps a slow release, or a stop of
                # everything meanwhile, may have removed it already)
                self.releasing.pop(battery_id, None)
        for battery_id in list(self.runs):
            try:
                await self._async_tick_run(battery_id, now)
            except Exception:
                # Whatever went wrong: this test stops (and releases), the
                # others go on.
                _LOGGER.exception("Control test of %s failed; stopping", battery_id)
                await self.async_stop(battery_id, "error")
        self._stop_timer_when_idle()

    async def _async_tick_run(self, battery_id: str, now: datetime) -> None:
        run = self.runs[battery_id]
        config = self.configs[battery_id]
        check = self._commands.checks.get(battery_id) if self._commands else None
        state = self._batteries.states[battery_id]
        topped_up = False
        if run.full and state.soc is not None and state.soc >= config.max_soc:
            # Full: on a little for the cells, until it takes little.
            run.full_since = run.full_since or now
            topped_up = now - run.full_since >= FULL_TOP_UP or (
                now - run.full_since >= TICK * 6
                and state.power_w is not None
                and state.power_w < FULL_DONE_W
            )
        reason = (
            "full"
            if topped_up
            else "done"
            if now >= run.until
            else "error"
            if run.controller.errors
            else "not_following"
            if check is not None and check.problem and run.full_since is None
            else self._refusal(config, run.power_w > 0, topping_up=run.full)
        )
        if reason is not None:
            await self.async_stop(battery_id, reason)
            return
        # A fresh target keeps the watchdog quiet; the controller sends
        # only what changed (and refreshes when the driver needs it).
        await run.controller.async_command(run.power_w, now)

    def _stop_timer_when_idle(self) -> None:
        if not self.runs and not self.releasing and self._unsub is not None:
            self._unsub()
            self._unsub = None

    async def async_stop(self, battery_id: str, reason: str = "stopped") -> None:
        """Stop a test (if any) and hand the battery back to its own control."""
        run = self.runs.pop(battery_id, None)
        if run is None:
            return
        try:
            await run.controller.async_stop()
        except Exception:
            _LOGGER.exception("Releasing %s failed", battery_id)
            run.controller.state.release_pending = True
        if run.controller.state.release_pending or run.controller.sending:
            # The release failed, or a command is still being sent (its
            # release follows when it returns and may fail): tried again
            # every tick (the battery must not stay forced while the test
            # counts as stopped).
            self.releasing[battery_id] = run.controller
            if self._unsub is None:
                self._unsub = async_track_time_interval(
                    self.hass, self._async_tick, TICK
                )
        self._stop_timer_when_idle()
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

    async def async_stop_all(self, _event: Any = None) -> None:
        """Stop every test (HomeBatteryAssist stops or reloads, Home
        Assistant stops) and release; a failed release is tried once more."""
        for battery_id in list(self.runs):
            await self.async_stop(battery_id, "unload")
        for battery_id, controller in list(self.releasing.items()):
            await controller.async_release("retry")
            if not controller.state.release_pending and not controller.sending:
                self.releasing.pop(battery_id, None)
        self._stop_timer_when_idle()
