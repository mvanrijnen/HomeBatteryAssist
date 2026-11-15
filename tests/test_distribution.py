"""Tests for spreading battery power over several batteries."""

from custom_components.homebatteryassist.planning.distribution import (
    Candidate,
    distribute,
)


def _b(id_: str, soc: float, power: float = 2500.0) -> Candidate:
    return Candidate(id_, soc, 10.0, 100.0, power, power)


def test_small_request_uses_one_battery() -> None:
    """400 W with a 300 W minimum: one battery, the fullest when discharging."""
    result = distribute(-400.0, [_b("a", 40.0), _b("b", 80.0)], 300.0)
    assert result == {"a": 0.0, "b": -400.0}


def test_large_request_is_spread() -> None:
    """2000 W with a 300 W minimum: shared over both batteries."""
    result = distribute(2000.0, [_b("a", 40.0), _b("b", 80.0)], 300.0)
    assert result == {"a": 1000.0, "b": 1000.0}


def test_minimum_limits_the_number_of_batteries() -> None:
    """700 W, minimum 300 W, three batteries: two (350 W each), emptiest first."""
    result = distribute(700.0, [_b("a", 60.0), _b("b", 20.0), _b("c", 40.0)], 300.0)
    assert result == {"a": 0.0, "b": 350.0, "c": 350.0}


def test_power_limits_force_more_batteries() -> None:
    """More than one battery can deliver: as many as needed, rest passed on."""
    batteries = [_b("a", 50.0, 800.0), _b("b", 50.0, 2500.0)]
    assert distribute(-1200.0, batteries, 2000.0) == {"a": -600.0, "b": -600.0}
    result = distribute(-3000.0, batteries, 300.0)
    assert result["a"] == -800.0 and result["b"] == -2200.0


def test_full_or_empty_batteries_are_skipped() -> None:
    """A full battery cannot charge; an empty one cannot discharge."""
    full, empty = _b("full", 100.0), _b("empty", 10.0)
    assert distribute(500.0, [full, empty], 300.0) == {"full": 0.0, "empty": 500.0}
    assert distribute(-500.0, [full, empty], 300.0) == {"full": -500.0, "empty": 0.0}
    assert distribute(0.0, [full], 300.0) == {"full": 0.0}
