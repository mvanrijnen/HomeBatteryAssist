"""Tests for the control layer (built, not active)."""

from datetime import datetime, timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.control.battery_controller import (
    BatteryController,
    ControlDisabled,
    ControlState,
    decide,
)
from custom_components.homebatteryassist.engine.devices.batteries.direct.base import (
    DirectBatteryDriver,
)

T0 = datetime(2026, 11, 16, 12, 0, tzinfo=dt_util.UTC)
S = timedelta(seconds=1)


class FakeDriver(DirectBatteryDriver):
    """Records commands; can fail."""

    name = "Fake"
    max_charge_w = 2500.0
    max_discharge_w = 2500.0

    def __init__(self, **hints) -> None:
        super().__init__(None, "fake")
        self.calls: list[tuple[str, float | None]] = []
        self.fail = False
        for key, value in hints.items():
            setattr(self, key, value)

    async def async_set_power(self, power_w: float) -> None:
        if self.fail:
            raise OSError("broken")
        self.calls.append(("set", power_w))

    async def async_release(self) -> None:
        self.calls.append(("release", None))


async def test_switched_off_sends_nothing() -> None:
    """While control is off nothing reaches the battery."""
    driver = FakeDriver()
    controller = BatteryController(driver)
    with pytest.raises(ControlDisabled):
        await controller.async_command(1000, T0)
    await controller.async_tick(T0)
    await controller.async_stop()
    assert driver.calls == []


async def test_limits_refresh_and_watchdog() -> None:
    driver = FakeDriver(refresh_s=30)
    controller = BatteryController(
        driver, enabled=True, watchdog=timedelta(minutes=2), limits=(2000, 9999)
    )
    await controller.async_command(5000, T0)  # above the caller's limit
    assert driver.calls == [("set", 2000)]
    await controller.async_tick(T0 + 10 * S)  # nothing new
    await controller.async_tick(T0 + 31 * S)  # refresh
    assert driver.calls[-1] == ("set", 2000) and len(driver.calls) == 2
    await controller.async_tick(T0 + 3 * 60 * S)  # no new target: watchdog
    assert driver.calls[-1] == ("release", None)
    assert not controller.state.active


async def test_throttle_and_direction() -> None:
    driver = FakeDriver(min_interval_s=20, deadband_w=250)
    controller = BatteryController(driver, enabled=True)
    await controller.async_command(1000, T0)
    await controller.async_command(1100, T0 + 5 * S)  # within deadband / interval
    await controller.async_command(1500, T0 + 10 * S)  # too soon
    assert driver.calls == [("set", 1000)]
    await controller.async_command(1500, T0 + 21 * S)  # allowed now
    await controller.async_command(-800, T0 + 22 * S)  # direction change: at once
    assert driver.calls == [("set", 1000), ("set", 1500), ("set", -800)]


async def test_idle_is_release_and_errors() -> None:
    driver = FakeDriver(idle_is_release=True)
    controller = BatteryController(driver, enabled=True)
    await controller.async_command(1000, T0)
    await controller.async_command(0, T0 + S)  # idle: release, not 0 W
    assert driver.calls == [("set", 1000), ("release", None)]
    driver.fail = True
    await controller.async_command(500, T0 + 2 * S)  # failing command: release
    assert driver.calls[-1] == ("release", None)
    assert controller.errors == 1 and not controller.state.active


async def test_stop_and_switch_off_release() -> None:
    driver = FakeDriver()
    controller = BatteryController(driver, enabled=True)
    await controller.async_command(-600, T0)
    controller.enabled = False  # switched off while active
    await controller.async_tick(T0 + S)
    assert driver.calls[-1] == ("release", None)
    controller.enabled = True
    await controller.async_command(300, T0 + 2 * S)
    await controller.async_stop()
    assert driver.calls[-1] == ("release", None)


def test_decide_without_target() -> None:
    """Nothing to do when idle and not in control."""
    assert decide(ControlState(), FakeDriver(), T0, timedelta(minutes=2)) is None
