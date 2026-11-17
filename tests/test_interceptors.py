"""Tests for the interceptor modules (the user's last say per battery)."""

from datetime import datetime
from pathlib import Path

from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.control.interceptors import (
    BUILTIN,
    DEFAULT_INTERCEPTOR,
    LIMIT,
    REJECT,
    RELEASE,
    BatteryProposal,
    Decision,
    InterceptInput,
    Interceptor,
    InterceptResult,
    create_interceptor,
    load_interceptors_from,
    run_interceptor,
)

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=dt_util.UTC)
PACKAGE = (
    Path(__file__).parent.parent
    / "custom_components/homebatteryassist/engine/control/interceptors"
)


def _battery(battery_id: str, proposed: float, **kwargs) -> BatteryProposal:
    values = {
        "id": battery_id,
        "name": battery_id.upper(),
        "phase": "l1",
        "soc": 50.0,
        "power_w": 0.0,
        "temperature_c": 20.0,
        "capacity_kwh": 5.0,
        "max_charge_w": 2500.0,
        "max_discharge_w": 2500.0,
        "min_soc": 10.0,
        "max_soc": 100.0,
        "virtual": True,
        "full_charge": False,
        "proposed_w": proposed,
        "reason": "zero_on_meter",
    }
    values.update(kwargs)
    return BatteryProposal(**values)


def _input(*batteries: BatteryProposal) -> InterceptInput:
    return InterceptInput(
        now=NOW,
        mode="nom",
        batteries=batteries,
        grid_w=1000.0,
        phase_w=(1000.0, 0.0, 0.0),
        phase_limit_w=5000.0,
        house_w=1000.0,
        pv_w=0.0,
        excluded_w=0.0,
        spike_w=0.0,
        slots=(),
    )


class _Fixed(Interceptor):
    key = "fixed"

    def __init__(self, result) -> None:
        self.result = result

    def intercept(self, data):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_default_lets_everything_through() -> None:
    interceptor = create_interceptor(None, {})
    assert interceptor.key == DEFAULT_INTERCEPTOR and DEFAULT_INTERCEPTOR in BUILTIN
    outcome = run_interceptor(interceptor, _input(_battery("a", -800.0)))
    assert outcome.powers == {"a": -800.0} and not outcome.changes


def test_limit_never_more_nor_the_other_way() -> None:
    """A limit is at most the proposal, in the same direction."""
    data = _input(_battery("a", -800.0), _battery("b", 600.0), _battery("c", -500.0))
    result = InterceptResult(
        [
            Decision("a", LIMIT, -300.0, "max 300"),
            Decision("b", LIMIT, 2000.0),  # more than proposed: proposal
            Decision("c", LIMIT, 400.0),  # the other way: 0
        ],
        redistribute=False,
    )
    outcome = run_interceptor(_Fixed(result), data)
    assert outcome.powers == {"a": -300.0, "b": 600.0, "c": 0.0}
    assert [(i, a) for i, a, _w, _r in outcome.changes] == [("a", LIMIT), ("c", LIMIT)]


def test_reject_release_and_redistribution() -> None:
    """What a held-back battery does not do, the approved one takes over
    (up to its limit); a released battery is marked for its own control."""
    data = _input(_battery("a", -1000.0), _battery("b", -1000.0), _battery("c", 300.0))
    result = InterceptResult(
        [Decision("a", REJECT, reason="too cold"), Decision("c", RELEASE)]
    )
    outcome = run_interceptor(_Fixed(result), data)
    assert outcome.powers["a"] == 0.0 and outcome.powers["c"] == 0.0
    assert outcome.powers["b"] == -2000.0  # took over the 1000 W of a
    assert outcome.released == {"c"}
    no_takeover = run_interceptor(
        _Fixed(InterceptResult([Decision("a", REJECT)], redistribute=False)), data
    )
    assert no_takeover.powers["b"] == -1000.0


def test_nonsense_and_failure_count_as_approved() -> None:
    data = _input(_battery("a", -800.0))
    weird = InterceptResult(
        [Decision("x", REJECT), "nonsense", Decision("a", LIMIT, float("nan"))]  # type: ignore[list-item]
    )
    assert run_interceptor(_Fixed(weird), data).powers == {"a": 0.0}  # NaN -> 0
    assert run_interceptor(_Fixed("not a result"), data).powers == {"a": -800.0}
    failed = run_interceptor(_Fixed(RuntimeError("boom")), data)
    assert failed.failed and failed.powers == {"a": -800.0}


def test_own_module_from_template(tmp_path: Path) -> None:
    """The template, copied to the own folder, loads and holds back a cold
    battery, limits a large discharge."""
    source = (PACKAGE / "template.py").read_text(encoding="utf-8")
    (tmp_path / "mine.py").write_text(
        source.replace(
            "from .base import",
            "from custom_components.homebatteryassist.engine.control.interceptors.base import",
        ),
        encoding="utf-8",
    )
    own = load_interceptors_from(tmp_path)
    assert list(own) == ["custom_template"]
    interceptor = create_interceptor("custom_template", own)
    data = _input(_battery("cold", -800.0, temperature_c=2.0), _battery("big", -2400.0))
    outcome = run_interceptor(interceptor, data)
    assert outcome.powers["cold"] == 0.0
    assert outcome.powers["big"] <= -1500.0  # limited, then took over the cold one
