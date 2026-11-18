"""Tests for the unexpected solar surplus and shortage."""

from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.evaluation.unexpected_surplus import (
    UnexpectedSurplus,
    unexpected,
)
from custom_components.homebatteryassist.engine.explain.messages import render
from custom_components.homebatteryassist.engine.explain.notifications import kind_of
from custom_components.homebatteryassist.engine.measure.house_measurement import (
    plan_balance,
    planned_discharge,
)

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


def test_plan_stores_unexpected_surplus_on_top() -> None:
    """A plan per slot charges what is unexpectedly left over, never from
    the grid; a planned discharge and an expected surplus stay as planned."""
    assert plan_balance(0.0, 1500.0, 0.0) == 1500.0
    assert plan_balance(500.0, 1500.0, 500.0) == 1500.0  # 500 planned + 1000
    assert plan_balance(2000.0, 1500.0, 0.0) == 2000.0  # grid charge planned
    assert plan_balance(-800.0, 1500.0, 0.0) == -800.0
    assert plan_balance(1000.0, 1200.0, 1000.0) == 1000.0  # as forecast
    assert plan_balance(0.0, 200.0, 0.0) == 0.0  # too small


def test_plan_does_not_take_missing_sun_from_the_grid() -> None:
    """Less sun than forecast: the sun part of a planned charge only as far
    as the surplus is there; a planned grid charge goes on."""
    assert plan_balance(1000.0, 200.0, 1200.0) == 200.0  # all from the sun
    assert plan_balance(1000.0, -300.0, 1200.0) == 0.0  # nothing left over
    assert plan_balance(2000.0, 100.0, 800.0) == 1300.0  # 1200 grid + 100
    assert plan_balance(1000.0, 700.0, 1200.0) == 1000.0  # more than half there
    assert plan_balance(0.0, 0.0, 1200.0) == 0.0  # nothing planned
    assert plan_balance(-500.0, 0.0, 1200.0) == -500.0  # discharge as planned


def test_threshold_is_a_setting() -> None:
    assert plan_balance(0.0, 400.0, 0.0, threshold_w=500.0) == 0.0
    assert plan_balance(0.0, 600.0, 0.0, threshold_w=500.0) == 600.0
    assert unexpected(400.0, 0.0, threshold_w=300.0)
    assert not unexpected(400.0, 0.0, threshold_w=500.0)


def test_shortage_reported_with_own_wait() -> None:
    check = UnexpectedSurplus(
        decimal_comma=True, shortage=True, start_after=timedelta(minutes=2)
    )
    cloudy = [(100.0, 1500.0)] * 60  # 10 min, 1400 W missing
    sunny = [(1500.0, 1500.0)] * 61
    messages = _run(check, [(1500.0, 1500.0)] * 3 + cloudy + sunny, nom=False)
    (i, key, params), (j, end_key, end) = messages
    assert key == "pv_shortage_unexpected" and i == 3 + 12
    assert params["surplus"] == "100 W" and params["expected"] == "1500 W"
    assert params["battery"] == "@shortage_plan"
    assert end_key == "pv_shortage_unexpected_ended" and j > 3 + 60
    assert end["peak"] == "1400 W"
    text = render("nl", key, params)
    assert "Minder zon dan verwacht" in text and "laden alleen" in text
    assert kind_of(key) == "solar" and kind_of(end_key) == "solar"
    # The surplus check stays quiet on a shortage, and the other way round.
    assert _run(UnexpectedSurplus(), cloudy) == []
    assert _run(UnexpectedSurplus(shortage=True), [(1500.0, 0.0)] * 60) == []


def test_planned_discharge_only_as_needed() -> None:
    """The plan discharges 1500 W for a forecast 1500 W house; the house uses
    400 W now: only 400 W, no battery energy into the grid. An export the
    plan chose (grid -1000 W) is kept."""
    from types import SimpleNamespace

    flow = SimpleNamespace(grid_w=400.0, excluded_w=0.0)
    assert planned_discharge(-1500.0, flow, 0.0) == -400.0  # type: ignore[arg-type]
    assert planned_discharge(-1500.0, flow, 200.0) == -400.0  # type: ignore[arg-type]
    assert planned_discharge(-1500.0, flow, -1000.0) == -1400.0  # type: ignore[arg-type]
    assert planned_discharge(-300.0, flow, 0.0) == -300.0  # type: ignore[arg-type]
    assert planned_discharge(800.0, flow, 0.0) == 800.0  # type: ignore[arg-type]
    # Exporting already (sun): no discharge at all.
    sunny = SimpleNamespace(grid_w=-500.0, excluded_w=0.0)
    assert planned_discharge(-1500.0, sunny, 0.0) == 0.0  # type: ignore[arg-type]
    # Not for an EV charger (excluded): the grid supplies it.
    ev = SimpleNamespace(grid_w=7400.0, excluded_w=7000.0)
    assert planned_discharge(-1500.0, ev, 0.0) == -400.0  # type: ignore[arg-type]
