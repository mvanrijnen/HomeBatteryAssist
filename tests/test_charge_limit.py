"""A battery that limits its charge power itself (e.g. on a cold night): no
alarm, the plans count on what it does, and the learning is saved while
running."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from homeassistant.core import HomeAssistant

from custom_components.homebatteryassist.engine.control.control_loop import ControlLoop
from custom_components.homebatteryassist.engine.coordinator import ForecastCoordinator
from custom_components.homebatteryassist.engine.db_store import SaveThrottle
from custom_components.homebatteryassist.engine.devices.batteries import (
    BatteryCommand,
)
from custom_components.homebatteryassist.engine.evaluation.battery_temperature import (
    LIMIT_KEEP,
    BatteryTemperature,
)
from custom_components.homebatteryassist.engine.evaluation.command_check import (
    CommandCheck,
    reason_for,
)
from custom_components.homebatteryassist.engine.explain.messages import render
from custom_components.homebatteryassist.engine.explain.plan_summary import (
    plan_summary,
)
from custom_components.homebatteryassist.engine.measure.battery_monitor import (
    BatteryConfig,
)

T0 = datetime(2026, 11, 25, 22, 0, tzinfo=UTC)
LOOK = timedelta(seconds=15)
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


def test_part_of_the_power_is_explained() -> None:
    """810 W of 2500 W: the battery limits it itself; nothing at all, or the
    wrong way, is still a problem."""
    charge = BatteryCommand(2500)
    assert reason_for(charge, 70, CONFIG, 12.0, 810.0) == "limited"
    assert reason_for(charge, 70, CONFIG, 12.0, 0.0) is None
    assert reason_for(charge, 70, CONFIG, 12.0, -500.0) is None
    assert reason_for(BatteryCommand(-2500), 50, CONFIG, 12.0, -700.0) == "limited"
    assert reason_for(BatteryCommand(-2500), 50, CONFIG, 12.0, 0.0) is None


def test_limited_charge_no_alarm() -> None:
    """A night of charging at 810 W: told once as explained, never a problem
    (the control loop keeps the battery)."""
    check = CommandCheck()
    told = []
    for i in range(40):
        result = check.update(
            T0 + i * LOOK, BatteryCommand(2500), 70.0, 810.0, CONFIG, 12.0
        )
        if result is not None:
            told.append(result[0])
        assert not check.problem
    assert told == ["battery_not_following_explained"]
    assert check.as_dict()["reason"] == "limited"


def _looks(battery, start, count, command_w, power, soc=60.0):
    for i in range(count):
        battery.observe(
            start + i * LOOK, CONFIG, BatteryCommand(command_w), soc, power, 12.0
        )


def test_charge_limit_learned_and_forgotten() -> None:
    """The charge power while limited: the median of a few minutes of looks
    (a single dip is no limit), kept ``LIMIT_KEEP``, forgotten once it
    charges at a command above it."""
    battery = BatteryTemperature()
    assert battery.charge_limit_w(T0) is None
    _looks(battery, T0, 5, 2500, 1620.0)
    assert battery.charge_limit_w(T0 + 5 * LOOK) is None  # not yet 2 minutes
    _looks(battery, T0 + 5 * LOOK, 5, 2500, 1620.0)
    assert battery.charge_limit_w(T0 + 10 * LOOK) == 1620.0
    # One look at 168 W (last night: it set the limit for hours): a dip.
    _looks(battery, T0 + 10 * LOOK, 1, 2500, 168.0)
    _looks(battery, T0 + 11 * LOOK, 2, 2500, 1620.0)
    assert battery.charge_limit_w(T0 + 13 * LOOK) == 1620.0
    # A lower step that lasts: followed within minutes.
    start = T0 + 13 * LOOK
    _looks(battery, start, 30, 2500, 810.0)
    assert battery.charge_limit_w(start + 30 * LOOK) == 810.0
    # A small command it follows says nothing about the limit.
    _looks(battery, start + 30 * LOOK, 5, 500, 500.0)
    assert battery.charge_limit_w(start + 35 * LOOK) == 810.0
    # Kept, and saved.
    again = BatteryTemperature.from_dict(battery.as_dict())
    assert again.charge_limit_w(start + 35 * LOOK) == 810.0
    assert battery.charge_limit_w(start + 30 * LOOK + LIMIT_KEEP) is None
    # Charging at the full command again: forgotten.
    _looks(battery, start + 40 * LOOK, 5, 2500, 2490.0)
    assert battery.charge_limit_w(start + 45 * LOOK) is None
    assert battery.summary()["charge_limit_w"] is None


def test_control_asks_full_power() -> None:
    """The limit is for the plans: a planned grid charge is asked of the
    battery in proportion up to its full power, so it takes what it can."""
    config = SimpleNamespace(id="b1", max_charge_w=2500.0)
    fake = SimpleNamespace(
        virtual=[config],
        _forecast=SimpleNamespace(
            power_limits={"b1": {"reason": "limited", "charge_w": 810}}
        ),
    )
    assert ControlLoop._unlimited(fake, 810.0) == 2500.0
    assert round(ControlLoop._unlimited(fake, 405.0)) == 1250
    assert ControlLoop._unlimited(fake, -500.0) == -500.0
    fake._forecast.power_limits = {"b1": {"reason": "warm", "charge_w": 1750}}
    assert ControlLoop._unlimited(fake, 1750.0) == 1750.0
    fake._forecast.power_limits = {}
    assert ControlLoop._unlimited(fake, 810.0) == 810.0


class _Log:
    def __init__(self) -> None:
        self.keys: list[tuple[str, dict[str, Any]]] = []

    def async_log(self, category: str, key: str, **params: Any) -> None:
        self.keys.append((key, params))


async def test_plans_use_the_charge_limit(hass: HomeAssistant) -> None:
    """The plans charge it at no more than the limit; told in *Why* and the
    summary, and ended when the limit is gone."""
    limit: dict[str, float | None] = {"b1": 810.0}
    fake = SimpleNamespace(
        hass=hass,
        temperature={"limit": 40.0, "band": 10.0, "min": 0.4, "discharge": False},
        _decisions=_Log(),
        _derating_told={},
        power_limits={},
        charge_limit=lambda battery_id: limit.get(battery_id),
    )
    config = SimpleNamespace(
        id="b1",
        name="Venus",
        temperature_sensor="sensor.venus_temp",
        max_charge_w=2500.0,
        max_discharge_w=2500.0,
    )
    hass.states.async_set("sensor.venus_temp", "12", {"unit_of_measurement": "°C"})
    state = SimpleNamespace(soc=60.0, config=config)

    def cycle() -> Any:
        derated = ForecastCoordinator._derated(fake, state)
        ForecastCoordinator._tell_derating(fake, [derated])
        return derated

    derated = cycle()
    assert round(derated.charge_factor * 2500) == 810
    assert derated.discharge_factor == 1.0
    assert fake.power_limits["b1"]["reason"] == "limited"
    assert fake.power_limits["b1"]["charge_w"] == 810
    cycle()  # told once
    assert [k for k, _ in fake._decisions.keys] == ["battery_charge_limited"]
    summary = plan_summary(
        None,
        [],
        T0,
        "nom",
        language="nl",
        power_limits=list(fake.power_limits.values()),
    )
    assert summary["power"] == (
        "Venus laadt nu met hooguit 810 W in plaats van 2500 W "
        "(beperkt door de batterij zelf)."
    )
    limit["b1"] = None
    assert cycle() is state
    assert [k for k, _ in fake._decisions.keys] == [
        "battery_charge_limited",
        "battery_charge_limited_ended",
    ]
    for lang in ("nl", "en"):
        for key, params in fake._decisions.keys:
            assert "{" not in render(lang, key, params)


async def test_save_throttle_saves_while_changing(hass: HomeAssistant) -> None:
    """Asked to save every 15 s with a delay of 600 s, it still asks the
    store once per delay (HA's delay alone moved the write on forever)."""
    calls: list[float] = []
    store = SimpleNamespace(async_delay_save=lambda func, delay: calls.append(delay))
    now = {"t": 1000.0}
    fake_hass = SimpleNamespace(loop=SimpleNamespace(time=lambda: now["t"]))
    save = SaveThrottle(fake_hass, store, dict, 600)
    for _ in range(100):  # 25 minutes of looks
        save()
        now["t"] += 15
    assert len(calls) == 3  # at 0, ~601 s and ~1202 s
