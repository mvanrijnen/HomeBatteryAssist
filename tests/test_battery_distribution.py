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


def test_one_direction_fuse_first() -> None:
    """Two phases overloaded the opposite way: the protection stands (the
    fuse comes first), the other batteries stop."""
    from custom_components.homebatteryassist.engine.planning.battery_distribution import (
        one_direction,
    )

    out = one_direction({"a": -2800.0, "b": 2800.0, "c": -500.0}, ["a", "b"], [])
    assert out == {"a": -2800.0, "b": 2800.0, "c": 0.0}


def test_system_limited() -> None:
    """The system's max powers hold for all batteries together."""
    from types import SimpleNamespace

    from custom_components.homebatteryassist.engine.devices.batteries.virtual import (
        system_limited,
    )

    rules = SimpleNamespace(max_charge_w=0.0, max_discharge_w=2000.0)
    out = system_limited({"a": -2000.0, "b": -2000.0}, rules)
    assert out == {"a": -1000.0, "b": -1000.0}
    assert system_limited({"a": 3000.0}, rules) == {"a": 3000.0}


def test_a_rounding_rest_does_not_keep_an_empty_battery_in() -> None:
    """A battery a hair above its minimum (a rounding rest) counts as empty:
    the other battery gives the whole demand; the simulated battery reaches
    its minimum instead of stopping just above it."""
    import random
    from types import SimpleNamespace

    from custom_components.homebatteryassist.engine.devices.batteries.virtual import (
        limit_power,
    )
    from custom_components.homebatteryassist.engine.planning.battery_distribution import (
        Candidate,
        distribute,
    )

    out = distribute(
        -1500.0,
        [
            Candidate("b0", 52.0, 10.0, 90.0, 2500.0, 2500.0),
            Candidate("b1", 10.0000006, 10.0, 90.0, 1200.0, 1200.0),
        ],
        0.0,
    )
    assert out == {"b0": -1500.0, "b1": 0.0}
    config = SimpleNamespace(
        capacity_kwh=2.5,
        min_soc=10.0,
        max_soc=90.0,
        max_charge_w=1200.0,
        max_discharge_w=1200.0,
        efficiency=0.81,
    )
    rng = random.Random(1)
    for _ in range(50):
        soc = 10.0 + rng.uniform(0, 3)
        for _ in range(400):
            command, _ = limit_power(config, soc, -750.0, 5 / 3600, 0.81)
            _, soc = limit_power(config, soc, command, 5 / 3600, 0.81)
        assert soc == 10.0
        soc = 90.0 - rng.uniform(0, 3)
        for _ in range(400):
            command, _ = limit_power(config, soc, 750.0, 5 / 3600, 0.81)
            _, soc = limit_power(config, soc, command, 5 / 3600, 0.81)
        assert soc == 90.0
