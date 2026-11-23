"""The control loop: HomeBatteryAssist controls real batteries.

Off unless the setting *Control on* (``control_enabled``) is on, and then only
for the batteries whose form says *Controlled by HomeBatteryAssist*
(``control``). Each round it gives such a battery the power the virtual
batteries would get in its place: the loop IS the virtual battery simulator
(``VirtualBatterySimulator``) on the controlled real batteries, so both share
every step — zero on the meter (PD control on the measured grid), or the
plan (setting *Control mode*: ``nom`` = zero on the meter whatever the plan,
``plan`` = the selected plan), full charges, phase protection, peak shaving,
the interceptor, the state of charge limits and the system limits.

What differs from the simulation:

- the grid is the measured grid **without** the controlled batteries (their
  measured power taken off, as for a twin): what the house and the sun ask;
- the powers are not simulated but sent, per battery through its
  ``BatteryController`` (watchdog, throttle, deadband, limits, release on any
  error) over its direct connection (``LinkDriver``) or, without one, its
  integration (``ReaderDriver``);
- what the batteries do is what they are measured to do (no simulated delay).

A battery is handed back to its own control (released) and not commanded
while a test runs on it (``ControlTest``), while it does not follow its
command (``CommandMonitor``), while its state of charge or power is unknown,
or while the grid measurement is gone; it is taken up again when that ends.
On stop (unload, Home Assistant stopping) every battery is released.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant

from ..devices.batteries import reader_for
from ..devices.batteries.response import BatteryResponse
from ..devices.batteries.virtual import (
    PhaseDevice,
    VirtualBatterySimulator,
    limit_power,
    without_batteries,
)
from ..explain import DecisionLog
from ..measure.battery_monitor import (
    BatteryConfig,
    BatteryInput,
    direct_link,
    twinned_ids,
)
from .battery_controller import BatteryController
from .reader_driver import LinkDriver, ReaderDriver

_LOGGER = logging.getLogger(__name__)

CONTROL_MODE_NOM = "nom"  # zero on the meter, whatever the plan says
CONTROL_MODE_PLAN = "plan"  # the selected plan (arbitrage, full charges, ...)
CONTROL_MODES = (CONTROL_MODE_NOM, CONTROL_MODE_PLAN)

HOLD_TEST = "test"
HOLD_NOT_FOLLOWING = "not_following"
HOLD_METER = "meter"
HOLD_UNKNOWN = "unknown"


class ControlLoop(VirtualBatterySimulator):
    """Turns zero on the meter (or the plan) into commands per real battery."""

    def __init__(
        self,
        hass: HomeAssistant,
        batteries: BatteryInput,
        measurements: Any,
        forecast: Any,
        decisions: DecisionLog,
        *,
        mode: str = CONTROL_MODE_NOM,
        monitor: Any = None,  # CommandMonitor: does a battery follow?
        tests: Any = None,  # ControlTest: a running test has the battery
    ) -> None:
        """Initialize: a controller per battery that may and can be controlled."""
        super().__init__(hass, batteries, measurements, forecast, decisions)
        self.mode = mode if mode in CONTROL_MODES else CONTROL_MODE_NOM
        self._monitor = monitor
        self._tests = tests
        self.controllers: dict[str, BatteryController] = {}
        self.writers: dict[str, str] = {}  # battery id -> how it is reached
        twins = twinned_ids(batteries.configs)
        for config in batteries.configs:
            if config.virtual or not config.control or config.id in twins:
                continue
            link = direct_link(hass, config)
            reader = reader_for(hass, config)
            if link is not None and link.can_write:
                driver: Any = LinkDriver(hass, link, config)
                self.writers[config.id] = link.driver.name
            elif link is None and reader is not None and reader.can_write:
                driver = ReaderDriver(hass, reader, config)
                self.writers[config.id] = reader.name
            else:
                decisions.async_log("battery", "control_not_possible", name=config.name)
                continue
            self.controllers[config.id] = BatteryController(
                driver,
                enabled=True,
                limits=(config.max_charge_w, config.max_discharge_w),
            )
        self.holding: dict[str, str] = {}  # battery id -> why it is released now
        self.sent: dict[str, float | None] = {}  # last power asked (None: held)
        self._failed: set[str] = set()
        self._busy = False

    # -- what differs from the simulation ---------------------------------
    @property
    def virtual(self) -> list[BatteryConfig]:
        """The batteries this loop drives (the name is the simulator's)."""
        return [c for c in self._batteries.configs if c.id in self.controllers]

    def _flow(self) -> Any:
        """The measured grid without the controlled batteries: what the
        house and the sun ask of them."""
        flow = super()._flow()
        if flow is None:
            return None
        states = self._batteries.states
        if any(states[c.id].power_w is None for c in self.virtual):
            return None  # the grid without them is not known now
        phases = max(len(flow.phase_w), 1)
        return without_batteries(
            flow,
            [
                (
                    PhaseDevice.from_config(c, phases).phase,
                    states[c.id].power_w or 0.0,
                )
                for c in self.virtual
            ],
        )

    def _follows_nom(self, data: Any) -> bool:  # type: ignore[override]
        """Zero on the meter in mode ``nom``; else as the plan says."""
        if self.mode == CONTROL_MODE_NOM:
            return True
        return VirtualBatterySimulator._follows_nom(data)

    def step(self, now: datetime) -> None:
        """One round. Direct zero on the meter works from what the battery
        does, not from the previous command: a real battery takes a few
        seconds, and adding the gap to a command it still ramps towards
        would overshoot (the PD controller handles that itself)."""
        super().step(now)
        if self._direct:
            self._commands = {}

    def _response(self, battery_id: str) -> BatteryResponse:
        """No simulated reaction: what a battery does is measured."""
        if battery_id not in self._responses:
            self._responses[battery_id] = BatteryResponse(0.0, 0.0)
        return self._responses[battery_id]

    def _apply(
        self,
        now: datetime,
        elapsed: timedelta,
        hours: float,
        wanted: dict[str, float],
        socs: dict[str, float],
        full: dict[str, Any],
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Send the powers (within each battery's limits); what they do is
        their measured power."""
        powers: dict[str, float] = {}
        commands: dict[str, float] = {}
        send: dict[str, tuple[float | None, str | None]] = {}
        for config in self.virtual:
            state = self._batteries.states[config.id]
            limits = replace(config, max_soc=100.0) if full[config.id] else config
            command, _soc = limit_power(
                limits, socs[config.id], wanted[config.id], hours
            )
            commands[config.id] = command
            powers[config.id] = state.power_w or 0.0
            hold = self._hold_reason(config.id)
            send[config.id] = (None if hold else command, hold)
        if not self._busy:
            self._busy = True
            self.hass.async_create_task(self._async_send(now, send))
        return powers, commands

    def _hold_reason(self, battery_id: str) -> str | None:
        """Why a battery is not commanded now (released), if so."""
        if self._tests is not None and battery_id in getattr(self._tests, "runs", {}):
            return HOLD_TEST
        check = (
            self._monitor.checks.get(battery_id) if self._monitor is not None else None
        )
        if check is not None and check.problem:
            return HOLD_NOT_FOLLOWING
        if self._meter_lost:
            return HOLD_METER
        state = self._batteries.states[battery_id]
        if state.soc is None or state.power_w is None:
            return HOLD_UNKNOWN
        return None

    async def _async_send(
        self, now: datetime, send: dict[str, tuple[float | None, str | None]]
    ) -> None:
        try:
            for battery_id, (power, hold) in send.items():
                controller = self.controllers[battery_id]
                name = next(
                    c.name for c in self._batteries.configs if c.id == battery_id
                )
                was = self.holding.get(battery_id)
                if hold is not None:
                    if was != hold:
                        self.holding[battery_id] = hold
                        if hold != HOLD_TEST:  # a test is not ours to release
                            await controller.async_release(hold)
                        self._decisions.async_log(
                            "battery",
                            "control_held",
                            name=name,
                            reason=f"@control_{hold}",
                        )
                    self.sent[battery_id] = None
                    continue
                if was is not None:
                    del self.holding[battery_id]
                    self._decisions.async_log("battery", "control_resumed", name=name)
                errors = controller.errors
                await controller.async_command(power, now)
                self.sent[battery_id] = power
                if controller.errors > errors and battery_id not in self._failed:
                    self._failed.add(battery_id)
                    self._decisions.async_log("battery", "control_failed", name=name)
                elif controller.errors == errors:
                    self._failed.discard(battery_id)
        except Exception:
            _LOGGER.exception("Control round failed")
        finally:
            self._busy = False

    # -- life cycle -------------------------------------------------------
    def async_start(self) -> None:
        """Start the rounds (only with a battery to control)."""
        if not self.controllers:
            return
        super().async_start()
        self._decisions.async_log(
            "battery",
            "control_started",
            names=", ".join(f"{c.name} ({self.writers[c.id]})" for c in self.virtual),
            mode=f"@control_mode_{self.mode}",
        )

    async def async_stop_all(self, _event: Any = None) -> None:
        """Stop and hand every battery back to its own control."""
        super().async_stop()
        for battery_id, controller in self.controllers.items():
            if self.holding.get(battery_id) == HOLD_TEST:
                continue  # the test hands it back itself
            try:
                await controller.async_stop()
            except Exception:
                _LOGGER.exception("Releasing %s failed", battery_id)
        if self.controllers:
            self._decisions.async_log("battery", "control_stopped")
            self.controllers = {}

    def as_dict(self) -> dict[str, Any]:
        """For diagnostics and the dashboard."""
        return {
            "mode": self.mode,
            "batteries": {
                battery_id: {
                    "through": self.writers.get(battery_id),
                    "sent": self.sent.get(battery_id),
                    "held": self.holding.get(battery_id),
                    "active": controller.state.active,
                    "errors": controller.errors,
                }
                for battery_id, controller in self.controllers.items()
            },
        }
