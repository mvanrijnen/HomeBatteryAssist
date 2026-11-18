"""Tests for the check whether a battery follows its command."""

from datetime import UTC, datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist.engine.devices.batteries import (
    BatteryCommand,
    command,
)
from custom_components.homebatteryassist.engine.evaluation.command_check import (
    CommandCheck,
    follows,
    reason_for,
)
from custom_components.homebatteryassist.engine.explain.messages import (
    MESSAGES,
    render,
)
from custom_components.homebatteryassist.engine.explain.notifications import kind_of
from custom_components.homebatteryassist.engine.measure.battery_monitor import (
    BatteryConfig,
)

T0 = datetime(2026, 11, 18, 3, 0, tzinfo=UTC)
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


def _run(check, start, minutes, cmd, soc, actual, step=15):
    """Updates every ``step`` seconds; the messages logged."""
    told = []
    for i in range(int(minutes * 60 / step) + 1):
        result = check.update(
            start + timedelta(seconds=i * step), cmd, soc, actual, CONFIG
        )
        if result is not None:
            told.append(result)
    return told


def test_follows() -> None:
    assert follows(1000, 600)
    assert not follows(1000, 400)
    assert not follows(1000, -800)  # the wrong way
    assert follows(-1000, -700)
    assert not follows(-1000, 0)
    # Against the maximum power when that is lower than the command.
    assert follows(3000, 1300, 2500)


def test_reasons() -> None:
    charge = BatteryCommand(1500)
    assert reason_for(charge, 50, CONFIG) is None
    assert reason_for(charge, 99.5, CONFIG) == "full"
    off = BatteryCommand(1500, charge_allowed=False)
    assert reason_for(off, 50, CONFIG) == "charge_off"
    held = BatteryCommand(1500, hysteresis=True)
    assert reason_for(held, 98, CONFIG) == "hysteresis"
    assert reason_for(BatteryCommand(-800), 12.5, CONFIG) == "empty"
    no_discharge = BatteryCommand(-800, discharge_allowed=False)
    assert reason_for(no_discharge, 50, CONFIG) == "discharge_off"


def test_not_following_told_after_a_while_and_ended() -> None:
    check = CommandCheck(100, timedelta(minutes=2))
    cmd = BatteryCommand(2000)
    assert _run(check, T0, 1.5, cmd, 40, 0.0) == []  # starting up: no message
    told = _run(check, T0 + timedelta(seconds=105), 1, cmd, 40, 0.0)
    assert [key for key, _ in told] == ["battery_not_following"]
    params = told[0][1]
    assert params["command"] == "2000 W" and params["actual"] == "0 W"
    assert params["direction"] == "@dir_charge" and params["since"] == T0
    assert check.problem and check.as_dict()["problem"]
    # Following again: over after a minute.
    later = T0 + timedelta(minutes=5)
    told = _run(check, later, 1.5, cmd, 40, 1900.0)
    assert [key for key, _ in told] == ["battery_not_following_ended"]
    assert not check.problem and check.event is None


def test_a_short_lag_is_no_message() -> None:
    check = CommandCheck(100, timedelta(minutes=2))
    cmd = BatteryCommand(-1500)
    told = []
    for i in range(40):  # 10 minutes, following again every 4th look
        actual = -1400.0 if i % 4 == 0 else 0.0
        result = check.update(T0 + timedelta(seconds=i * 15), cmd, 60, actual, CONFIG)
        if result:
            told.append(result)
    assert told == [] and check.event is None


def test_small_or_unknown_is_not_checked() -> None:
    check = CommandCheck(100, timedelta(minutes=2))
    assert _run(check, T0, 5, BatteryCommand(60), 40, 0.0) == []
    assert _run(check, T0, 5, None, 40, 0.0) == []
    assert _run(check, T0, 5, BatteryCommand(500), 40, None) == []


def test_explained_is_no_problem() -> None:
    check = CommandCheck(100, timedelta(minutes=2))
    told = _run(check, T0, 3, BatteryCommand(1000), 100, 0.0)
    assert [key for key, _ in told] == ["battery_not_following_explained"]
    assert told[0][1]["reason"] == "@reason_full"
    assert check.event is not None and not check.problem
    # No "ended" for an explained one.
    assert _run(check, T0 + timedelta(minutes=4), 2, None, 100, 0.0) == []
    assert check.event is None


def test_explained_then_a_problem() -> None:
    check = CommandCheck(100, timedelta(minutes=2))
    _run(check, T0, 3, BatteryCommand(1000, hysteresis=True), 98, 0.0)
    later = T0 + timedelta(minutes=3, seconds=15)
    told = _run(check, later, 1, BatteryCommand(1000), 98, 0.0)
    assert [key for key, _ in told] == ["battery_not_following"]
    assert check.problem


def test_messages_and_notification_kind() -> None:
    for lang in MESSAGES:
        text = render(
            lang,
            "battery_not_following_explained",
            {
                "name": "Venus",
                "direction": "@dir_discharge",
                "command": "800 W",
                "actual": "0 W",
                "since": T0,
                "reason": "@reason_empty",
            },
        )
        assert "@" not in text and "{" not in text
    assert kind_of("battery_not_following") == "battery_command"
    assert kind_of("battery_not_following_ended") == "battery_command"
    assert kind_of("battery_not_following_explained") is None


async def test_command_read_from_omnibattery(hass: HomeAssistant) -> None:
    """The command Omnibattery gives the battery, from its device's entities."""
    source = MockConfigEntry(domain="omnibattery")
    source.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=source.entry_id, identifiers={("omnibattery", "v1")}
    )
    registry = er.async_get(hass)
    values = {
        ("sensor", "battery_soc"): "40",
        ("switch", "rs485_control_mode"): "on",
        ("select", "force_mode"): "Discharge",
        ("number", "set_charge_power"): "0",
        ("number", "set_discharge_power"): "800",
        ("switch", "battery_allow_charge"): "on",
        ("switch", "battery_allow_discharge"): "off",
        ("binary_sensor", "charge_hysteresis_active"): "off",
    }
    ids = {}
    for (domain, key), value in values.items():
        entry = registry.async_get_or_create(
            domain,
            "omnibattery",
            f"v1_{key}",
            device_id=device.id,
            translation_key=key,
            suggested_object_id=f"venus_{key}",
        )
        ids[key] = entry.entity_id
        hass.states.async_set(entry.entity_id, value)
    assert command(hass, CONFIG) == BatteryCommand(-800.0, True, False, False)
    hass.states.async_set(ids["force_mode"], "Charge")
    hass.states.async_set(ids["set_charge_power"], "1500")
    assert command(hass, CONFIG).power_w == 1500.0
    hass.states.async_set(ids["force_mode"], "None")
    assert command(hass, CONFIG).power_w == 0.0
    # External control off: the battery controls itself, no command.
    hass.states.async_set(ids["rs485_control_mode"], "off")
    assert command(hass, CONFIG) is None
