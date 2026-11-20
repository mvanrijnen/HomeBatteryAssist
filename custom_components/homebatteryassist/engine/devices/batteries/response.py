"""How a battery reacts to a new power (simulated, virtual batteries).

A real battery does not take a new power at once: it starts after a delay
(its integration polls, the inverter needs a moment) and ramps its power up
or down. The virtual batteries can simulate that (options ``sim_delay_s`` and
``sim_ramp_w_s``; 0 = at once, as before), so the control quality shows
whether zero on the meter would overshoot or lag on a real battery
(``engine/control/pd_controller.py``).

Per battery: a command takes over ``delay`` after it was given, at that
moment (not at the next round); from then the power moves towards it by at
most ``ramp_w_s`` per second. ``power_at`` gives the power at any moment, so
zero on the meter sees what the battery does when it looks, as a meter does.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta


class BatteryResponse:
    """The simulated reaction of one battery to its commands."""

    def __init__(self, delay_s: float = 0.0, ramp_w_s: float = 0.0) -> None:
        """Initialize (0 = at once)."""
        self.delay = timedelta(seconds=max(delay_s, 0.0))
        self.ramp_w_s = max(ramp_w_s, 0.0)
        self._commands: deque[tuple[datetime, float]] = deque()
        self._target: float | None = None  # the command in force
        self._power: float | None = None
        self._last: datetime | None = None

    @property
    def active(self) -> bool:
        """Whether it changes anything (else the command is the power)."""
        return self.delay > timedelta(0) or self.ramp_w_s > 0

    def _ramp(self, power: float, target: float, seconds: float) -> float:
        if self.ramp_w_s <= 0:
            return target
        most = self.ramp_w_s * max(seconds, 0.0)
        return power + max(-most, min(most, target - power))

    def power_at(self, now: datetime) -> float:
        """The power at ``now``: the commands given so far, each from the
        moment it takes over (given + delay), ramped from there."""
        power = self._power if self._power is not None else 0.0
        if self._last is None or now <= self._last:
            if self._last is None:
                self._last = now
            return power
        t = self._last
        target = self._target if self._target is not None else power
        while self._commands and self._commands[0][0] + self.delay <= now:
            given, command = self._commands.popleft()
            due = max(given + self.delay, t)
            power = self._ramp(power, target, (due - t).total_seconds())
            t, target = due, command
        power = self._ramp(power, target, (now - t).total_seconds())
        self._power, self._last, self._target = power, now, target
        return power

    def apply(self, now: datetime, command_w: float) -> float:
        """Give ``command_w`` now; returns the power the battery has now
        (the command takes over from now + delay)."""
        if not self.active:
            self._power, self._last = command_w, now
            return command_w
        power = self.power_at(now)
        self._commands.append((now, command_w))
        return self.power_at(now) if self.delay <= timedelta(0) else power

    def hold(self, power_w: float, now: datetime) -> None:
        """The battery's power was set from outside (limits, full/empty):
        go on from it."""
        self._power, self._last = power_w, now
