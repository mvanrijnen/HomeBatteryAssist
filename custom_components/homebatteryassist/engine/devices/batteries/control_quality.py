"""How well zero on the meter keeps the grid at its target (control quality).

Per round of the virtual batteries: the grid as it would have been with them
(measured grid - excluded devices + their power, averaged over the round)
minus the zero on the meter target is the error. Over the last ``WINDOW``:

- ``oscillating``: the error keeps crossing zero (>= ``ERROR_W`` on both
  sides) while the battery power keeps reversing - the control overshoots;
- ``sluggish``: the mean error stays >= ``SLUGGISH_W`` while the batteries
  had room - the control lags behind the house;
- ``stable``: neither;
- ``idle``: too few rounds of zero on the meter (another mode, protections,
  batteries full or empty).

Only rounds in which the batteries could follow (zero on the meter, nothing
held them back) count. A preparation for real control: the same measure
tells whether a battery's own reaction is too fast or too slow.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

WINDOW = timedelta(minutes=10)
ERROR_W = 100.0  # an error at least this big counts for a crossing
OSCILLATING_CROSSINGS = 8  # per WINDOW, with at least as many reversals
SLUGGISH_W = 150.0  # mean absolute error while the batteries had room
MIN_ROUNDS = 12  # fewer rounds in WINDOW: idle

STATES = ("stable", "oscillating", "sluggish", "idle")


@dataclass(frozen=True, slots=True)
class _Round:
    when: datetime
    error_w: float
    power_w: float


class ControlQuality:
    """The control quality over the last ``WINDOW``."""

    def __init__(self) -> None:
        """Initialize."""
        self._rounds: deque[_Round] = deque()

    def add(self, when: datetime, error_w: float, power_w: float) -> None:
        """A round in which the batteries could follow: its error and the
        batteries' total power (+ charging)."""
        self._rounds.append(_Round(when, error_w, power_w))
        self._prune(when)

    def _prune(self, now: datetime) -> None:
        while self._rounds and now - self._rounds[0].when > WINDOW:
            self._rounds.popleft()

    def summary(self, now: datetime) -> dict[str, float | int | str]:
        """State and its figures (sensor, panel, diagnostics)."""
        self._prune(now)
        rounds = list(self._rounds)
        crossings = reversals = 0
        sign = 0
        for r in rounds:
            if abs(r.error_w) >= ERROR_W:
                new = 1 if r.error_w > 0 else -1
                if sign and new != sign:
                    crossings += 1
                sign = new
        step_sign = 0
        for a, b in pairwise(rounds):
            delta = b.power_w - a.power_w
            if abs(delta) >= ERROR_W:
                new = 1 if delta > 0 else -1
                if step_sign and new != step_sign:
                    reversals += 1
                step_sign = new
        mean = sum(abs(r.error_w) for r in rounds) / len(rounds) if rounds else 0.0
        if len(rounds) < MIN_ROUNDS:
            state = "idle"
        elif crossings >= OSCILLATING_CROSSINGS and reversals >= OSCILLATING_CROSSINGS:
            state = "oscillating"
        elif mean >= SLUGGISH_W:
            state = "sluggish"
        else:
            state = "stable"
        return {
            "state": state,
            "rounds": len(rounds),
            "mean_error_w": round(mean),
            "crossings": crossings,
            "reversals": reversals,
        }
