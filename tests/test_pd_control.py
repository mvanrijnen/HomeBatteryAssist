"""PD control of zero on the meter and the simulated battery reaction."""

from datetime import datetime, timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.control.pd_controller import (
    PdController,
    PdSettings,
)
from custom_components.homebatteryassist.engine.devices.batteries.response import (
    BatteryResponse,
)

T0 = datetime(2026, 11, 21, 12, tzinfo=dt_util.UTC)


def test_pd_like_direct_with_full_gain() -> None:
    """Kp 1 and Kd 0 without limits: at once what zero on the meter wants."""
    pd = PdController(PdSettings(kp=1.0, kd=0.0, max_step_w=0, hysteresis_w=0))
    assert pd.step(-1200.0, 0.0) == -1200.0
    assert pd.step(300.0, -1200.0) == 300.0


def test_pd_steps_limits_and_damping() -> None:
    """Part of the difference per round, at most max_step; the derivative
    damps when the difference shrinks."""
    pd = PdController(PdSettings(kp=0.5, kd=0.0, max_step_w=400, hysteresis_w=0))
    assert pd.step(-2000.0, 0.0) == -400.0  # 0.5 x 2000 = 1000, capped
    assert pd.step(-2000.0, -400.0) == -800.0
    damped = PdController(PdSettings(kp=0.5, kd=0.3, max_step_w=0, hysteresis_w=0))
    first = damped.step(-1000.0, 0.0)  # no previous error: P only
    assert first == pytest.approx(-500.0)
    # The error went from -1000 to -500: the derivative (+500 x 0.3) slows it.
    assert damped.step(-1000.0, first) == pytest.approx(-500.0 - 250.0 + 150.0)


def test_pd_direction_hysteresis() -> None:
    """A small power the other way stops the batteries instead."""
    pd = PdController(PdSettings(kp=1.0, kd=0.0, max_step_w=0, hysteresis_w=60))
    assert pd.step(40.0, -100.0) == 0.0  # would be +40 W charging: stop
    pd.reset()
    assert pd.step(200.0, -100.0) == 200.0


def test_response_delay_and_ramp() -> None:
    """A new power is followed after the delay, then ramped."""
    at_once = BatteryResponse()
    assert at_once.apply(T0, 800.0) == 800.0
    delayed = BatteryResponse(delay_s=10, ramp_w_s=100)
    assert delayed.apply(T0, 1000.0) == 0.0
    assert delayed.apply(T0 + timedelta(seconds=5), 1000.0) == 0.0  # not yet
    assert delayed.apply(T0 + timedelta(seconds=10), 1000.0) == 500.0  # 5 s x 100
    assert delayed.apply(T0 + timedelta(seconds=15), 1000.0) == 1000.0
    delayed.hold(400.0, T0 + timedelta(seconds=20))  # e.g. it got full
    assert delayed.apply(T0 + timedelta(seconds=21), 1000.0) == 500.0


def _simulate(settings: PdSettings) -> dict:
    """A house using 1500 W and a battery that follows after 10 s at
    200 W/s, controlled every 5 s; the control quality over the run."""
    from custom_components.homebatteryassist.engine.devices.batteries.control_quality import (
        ControlQuality,
    )

    pd = PdController(settings)
    response = BatteryResponse(delay_s=10, ramp_w_s=200)
    quality = ControlQuality()
    command: float | None = None
    actual = 0.0
    house = 1500.0
    when = T0
    for i in range(120):
        when = T0 + timedelta(seconds=5 * i)
        command = max(-2500.0, min(2500.0, pd.step(-house, actual, command)))
        actual = response.apply(when, command)
        quality.add(when, house + actual, actual)
    return quality.summary(when)


def test_direct_overshoots_a_slow_battery_pd_does_not() -> None:
    """With a delayed battery, direct (full gain) keeps overshooting; the PD
    defaults settle at zero on the meter."""
    direct = _simulate(PdSettings(kp=1.0, kd=0.0, max_step_w=0, hysteresis_w=0))
    assert direct["state"] == "oscillating"
    pd = _simulate(PdSettings())
    assert pd["state"] == "stable"
    assert pd["mean_error_w"] < 100


def test_pd_never_against_zero_on_the_meter() -> None:
    """When zero on the meter wants nothing (e.g. discharging is blocked by
    the price), the derivative never turns the batteries the other way."""
    pd = PdController(PdSettings())
    pd.step(2500.0, 500.0, 500.0)
    assert pd.step(0.0, 500.0, 500.0) == 0.0
    assert PdController(PdSettings()).step(-800.0, 300.0, 300.0) <= 0.0
