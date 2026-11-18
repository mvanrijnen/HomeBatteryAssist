"""Does a battery follow its command?

Whoever controls a battery (in this phase its own integration, e.g.
Omnibattery; later HomeBatteryAssist's control loop) tells it to charge or
discharge at a power. The battery's driver reads that command
(``BatteryReader.command``); this check compares it with the power the
battery really has.

Not following: a command of at least ``threshold_w`` while the battery moves
less than half of it (``FOLLOW_SHARE``, of the command or of its maximum power
when that is lower) in that direction, or goes the other way. Told once it
lasts ``start_after`` (starting up and ramping take seconds, so a short lag is
no message), over after ``END_AFTER`` of following again (or without a
command).

When it is explainable — full (charging), at its minimum (discharging),
charging/discharging switched off on the battery, the battery's hysteresis
after a full charge — *Why* says so with the reason, and it is not a problem:
no alarm, no notification. Otherwise it is a problem: *Why*
``battery_not_following`` (notification kind ``battery_command``), the
battery's problem sensor on, and ``_ended`` once it follows again.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from ..devices.batteries import BatteryCommand
from ..devices.batteries import command as read_command
from ..explain import DecisionLog
from ..measure.battery_monitor import BatteryConfig, BatteryInput

FOLLOW_SHARE = 0.5
START_AFTER = timedelta(minutes=2)
END_AFTER = timedelta(minutes=1)
INTERVAL = timedelta(seconds=15)
SOC_MARGIN = 1.0  # % from the limit that counts as full / empty


def follows(command_w: float, actual_w: float, max_w: float = 0.0) -> bool:
    """Whether the battery moves at least half of what it is told to (or of
    its maximum power, when that is lower), in the commanded direction."""
    target = abs(command_w)
    if max_w > 0:
        target = min(target, max_w)
    moved = actual_w if command_w > 0 else -actual_w
    return moved >= FOLLOW_SHARE * target


def reason_for(
    command: BatteryCommand, soc: float | None, config: BatteryConfig
) -> str | None:
    """Why a battery cannot follow its command, if that is explainable."""
    if command.power_w > 0:
        if not command.charge_allowed:
            return "charge_off"
        if command.hysteresis:
            return "hysteresis"
        if soc is not None and soc >= min(config.max_soc, 100.0) - SOC_MARGIN:
            return "full"
    elif command.power_w < 0:
        if not command.discharge_allowed:
            return "discharge_off"
        if soc is not None and soc <= config.min_soc + SOC_MARGIN:
            return "empty"
    return None


@dataclass
class _Event:
    start: datetime
    seen: datetime
    reason: str | None  # explainable now (None = a problem)
    problem: bool  # was a problem (told so: ended is told too)


class CommandCheck:
    """Follows one battery's command against its power."""

    def __init__(
        self,
        threshold_w: float = 100.0,
        start_after: timedelta = START_AFTER,
    ) -> None:
        """Initialize."""
        self.threshold_w = threshold_w
        self.start_after = start_after
        self.event: _Event | None = None
        self.command: BatteryCommand | None = None
        self.actual_w: float | None = None
        self._since: datetime | None = None  # not following since (before start)
        self._quiet: datetime | None = None  # following again since (in event)

    @property
    def problem(self) -> bool:
        """Not following, and not explainable."""
        return self.event is not None and self.event.reason is None

    def as_dict(self) -> dict[str, Any]:
        """For the dashboard and the problem sensor."""
        event = self.event
        return {
            "command_w": self.command.power_w if self.command else None,
            "actual_w": self.actual_w,
            "not_following": event is not None,
            "problem": self.problem,
            "reason": event.reason if event else None,
            "since": event.start.isoformat() if event else None,
        }

    def update(
        self,
        when: datetime,
        command: BatteryCommand | None,
        soc: float | None,
        actual_w: float | None,
        config: BatteryConfig,
    ) -> tuple[str, dict[str, Any]] | None:
        """One look; returns a message to log, if any."""
        self.command, self.actual_w = command, actual_w
        max_w = 0.0
        if command is not None:
            max_w = (
                config.max_charge_w if command.power_w > 0 else config.max_discharge_w
            )
        failing = (
            command is not None
            and actual_w is not None
            and abs(command.power_w) >= self.threshold_w
            and not follows(command.power_w, actual_w, max_w)
        )
        if not failing:
            self._since = None
            return self._maybe_end(when)
        assert command is not None and actual_w is not None
        reason = reason_for(command, soc, config)
        self._quiet = None
        if self.event is not None:
            self.event.seen = when
            self.event.reason = reason
            if reason is None and not self.event.problem:
                # It was explainable, now it is not.
                self.event.problem = True
                return self._told("battery_not_following", command, actual_w, config)
            return None
        if self._since is None:
            self._since = when
        if when - self._since < self.start_after:
            return None
        self.event = _Event(self._since, when, reason, reason is None)
        self._since = None
        if reason is None:
            return self._told("battery_not_following", command, actual_w, config)
        return self._told(
            "battery_not_following_explained", command, actual_w, config, reason
        )

    def _told(
        self,
        key: str,
        command: BatteryCommand,
        actual_w: float,
        config: BatteryConfig,
        reason: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        assert self.event is not None
        params: dict[str, Any] = {
            "name": config.name,
            "direction": "@dir_charge" if command.power_w > 0 else "@dir_discharge",
            "command": f"{abs(command.power_w):.0f} W",
            "actual": f"{actual_w:.0f} W",
            "since": self.event.start,
        }
        if reason is not None:
            params["reason"] = f"@reason_{reason}"
        return key, params

    def _maybe_end(self, when: datetime) -> tuple[str, dict[str, Any]] | None:
        event = self.event
        if event is None:
            return None
        if self._quiet is None:
            self._quiet = when
        if when - self._quiet < END_AFTER:
            return None
        self.event = None
        self._quiet = None
        if not event.problem:
            return None
        return (
            "battery_not_following_ended",
            {"name": "", "start": event.start, "end": event.seen},
        )


class CommandMonitor:
    """Runs a ``CommandCheck`` per real battery every ``INTERVAL`` (also when
    the battery's power does not change, e.g. stuck at 0 W)."""

    def __init__(
        self,
        hass: HomeAssistant,
        batteries: BatteryInput,
        decisions: DecisionLog,
        threshold_w: float = 100.0,
        start_after: timedelta = START_AFTER,
        read: Callable[
            [HomeAssistant, BatteryConfig], BatteryCommand | None
        ] = read_command,
    ) -> None:
        """Initialize."""
        self.hass = hass
        self._batteries = batteries
        self._decisions = decisions
        self._read = read
        self.checks: dict[str, CommandCheck] = {
            c.id: CommandCheck(threshold_w, start_after)
            for c in batteries.configs
            if not c.virtual
        }
        self._listeners: list[Callable[[], None]] = []
        self._unsub: CALLBACK_TYPE | None = None

    @callback
    def async_start(self) -> None:
        """Start looking."""
        if self.checks:
            self._unsub = async_track_time_interval(
                self.hass, self.async_check, INTERVAL
            )

    @callback
    def async_stop(self) -> None:
        """Stop looking."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call ``listener`` after every look."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def state(self, battery_id: str) -> dict[str, Any] | None:
        """The check of a battery, for the dashboard (None: not checked)."""
        check = self.checks.get(battery_id)
        return check.as_dict() if check else None

    @callback
    def async_check(self, now: datetime) -> None:
        """Look at every real battery once."""
        for config in self._batteries.configs:
            check = self.checks.get(config.id)
            if check is None:
                continue
            state = self._batteries.states[config.id]
            result = check.update(
                now,
                self._read(self.hass, config),
                state.soc,
                state.power_w,
                config,
            )
            if result is not None:
                key, params = result
                params["name"] = config.name
                self._decisions.async_log("battery", key, **params)
        for listener in list(self._listeners):
            listener()
