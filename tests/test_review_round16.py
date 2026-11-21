"""Review round 16: control safety before the supervised test, and more."""

import asyncio
from types import SimpleNamespace

from homeassistant.core import HomeAssistant

from custom_components.homebatteryassist.engine.control import control_test
from custom_components.homebatteryassist.engine.control.battery_controller import (
    BatteryController,
)
from custom_components.homebatteryassist.engine.control.control_test import ControlTest

from .test_battery_controller import T0, FakeDriver
from .test_control_test import CONFIG, FakeLog, FakeReader, _batteries


async def test_stop_while_a_command_is_sent_releases() -> None:
    """A stop while the command is still being sent: the battery is
    released once that command returns (never left forced)."""
    gate = asyncio.Event()

    class Slow(FakeDriver):
        async def async_set_power(self, power_w: float) -> None:
            await gate.wait()
            self.calls.append(("set", power_w))

    driver = Slow()
    controller = BatteryController(driver, enabled=True)
    task = asyncio.ensure_future(controller.async_command(1000, T0))
    await asyncio.sleep(0)
    await controller.async_stop()  # while the set is in flight
    gate.set()
    await task
    assert driver.calls[-1] == ("release", None)
    assert not controller.state.active
    count = len(driver.calls)
    await controller.async_command(1000, T0)  # stopped: nothing more
    assert len(driver.calls) == count


async def test_failed_release_is_retried(hass: HomeAssistant, monkeypatch) -> None:
    """A test whose release fails stays to be released: retried every tick
    until it works (the battery must not stay forced)."""

    class FlakyReader(FakeReader):
        def __init__(self) -> None:
            super().__init__()
            self.fail = 1

        async def async_release(self, hass, config) -> None:
            if self.fail:
                self.fail -= 1
                raise OSError("busy")
            await super().async_release(hass, config)

    reader = FlakyReader()
    monkeypatch.setattr(control_test, "reader_for", lambda hass, config: reader)
    test = ControlTest(hass, _batteries(50), FakeLog(), allowed=True)
    await test.async_start("b1", charge=True)
    await test.async_stop("b1")
    assert "b1" in test.releasing  # the release failed
    await test._async_tick(T0)
    assert "b1" not in test.releasing
    assert reader.calls[-1] == ("release",)


async def test_released_battery_is_not_redistributed() -> None:
    """A battery the interceptor releases covers its load itself: its part
    is not handed to the others too."""
    from custom_components.homebatteryassist.engine.control.interceptors import (
        run_interceptor,
    )
    from custom_components.homebatteryassist.engine.control.interceptors.base import (
        RELEASE,
        Decision,
        Interceptor,
        InterceptResult,
    )

    class Release(Interceptor):
        key = "release_a"

        def intercept(self, data):
            return InterceptResult([Decision("a", RELEASE)], redistribute=True)

    def proposal(bid, power):
        return SimpleNamespace(
            id=bid,
            soc=50.0,
            max_soc=100.0,
            min_soc=10.0,
            floor_soc=None,
            max_charge_w=2000.0,
            max_discharge_w=2000.0,
            full_charge=False,
            reason="zero_on_meter",
            proposed_w=power,
        )

    data = SimpleNamespace(batteries=[proposal("a", -1000.0), proposal("b", -500.0)])
    outcome = run_interceptor(Release(), data)
    assert "a" in outcome.released
    assert outcome.powers["b"] == -500.0


async def test_omnibattery_powers_before_manual_mode(monkeypatch) -> None:
    """Powers first (the other direction to 0 first), then manual mode; no
    manual mode switch: nothing is written."""
    import pytest

    from custom_components.homebatteryassist.engine.devices.batteries.integrations import (
        omnibattery_integration as omni,
    )

    calls = []

    async def fake_call(domain, service, data, blocking=False):
        calls.append((domain, service, data.get("entity_id"), data.get("value")))

    hass = SimpleNamespace(services=SimpleNamespace(async_call=fake_call))
    entities = {
        ("switch", "battery_manual_mode"): "switch.manual",
        ("number", "set_charge_power"): "number.charge",
        ("number", "set_discharge_power"): "number.discharge",
    }
    from custom_components.homebatteryassist.engine.devices.batteries.integrations import (
        entity_reader,
    )

    monkeypatch.setattr(omni, "device_entities", lambda hass, config: entities)
    monkeypatch.setattr(entity_reader, "device_entities", lambda hass, config: entities)
    reader = omni.OmnibatteryReader()
    await reader.async_set_power(hass, CONFIG, 1500.0)
    assert [c[2] for c in calls] == [
        "number.discharge",
        "number.charge",
        "switch.manual",
    ]
    assert calls[0][3] == 0.0 and calls[1][3] == 1500.0
    calls.clear()
    del entities[("switch", "battery_manual_mode")]
    with pytest.raises(RuntimeError):
        await reader.async_set_power(hass, CONFIG, 1500.0)
    assert calls == []


async def test_twin_hold_told_only_when_it_lasts() -> None:
    """A twinned real battery unknown for a moment (its integration loading
    after HomeBatteryAssist) holds, but Why tells it only after a while."""
    from dataclasses import replace as dataclass_replace
    from datetime import timedelta

    from custom_components.homebatteryassist.engine.measure.battery_monitor import (
        BatteryState,
    )

    from .test_review_round13 import T1, _sim

    sim, batteries = _sim([1000.0], {"A": "l1"})
    real = SimpleNamespace(id="R", name="Real", virtual=False, twin_of="", phase="l1")
    batteries.configs[0] = dataclass_replace(batteries.configs[0], twin_of="R")
    batteries.configs.append(real)
    batteries.states["R"] = BatteryState(real, 50.0, None)
    logged = []
    sim._decisions = SimpleNamespace(async_log=lambda *a, **k: logged.append(a[1]))
    sim.step(T1 + timedelta(seconds=5))
    assert batteries.states["A"].power_w == 0.0
    assert "twin_real_unknown_hold" not in logged  # not yet: a moment


def test_diagnostics_mask_a_numeric_serial() -> None:
    from custom_components.homebatteryassist.diagnostics import _addresses, _mask

    entry = SimpleNamespace(
        data={"meter_address": "1900123456"}, options={}, subentries={}
    )
    result = _mask(
        {"meter": {"serial": 1900123456, "1900123456": 1}}, _addresses(entry)
    )
    assert "1900123456" not in str(result)


def test_pd_restart_keeps_the_real_measurement() -> None:
    """After a restart from protection, the next step's derivative uses what
    the batteries really did (no kick from a planted ideal)."""
    from custom_components.homebatteryassist.engine.control.pd_controller import (
        PdController,
        PdSettings,
    )

    pd = PdController(PdSettings(kp=0.0, kd=0.5, max_step_w=0, hysteresis_w=0))
    pd.restart(-500.0)
    assert pd.step(-2000.0, -500.0, -2000.0) == -2000.0  # no change: no kick
