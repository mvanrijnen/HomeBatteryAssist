"""Battery control — BUILT, NOT ACTIVE.

HomeBatteryAssist is read-only by decision of the project owner. This module
is the control layer for the day that changes, built and tested beforehand so
the safety is there before anything is ever controlled:

- **Master switch** ``enabled`` (default False). While off, nothing is ever
  sent to a battery; asking for a command raises ``ControlDisabled``. Nothing
  in HomeBatteryAssist turns it on.
- **Always release**: on stop, reload, restart, on every error, and after a
  failed command, control is handed back to the battery's own logic
  (``driver.async_release``) before anything else.
- **Watchdog**: without a new command for ``watchdog_s`` (the plan or the
  control loop stopped), control is released.
- **Refresh**: the last command is repeated every ``driver.refresh_s`` for
  batteries that drop out of external control otherwise.
- **Throttle**: at most one new command every ``MIN_INTERVAL_S`` (for every
  battery; a driver may ask for longer with ``driver.min_interval_s``) and
  only when it differs by ``driver.deadband_w`` (slowly ramping batteries,
  write wear); going idle or changing direction is never held back.
- **Idle = release** for batteries where 0 W is not idle
  (``driver.idle_is_release``, e.g. a Huawei inverter that still limits PV).
- **Limits** of the driver and of the caller are always enforced.

``decide`` holds all of these rules as a pure function (easy to test);
``BatteryController`` runs it with a driver and a 1-second tick.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from homeassistant.util import dt as dt_util

from ..devices.batteries.direct.base import DirectBatteryDriver

_LOGGER = logging.getLogger(__name__)

DEFAULT_WATCHDOG = timedelta(minutes=2)
# For every battery: at least this long between new commands (a driver may
# ask for longer, never shorter). Idle and direction changes are not held back.
MIN_INTERVAL_S = 5.0
IDLE_W = 1.0  # below this a command means "idle"


class ControlDisabled(RuntimeError):
    """Control is switched off (HomeBatteryAssist is read-only)."""


@dataclass(slots=True)
class ControlState:
    """What the controller asked for and what it last sent."""

    target_w: float | None = None  # wanted power, + charging; None = release
    target_at: datetime | None = None  # when the target was last given
    sent_w: float | None = None  # last power sent; None = released
    sent_at: datetime | None = None
    active: bool = False  # the battery is under external control
    # A release failed: tried again every tick until it succeeds (a battery
    # must never stay forced while HomeBatteryAssist thinks it is free).
    release_pending: bool = False


@dataclass(frozen=True, slots=True)
class Action:
    """What to do now."""

    kind: Literal["send", "release"]
    power_w: float = 0.0
    reason: str = ""


def clamp(
    power_w: float, driver: DirectBatteryDriver, limits: tuple[float, float]
) -> float:
    """``power_w`` within the device's and the caller's charge/discharge limits."""
    max_charge, max_discharge = limits
    if driver.max_charge_w is not None:
        max_charge = min(max_charge, driver.max_charge_w)
    if driver.max_discharge_w is not None:
        max_discharge = min(max_discharge, driver.max_discharge_w)
    return max(-max(max_discharge, 0.0), min(power_w, max(max_charge, 0.0)))


def decide(
    state: ControlState,
    driver: DirectBatteryDriver,
    now: datetime,
    watchdog: timedelta,
) -> Action | None:
    """The next action under all safety rules, or None (nothing to do)."""
    # Watchdog: no fresh target -> back to the battery's own control.
    if state.active and (state.target_at is None or now - state.target_at > watchdog):
        return Action("release", reason="watchdog")
    target = state.target_w
    if target is None or (abs(target) < IDLE_W and driver.idle_is_release):
        return Action("release", reason="idle") if state.active else None
    if not state.active or state.sent_w is None or state.sent_at is None:
        return Action("send", target, "start")
    since = (now - state.sent_at).total_seconds()
    change = abs(target - state.sent_w)
    direction = (target > IDLE_W) - (target < -IDLE_W)
    sent_direction = (state.sent_w > IDLE_W) - (state.sent_w < -IDLE_W)
    # Going idle is never held back; a reversal (charge <-> discharge) is a
    # change like any other: throttled and with the deadband, else NOM
    # hovering around 0 W would write and flip every second.
    going_idle = direction == 0 and sent_direction != 0
    if change >= 0.5 and (
        going_idle
        or (
            since >= max(driver.min_interval_s, MIN_INTERVAL_S)
            and change >= max(driver.deadband_w, 0.5)
        )
    ):
        return Action("send", target, "change")
    if driver.refresh_s and since >= driver.refresh_s:
        return Action("send", state.sent_w, "refresh")
    return None


class BatteryController:
    """Controls one battery through its direct driver — only when enabled."""

    def __init__(
        self,
        driver: DirectBatteryDriver,
        *,
        enabled: bool = False,
        watchdog: timedelta = DEFAULT_WATCHDOG,
        limits: tuple[float, float] = (float("inf"), float("inf")),
    ) -> None:
        """Initialize; ``limits`` = (max charge, max discharge) in W."""
        self.driver = driver
        self.enabled = enabled
        self.watchdog = watchdog
        self.limits = limits
        self.state = ControlState()
        self.errors = 0
        # Stopped: no command is sent any more (one already being sent is
        # undone by a release when it returns).
        self.stopped = False
        self.sending = False  # a command is being sent right now

    async def async_command(
        self, power_w: float | None, now: datetime | None = None
    ) -> None:
        """Ask for ``power_w`` (+ charging; None = release). Refused while
        control is switched off."""
        if not self.enabled:
            raise ControlDisabled("battery control is switched off (read-only)")
        if self.stopped:
            return  # stopped: nothing more is sent
        now = now or dt_util.utcnow()
        if power_w is not None and not math.isfinite(power_w):
            # NaN would clamp to full discharge: release instead.
            _LOGGER.warning(
                "%s: invalid power %s; releasing", self.driver.name, power_w
            )
            power_w = None
        self.state.target_w = (
            None if power_w is None else clamp(power_w, self.driver, self.limits)
        )
        self.state.target_at = now
        await self.async_tick(now)

    async def async_tick(self, now: datetime | None = None) -> None:
        """Apply the rules now (called every second while running)."""
        if self.state.release_pending:
            await self.async_release("retry")
            return
        if not self.enabled and not self.state.active:
            return
        now = now or dt_util.utcnow()
        if not self.enabled:  # switched off while active: hand back
            await self.async_release("disabled")
            return
        action = decide(self.state, self.driver, now, self.watchdog)
        if action is None:
            return
        if action.kind == "release":
            await self.async_release(action.reason)
            return
        if self.stopped:
            return
        # Under external control from the moment the command goes out: a
        # stop while it is being sent releases (else it would see "not
        # active" and the battery would stay forced).
        self.state.active = True
        self.sending = True
        try:
            await self.driver.async_set_power(action.power_w)
        except Exception:
            self.errors += 1
            _LOGGER.exception("%s: command failed; releasing", self.driver.name)
            await self.async_release("error")
            return
        finally:
            self.sending = False
        if self.stopped:
            # Stopped while the command was being sent: undo it.
            await self.async_release("stop")
            return
        self.state.sent_w, self.state.sent_at = action.power_w, now

    async def async_release(self, reason: str = "") -> None:
        """Hand control back to the battery (always tried; errors logged)."""
        self.state.sent_w = self.state.sent_at = None
        if reason in ("watchdog", "error", "disabled", "stop", "retry"):
            self.state.target_w = None
        try:
            await self.driver.async_release()
        except Exception:
            self.errors += 1
            _LOGGER.exception("%s: release failed (%s)", self.driver.name, reason)
            # Still under control as far as we know: try again next tick.
            self.state.release_pending = True
            self.state.active = True
            return
        self.state.release_pending = False
        self.state.active = False

    async def async_stop(self) -> None:
        """Stop controlling: release if active (also while a command is
        being sent); nothing is sent afterwards."""
        self.stopped = True
        if self.state.active or self.state.release_pending:
            await self.async_release("stop")
