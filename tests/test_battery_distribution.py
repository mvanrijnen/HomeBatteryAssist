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
