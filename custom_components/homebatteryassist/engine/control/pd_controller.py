"""PD control of zero on the meter (proportional-derivative).

Zero on the meter as it is now ("direct") sets the batteries every round to
what the grid asks: the measured grid without them (``nom_balance``). That is
only exact when the batteries do what they are told at once. A real battery
reacts with a delay and ramps its power, and the meter sees the result a few
seconds later: setting the full difference every round then overshoots and
oscillates. A PD controller steers towards the target in steps instead:

    error = ideal - actual       (W: what zero on the meter wants minus what
                                  the batteries do now, as the meter sees it)
    new   = previous command + Kp * error + Kd * (error - previous error)

Built on the previous *command*, as a real controller does: while a battery
still ramps towards it, the meter shows the old shortage, so "direct"
(Kp 1, Kd 0) adds it again and overshoots; a lower Kp and the derivative damp
that. Without a delay (actual = previous command) direct is exactly the ideal.

- ``kp`` (proportional): how much of the error is closed per round (1 = all,
  as direct);
- ``kd`` (derivative): reacts to how fast the error changes, damping an
  overshoot;
- ``max_step_w``: the most the power changes in one round (0 = no limit);
- ``hysteresis_w``: a change of direction (charge <-> discharge) only when
  the new power is at least this much; below it the batteries stop.

The round is the reaction interval (``react_interval_s``). Used by the
virtual batteries now (option ``nom_control`` = ``pd``), and the same class is
meant for real control later. The effect shows in the control quality
(``control_quality``: stable, oscillating, sluggish), together with a
simulated battery reaction (``devices/batteries/response.py``).
"""

from __future__ import annotations

from dataclasses import dataclass

CONTROL_DIRECT = "direct"
CONTROL_PD = "pd"
CONTROLS = (CONTROL_DIRECT, CONTROL_PD)

DEFAULT_KP = 0.35
DEFAULT_KD = 0.30
DEFAULT_MAX_STEP_W = 800
DEFAULT_HYSTERESIS_W = 60


@dataclass(frozen=True, slots=True)
class PdSettings:
    """The controller's settings."""

    kp: float = DEFAULT_KP
    kd: float = DEFAULT_KD
    max_step_w: float = DEFAULT_MAX_STEP_W
    hysteresis_w: float = DEFAULT_HYSTERESIS_W


class PdController:
    """One PD loop over the batteries' total power (W, + charging)."""

    def __init__(self, settings: PdSettings) -> None:
        """Initialize."""
        self.settings = settings
        self._previous_error: float | None = None

    def reset(self) -> None:
        """Forget the previous error (another mode ran in between)."""
        self._previous_error = None

    def step(
        self, ideal_w: float, actual_w: float, command_w: float | None = None
    ) -> float:
        """The new total command from what zero on the meter wants
        (``ideal_w``), what the batteries do now (``actual_w``) and the
        previous command (``command_w``; None: the actual power)."""
        s = self.settings
        current_w = actual_w if command_w is None else command_w
        error = ideal_w - actual_w
        change = 0.0 if self._previous_error is None else error - self._previous_error
        self._previous_error = error
        delta = s.kp * error + s.kd * change
        if s.max_step_w > 0:
            delta = max(-s.max_step_w, min(s.max_step_w, delta))
        new = current_w + delta
        if s.hysteresis_w > 0 and new * current_w < 0 and abs(new) < s.hysteresis_w:
            new = 0.0  # no change of direction for a small power
        return new
