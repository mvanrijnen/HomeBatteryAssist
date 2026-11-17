"""Tests for the PV correction modules."""

from datetime import datetime, timedelta
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.evaluation.forecast_accuracy import (
    PV_CORRECTOR_KIND,
    ForecastAccuracy,
)
from custom_components.homebatteryassist.engine.evaluation.pv_corrections import (
    BUILTIN,
    DEFAULT_PV_CORRECTOR,
    PvCorrectionInput,
    PvCorrector,
    PvResult,
    apply_pv_correction,
    load_pv_correctors_from,
)

UTC = dt_util.UTC
H = timedelta(hours=1)
NOW = datetime(2026, 11, 20, 0, 0, tzinfo=UTC)
PACKAGE = (
    Path(__file__).parent.parent
    / "custom_components/homebatteryassist/engine/evaluation/pv_corrections"
)


def _results(days: int, actual_of) -> list[PvResult]:
    """Hourly results 8..16 local; forecast 1000 Wh at noon, less around it."""
    out = []
    for day in range(days, 0, -1):
        local_midnight = dt_util.as_local(NOW - timedelta(days=day)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for hour in range(8, 17):
            start = dt_util.as_utc(local_midnight + hour * H)
            pred = 1000.0 - 100.0 * abs(hour - 12)
            if day % 3 == 0:
                pred *= 0.25  # a dull day
            out.append(
                PvResult(start, actual_of(hour, pred, day % 3 == 0), {"6-24h": pred})
            )
    return out


def _input(results, slots) -> PvCorrectionInput:
    return PvCorrectionInput(NOW, slots, results, lambda _start: 1.0, {"6-24h": 1.0})


def _slot(hour: int, wh: float) -> tuple[datetime, float]:
    local = dt_util.as_local(NOW + timedelta(days=1)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    return dt_util.as_utc(local), wh


def test_default_and_original_available() -> None:
    """The new correction is the default; the original stays available."""
    assert DEFAULT_PV_CORRECTOR == "hour_and_level"
    assert {"hour_and_level", "lead_time"} <= set(BUILTIN)


def test_learns_morning_shade(hass: HomeAssistant) -> None:
    """Mornings bring half of the forecast: the morning hours are corrected."""
    results = _results(21, lambda h, p, dull: p * (0.5 if h < 11 else 1.0))
    slots = [_slot(9, 800.0), _slot(13, 900.0)]
    morning, afternoon = apply_pv_correction(
        BUILTIN["hour_and_level"], _input(results, slots)
    )
    assert morning < 800.0 * 0.7
    assert abs(afternoon - 900.0) < 900.0 * 0.15
    # The original only knows one factor per lead time.
    original = apply_pv_correction(BUILTIN["lead_time"], _input(results, slots))
    assert original == [800.0, 900.0]


def test_learns_dull_days(hass: HomeAssistant) -> None:
    """Dull hours bring less than forecast, sunny ones as forecast."""
    results = _results(30, lambda h, p, dull: p * (0.5 if dull else 1.0))
    slots = [_slot(12, 250.0), _slot(12, 1000.0)]
    dull, sunny = apply_pv_correction(BUILTIN["hour_and_level"], _input(results, slots))
    assert dull < 250.0 * 0.8
    assert sunny > 1000.0 * 0.9
    details = BUILTIN["hour_and_level"].details()
    assert details["levels"]["dull"] < details["levels"]["sunny"]


def test_without_history_like_lead_time(hass: HomeAssistant) -> None:
    """No results: only the factor per lead time."""
    data = PvCorrectionInput(NOW, [_slot(12, 500.0)], [], lambda _s: 0.8, {})
    assert apply_pv_correction(BUILTIN["hour_and_level"], data) == [400.0]


class _Broken(PvCorrector):
    key = "broken"

    def correct(self, data):
        return [float("nan"), -5.0, 99999.0]


def test_final_check(hass: HomeAssistant) -> None:
    """Nonsense from a module is replaced by the correction per lead time."""
    data = PvCorrectionInput(
        NOW,
        [_slot(10, 100.0), _slot(11, 200.0), _slot(12, 300.0)],
        [],
        lambda _s: 0.5,
        {},
    )
    assert apply_pv_correction(_Broken(), data) == [50.0, 100.0, 150.0]


def test_own_module_from_template(tmp_path: Path) -> None:
    """The template, copied to the own folder, loads as custom_<key>."""
    source = (PACKAGE / "template.py").read_text(encoding="utf-8")
    (tmp_path / "shade.py").write_text(
        source.replace(
            "from .base import",
            "from custom_components.homebatteryassist.engine.evaluation.pv_corrections.base import",
        ),
        encoding="utf-8",
    )
    found = load_pv_correctors_from(tmp_path)
    assert list(found) == ["custom_morning_shade"]


async def test_corrections_are_compared(hass: HomeAssistant) -> None:
    """Each correction's forecast is settled against the measured PV."""
    accuracy = ForecastAccuracy(hass, "test")
    start = NOW + 2 * H
    kind = f"{PV_CORRECTOR_KIND}lead_time"
    accuracy.track(kind)
    accuracy.record("pv", [(start, start + H, 500.0)], NOW)
    accuracy.record(kind, [(start, start + H, 400.0)], NOW)
    records = [
        {
            "start": (start + i * timedelta(minutes=15)).isoformat(),
            "minutes": 15,
            "avg_w": 300.0,
            "coverage": 1.0,
            "pv_w": 400.0,
        }
        for i in range(5)
    ]
    assert accuracy.evaluate_pv(records) == 1
    accuracy.refresh_stats(start + 2 * H)
    assert accuracy.pv_correctors()["lead_time"]["1-6h"]["mae"] == 0.0
    assert accuracy.pv_results()[0].actual == 400.0
