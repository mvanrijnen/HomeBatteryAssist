"""HomeBatteryAssist is read-only: nothing may control a battery or device.

These checks fail as soon as code outside the drivers and the (inactive)
control layer calls a write method, creates a controller, enables a direct
driver or calls a Home Assistant action that changes a device.
"""

import re
from pathlib import Path

from custom_components.homebatteryassist.engine.devices.batteries import (
    DIRECT_DRIVERS,
    READERS,
)

PACKAGE = Path(__file__).parent.parent / "custom_components" / "homebatteryassist"
# Where write methods are *defined* (and, behind switches that are off, called).
DEFINITIONS = (
    "engine/control/",
    "engine/devices/transports/",
    "engine/devices/batteries/",
)
FORBIDDEN = re.compile(
    r"async_set_power\(|async_release\(|BatteryController\(|"
    r"\.enabled\s*=\s*True|write_registers?\(|mqtt\.async_publish"
)
# Home Assistant actions that are allowed: notifications, reading prices and
# reading the weather forecast.
ALLOWED_ACTION_FILES = (
    "engine/explain/notifications.py",
    "engine/sources/prices/ha_price_actions.py",
    "engine/sources/prices/template.py",
    "engine/sources/weather/ha_weather_entity.py",  # weather.get_forecasts
)


def _files():
    for path in PACKAGE.rglob("*.py"):
        if "__pycache__" not in path.parts:
            yield path.relative_to(PACKAGE).as_posix(), path.read_text(encoding="utf-8")


def test_nothing_calls_control() -> None:
    offenders = [
        name
        for name, text in _files()
        if not name.startswith(DEFINITIONS) and FORBIDDEN.search(text)
    ]
    assert offenders == []


def test_no_device_actions() -> None:
    offenders = [
        name
        for name, text in _files()
        if "services.async_call(" in text
        and not name.startswith("engine/devices/batteries/")
        and name not in ALLOWED_ACTION_FILES
    ]
    assert offenders == []


def test_direct_drivers_disabled() -> None:
    assert DIRECT_DRIVERS
    assert not any(driver.enabled for driver in DIRECT_DRIVERS)


def test_controller_off_by_default() -> None:
    import inspect

    from custom_components.homebatteryassist.engine.control.battery_controller import (
        BatteryController,
    )

    default = inspect.signature(BatteryController).parameters["enabled"].default
    assert default is False
    assert READERS  # readers only read (their write methods are never called)


def test_control_loop_is_only_comment() -> None:
    """The control loop is written out as comment: no active code at all."""
    import ast

    tree = ast.parse((PACKAGE / "engine/control/control_loop.py").read_text("utf-8"))
    assert len(tree.body) == 1  # the docstring
    assert isinstance(tree.body[0], ast.Expr)


def test_control_test_switched_off() -> None:
    """The test control per battery is built, but sends nothing in this phase."""
    from custom_components.homebatteryassist.engine.control.control_test import (
        CONTROL_TEST_ALLOWED,
    )

    assert CONTROL_TEST_ALLOWED is False


def test_export_limit_sends_nothing() -> None:
    """The export limit is shown and explained; no inverter driver is
    enabled and none implements sending yet."""
    import asyncio

    import pytest

    from custom_components.homebatteryassist.engine.control.export_limiter import (
        CONTROL,
    )
    from custom_components.homebatteryassist.engine.devices.inverters import DRIVERS

    assert CONTROL is False
    for driver in DRIVERS:
        assert driver.enabled is False
        with pytest.raises(NotImplementedError):
            asyncio.run(driver.async_set_limit(None, "1.2.3.4", 0))  # type: ignore[arg-type]
