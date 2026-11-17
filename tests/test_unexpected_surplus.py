"""Tests for the unexpected solar surplus message."""

from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.evaluation.unexpected_surplus import (
    UnexpectedSurplus,
    unexpected,
)
from custom_components.homebatteryassist.engine.explain.messages import render
from custom_components.homebatteryassist.engine.explain.notifications import kind_of

T0 = datetime(2026, 11, 17, 11, 0, tzinfo=dt_util.UTC)
S = timedelta(seconds=10)


def _run(check, values, nom=True):
    """(surplus, expected) per 10 s; returns the messages."""
    out = []
    for i, (surplus, expected) in enumerate(values):
        result = check.update(T0 + i * S, surplus, expected, nom=nom)
        if result is not None:
            out.append((i, *result))
    return out


def test_rule() -> None:
    assert unexpected(1200.0, 100.0)
    assert not unexpected(1200.0, 800.0)  # forecast, more or less
    assert not unexpected(200.0, -500.0)  # too small


def test_reported_after_five_minutes_and_ended() -> None:
    check = UnexpectedSurplus(decimal_comma=True)
    sunny = [(1500.0, -200.0)] * 60  # 10 min
    dull = [(0.0, -200.0)] * 61  # over for 10 min
    messages = _run(check, [(0.0, -200.0)] * 3 + sunny + dull)
    (i, key, params), (j, end_key, end) = messages
    assert key == "pv_surplus_unexpected" and i == 3 + 30
    assert params["surplus"] == "1500 W" and params["expected"] == "0 W"
    assert params["battery"] == "@surplus_nom"
    assert end_key == "pv_surplus_unexpected_ended" and j > 3 + 60
    assert end["energy"] == "0,25" and end["expected"] == "0,00"
    assert end["peak"] == "1500 W"


def test_passing_sun_is_no_message() -> None:
    check = UnexpectedSurplus()
    values = ([(1500.0, 0.0)] * 20 + [(100.0, 0.0)] * 2) * 5
    assert _run(check, values) == []


def test_unknown_stops_counting() -> None:
    check = UnexpectedSurplus()
    values = [(1500.0, 0.0)] * 20 + [(None, None)] + [(1500.0, 0.0)] * 20
    assert _run(check, values) == []


def test_message_in_plan_mode_and_notification_kind() -> None:
    check = UnexpectedSurplus()
    [(_, key, params)] = _run(check, [(900.0, 100.0)] * 31, nom=False)
    text = render("nl", key, params)
    assert "Onverwacht zonne-overschot" in text and "900 W" in text
    assert "plan rekende er niet op" in text
    assert kind_of(key) == "solar"
    assert kind_of("pv_surplus_unexpected_ended") == "solar"
