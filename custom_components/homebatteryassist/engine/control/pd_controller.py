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
  the new power is at least this much; below it the batteries stop (the
  direction is remembered, so it does not flap at low power).

Never against what zero on the meter wants: when it wants no discharge (a
surplus, or a rule such as the discharge price) the output does not
discharge, and the other way round. An extra round (a jump, an overload)
counts as part of a round (``scale``), so the gains stay per reaction
interval.

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
        self._direction = 0  # last direction: 1 charging, -1 discharging

    def reset(self) -> None:
        """Forget the previous error and direction (another mode ran in
        between, or the meter was gone)."""
        self._previous_error = None
        self._direction = 0

    def step(
        self,
        ideal_w: float,
        actual_w: float,
        command_w: float | None = None,
        scale: float = 1.0,
    ) -> float:
        """The new total command from what zero on the meter wants
        (``ideal_w``), what the batteries do now (``actual_w``) and the
        previous command (``command_w``; None: the actual power). ``scale``:
        the part of a reaction interval since the previous step (0..1)."""
        s = self.settings
        scale = max(0.0, min(scale, 1.0))
        current_w = actual_w if command_w is None else command_w
        error = ideal_w - actual_w
        change = 0.0 if self._previous_error is None else error - self._previous_error
        self._previous_error = error
        delta = scale * (s.kp * error + s.kd * change)
        if s.max_step_w > 0:
            most = s.max_step_w * scale
            delta = max(-most, min(most, delta))
        new = current_w + delta
        # Never against what zero on the meter wants.
        if ideal_w >= 0:
            new = max(new, 0.0)
        if ideal_w <= 0:
            new = min(new, 0.0)
        direction = (new > 0) - (new < 0)
        last = self._direction or (current_w > 0) - (current_w < 0)
        if (
            s.hysteresis_w > 0
            and direction
            and last
            and direction != last
            # What zero on the meter wants the other way (not this round's
            # step, else the dead band would be hysteresis / Kp).
            and abs(ideal_w) < s.hysteresis_w
        ):
            new, direction = 0.0, 0  # no change of direction for a small power
        if direction:
            self._direction = direction
        return new
