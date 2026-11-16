"""Tests for spreading battery power over several batteries."""

from custom_components.homebatteryassist.engine.planning.distribution import (
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


def test_distributor_keeps_battery_until_balance_check() -> None:
    """No flapping: the battery in use stays until the hourly balance check."""
    from datetime import datetime, timedelta

    from custom_components.homebatteryassist.engine.planning.distribution import (
        Distributor,
    )

    t0 = datetime(2026, 11, 16, 0, 0)
    distributor = Distributor(timedelta(hours=1))
    result, switch = distributor.distribute(
        -400.0, [_b("a", 51.0), _b("b", 50.0)], 300.0, t0
    )
    assert result == {"a": -400.0, "b": 0.0} and switch is None

    # "a" is now emptier than "b", but it stays in use before the check.
    later = t0 + timedelta(minutes=30)
    result, switch = distributor.distribute(
        -400.0, [_b("a", 47.0), _b("b", 50.0)], 300.0, later
    )
    assert result["a"] == -400.0 and switch is None

    # At the balance check "b" is more than 2 % fuller: it takes over.
    check = t0 + timedelta(hours=1)
    result, switch = distributor.distribute(
        -400.0, [_b("a", 46.0), _b("b", 50.0)], 300.0, check
    )
    assert result == {"a": 0.0, "b": -400.0} and switch == ("b", "a")

    # Within the tolerance nothing changes at the next check.
    next_check = check + timedelta(hours=1)
    result, switch = distributor.distribute(
        -400.0, [_b("a", 46.0), _b("b", 47.0)], 300.0, next_check
    )
    assert result["b"] == -400.0 and switch is None
