"""Tests for the test control (switched off in this phase)."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.control import control_test
from custom_components.homebatteryassist.engine.control.control_test import (
    CONTROL_TEST_ALLOWED,
    ControlTest,
)
from custom_components.homebatteryassist.engine.measure.battery_monitor import (
    BatteryConfig,
    BatteryState,
)

CONFIG = BatteryConfig(
    id="b1",
    name="Venus",
    soc_sensor="sensor.venus_battery_soc",
    power_sensor="sensor.venus_ac_power",
    power_sign="discharging_positive",
    capacity_kwh=5.12,
    max_charge_w=2500,
    max_discharge_w=2500,
    min_soc=12,
    max_soc=100,
    efficiency=0.85,
    full_charge_interval_days=0,
    phase="l1",
)


class FakeReader:
    name = "Omnibattery"
    can_write = True

    def __init__(self) -> None:
        self.calls: list = []

    async def async_set_power(self, hass, config, power_w) -> None:
        self.calls.append(("set", power_w))

    async def async_release(self, hass, config) -> None:
        self.calls.append(("release",))


class FakeLog:
    def __init__(self) -> None:
        self.keys: list = []

    def async_log(self, category, key, **params) -> None:
        self.keys.append((key, params))


def _batteries(soc: float):
    return SimpleNamespace(
        configs=[CONFIG],
        states={"b1": BatteryState(CONFIG, soc, 0.0)},
        stats={"b1": {"charged_kwh": 1.0, "discharged_kwh": 0.5}},
    )


@pytest.fixture
def reader(monkeypatch) -> FakeReader:
    fake = FakeReader()
    monkeypatch.setattr(control_test, "reader_for", lambda hass, config: fake)
    return fake


def test_switched_off_in_this_phase() -> None:
    assert CONTROL_TEST_ALLOWED is False


async def test_blocked_while_switched_off(hass: HomeAssistant, reader) -> None:
    log = FakeLog()
    test = ControlTest(hass, _batteries(50), log)
    assert test.status("b1") == "read_only"
    await test.async_start("b1", charge=True)
    assert [k for k, _ in log.keys] == ["control_test_blocked"]
    assert reader.calls == [] and test.runs == {}


async def test_charge_for_the_test_duration(hass: HomeAssistant, reader) -> None:
    log = FakeLog()
    batteries = _batteries(50)
    test = ControlTest(hass, batteries, log, allowed=True)
    assert test.status("b1") == "ready"
    test.power_w["b1"] = 400
    test.minutes["b1"] = 2
    await test.async_start("b1", charge=True)
    assert reader.calls == [("set", 400)]
    assert test.status("b1") == "charging"
    assert log.keys[0][0] == "control_test_started"
    # Time is up: back to its own control, with what it charged.
    batteries.stats["b1"]["charged_kwh"] = 1.012
    await test._async_tick(dt_util.utcnow() + timedelta(minutes=3))
    assert reader.calls[-1] == ("release",)
    key, params = log.keys[-1]
    assert key == "control_test_stopped"
    assert params["reason"] == "@test_done" and params["charged"] == "0.01"
    assert test.runs == {} and test.status("b1") == "ready"


async def test_refused_when_full_or_empty(hass: HomeAssistant, reader) -> None:
    log = FakeLog()
    full = ControlTest(hass, _batteries(100), log, allowed=True)
    await full.async_start("b1", charge=True)
    empty = ControlTest(hass, _batteries(20), log, reserve_soc=lambda: 20, allowed=True)
    await empty.async_start("b1", charge=False)
    assert [(k, p["reason"]) for k, p in log.keys] == [
        ("control_test_refused", "@test_full"),
        ("control_test_refused", "@test_empty"),
    ]
    assert reader.calls == []


async def test_stops_when_not_followed(hass: HomeAssistant, reader) -> None:
    log = FakeLog()
    commands = SimpleNamespace(checks={"b1": SimpleNamespace(problem=False)})
    test = ControlTest(hass, _batteries(50), log, commands=commands, allowed=True)
    await test.async_start("b1", charge=False)
    assert reader.calls == [("set", -300.0)]
    commands.checks["b1"].problem = True
    await test._async_tick(dt_util.utcnow())
    assert reader.calls[-1] == ("release",)
    assert log.keys[-1][1]["reason"] == "@test_not_following"


async def test_stop_by_hand_and_on_unload(hass: HomeAssistant, reader) -> None:
    log = FakeLog()
    test = ControlTest(hass, _batteries(50), log, allowed=True)
    await test.async_start("b1", charge=True)
    await test.async_stop("b1")
    assert log.keys[-1][1]["reason"] == "@test_stopped"
    await test.async_start("b1", charge=True)
    await test.async_stop_all()
    assert log.keys[-1][1]["reason"] == "@test_unload"
    assert reader.calls.count(("release",)) == 2
