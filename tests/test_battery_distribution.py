def test_charging_one_after_the_other() -> None:
    """Sequential: the emptiest at its full power, the next the rest."""
    from custom_components.homebatteryassist.engine.planning.battery_distribution import (
        Candidate,
        distribute,
    )

    a = Candidate("a", 70.0, 10.0, 100.0, 2500.0, 2500.0)
    b = Candidate("b", 40.0, 10.0, 100.0, 2500.0, 2500.0)
    assert distribute(3000.0, [a, b], 300.0, sequential=True) == {
        "a": 500.0,
        "b": 2500.0,
    }
    assert distribute(2000.0, [a, b], 300.0, sequential=True) == {"a": 0.0, "b": 2000.0}


def test_one_direction() -> None:
    """Never one battery charging while another discharges."""
    from custom_components.homebatteryassist.engine.planning.battery_distribution import (
        one_direction,
    )

    # The net stands: -500 W, only by the discharging one.
    assert one_direction({"a": 1000.0, "b": -1500.0}) == {"a": 0.0, "b": -500.0}
    # Net +2500 W by the two charging ones, in proportion.
    out = one_direction({"a": 2000.0, "b": -500.0, "c": 1000.0})
    assert out["b"] == 0.0
    assert abs(out["a"] - 2500 * 2 / 3) < 1e-6 and abs(out["c"] - 2500 / 3) < 1e-6
    # A full charge sets the direction: the other stops discharging.
    assert one_direction({"a": 2500.0, "b": -1500.0}, [], ["a"]) == {
        "a": 2500.0,
        "b": 0.0,
    }
    # Protection before a full charge.
    assert one_direction({"a": 2500.0, "b": -1500.0}, ["b"], ["a"]) == {
        "a": 0.0,
        "b": -1500.0,
    }
    # One direction already: unchanged.
    assert one_direction({"a": 100.0, "b": 0.0}) == {"a": 100.0, "b": 0.0}
