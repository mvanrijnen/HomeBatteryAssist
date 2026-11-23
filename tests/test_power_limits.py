"""A warm battery: told in *Why* and in the plan summary."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from homeassistant.core import HomeAssistant

from custom_components.homebatteryassist.engine.coordinator import ForecastCoordinator
from custom_components.homebatteryassist.engine.explain.messages import render
from custom_components.homebatteryassist.engine.explain.plan_summary import (
    plan_summary,
)


class _Log:
    def __init__(self) -> None:
        self.keys: list[tuple[str, dict[str, Any]]] = []

    def async_log(self, category: str, key: str, **params: Any) -> None:
        self.keys.append((key, params))


def _fake(hass: HomeAssistant, discharge: bool = False) -> SimpleNamespace:
    fake = SimpleNamespace(
        hass=hass,
        temperature={"limit": 40.0, "band": 10.0, "min": 0.4, "discharge": discharge},
        _decisions=_Log(),
        _derating_told={},
        power_limits={},
    )
    fake._derated = lambda state: ForecastCoordinator._derated(fake, state)
    return fake


def _state() -> SimpleNamespace:
    config = SimpleNamespace(
        id="b1",
        name="Venus",
        temperature_sensor="sensor.venus_temp",
        max_charge_w=2500.0,
        max_discharge_w=2500.0,
    )
    return SimpleNamespace(soc=50.0, config=config)


def _cycle(hass: HomeAssistant, fake: SimpleNamespace, celsius: float) -> None:
    hass.states.async_set(
        "sensor.venus_temp", str(celsius), {"unit_of_measurement": "°C"}
    )
    ForecastCoordinator._tell_derating(fake, [fake._derated(_state())])


async def test_warm_told_once_and_ended(hass: HomeAssistant) -> None:
    """Warm: told once with the powers; ended only 1 °C below the limit."""
    fake = _fake(hass)
    _cycle(hass, fake, 45.0)
    assert [k for k, _ in fake._decisions.keys] == ["battery_warm"]
    params = fake._decisions.keys[0][1]
    assert params["charge"] == 1750  # half the band: 1 - 0.5 x 0.6
    assert params["max_charge"] == 2500
    assert fake.power_limits["b1"]["charge_w"] == 1750
    assert fake.power_limits["b1"]["discharge_w"] == 2500
    _cycle(hass, fake, 46.0)  # still warm: not told again
    assert len(fake._decisions.keys) == 1
    _cycle(hass, fake, 39.5)  # full power, but just below the limit
    assert fake.power_limits == {}
    assert len(fake._decisions.keys) == 1
    _cycle(hass, fake, 38.5)
    assert [k for k, _ in fake._decisions.keys] == [
        "battery_warm",
        "battery_warm_ended",
    ]
    for lang in ("nl", "en"):
        for key, params in fake._decisions.keys:
            assert "{" not in render(lang, key, params)


async def test_warm_discharge_too(hass: HomeAssistant) -> None:
    """With the discharge derated too, both powers are told."""
    fake = _fake(hass, discharge=True)
    _cycle(hass, fake, 50.0)
    assert fake._decisions.keys[0][0] == "battery_warm_both"
    assert fake.power_limits["b1"]["discharge_w"] == 1000


def test_power_line_in_summary() -> None:
    """The summary has a *Power* line right after *Now*."""
    info = {
        "name": "Venus",
        "reason": "warm",
        "temperature_c": 45.0,
        "charge_w": 1750,
        "max_charge_w": 2500,
        "discharge_w": 2500,
        "max_discharge_w": 2500,
    }
    nl = plan_summary(None, [], _now(), "nom", language="nl", power_limits=[info])
    assert nl["power"] == (
        "Venus is warm (45,0 °C): laden met hooguit 1750 W in plaats van 2500 W."
    )
    assert [line["key"] for line in nl["lines"]][:2] == ["now", "power"]
    en = plan_summary(None, [], _now(), "nom", language="en")
    assert en["power"] is None


def _now():
    from datetime import UTC, datetime

    return datetime(2026, 11, 23, 12, tzinfo=UTC)
