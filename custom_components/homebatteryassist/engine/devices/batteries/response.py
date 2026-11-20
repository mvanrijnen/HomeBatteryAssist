"""How a battery reacts to a new power (simulated, virtual batteries).

A real battery does not take a new power at once: it starts after a delay
(its integration polls, the inverter needs a moment) and ramps its power up
or down. The virtual batteries can simulate that (options ``sim_delay_s`` and
``sim_ramp_w_s``; 0 = at once, as before), so the control quality shows
whether zero on the meter would overshoot or lag on a real battery
(``engine/control/pd_controller.py``).

Per battery: the command in force is the newest one given at least
``delay`` ago; the power moves towards it by at most ``ramp_w_s`` per second.
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

    def apply(self, now: datetime, command_w: float) -> float:
        """Give ``command_w`` now; returns the power the battery has now."""
        if not self.active:
            self._power, self._last = command_w, now
            return command_w
        self._commands.append((now, command_w))
        due = now - self.delay
        # The front becomes the newest command that is due.
        while len(self._commands) > 1 and self._commands[1][0] <= due:
            self._commands.popleft()
        given, command = self._commands[0]
        if given <= due:
            self._target = command
        target = self._target if self._target is not None else (self._power or 0.0)
        power = self._power if self._power is not None else 0.0
        if self.ramp_w_s > 0 and self._last is not None:
            most = self.ramp_w_s * max((now - self._last).total_seconds(), 0.0)
            power += max(-most, min(most, target - power))
        else:
            power = target
        self._power, self._last = power, now
        return power

    def hold(self, power_w: float, now: datetime) -> None:
        """The battery's power was set from outside (limits, full/empty):
        go on from it."""
        self._power, self._last = power_w, now
