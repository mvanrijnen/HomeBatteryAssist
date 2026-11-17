"""Tests for the short peaks (spike filter modules)."""

from datetime import datetime, timedelta
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.history.spikes import (
    is_regular,
    regular_peak_hours,
    without_spikes,
)
from custom_components.homebatteryassist.engine.measure.house_measurement import (
    PowerFlow,
    nom_balance,
)
from custom_components.homebatteryassist.engine.measure.spike_filters import (
    BUILTIN,
    DEFAULT_SPIKE_FILTER,
    SpikeState,
    checked,
    create_spike_filter,
    load_spike_filters_from,
)

T0 = datetime(2026, 11, 20, 7, 0, tzinfo=dt_util.UTC)
S = timedelta(seconds=10)
PACKAGE = (
    Path(__file__).parent.parent
    / "custom_components/homebatteryassist/engine/measure/spike_filters"
)


def _run(spike_filter, values, start=T0):
    """Feed one value per 10 s; returns the states."""
    return [spike_filter.update(start + i * S, v) for i, v in enumerate(values)]


def test_kettle_is_a_peak() -> None:
    """3 minutes of 2400 W on 300 W: ignored while on, energy reported after."""
    f = create_spike_filter(DEFAULT_SPIKE_FILTER, {}, 2000, 300)
    states = _run(f, [300.0] * 12 + [2700.0] * 18 + [300.0] * 3)
    assert states[12].ignore_w == 2400.0  # at once, while it lasts
    assert all(s.ignore_w == 2400.0 for s in states[12:30])
    ended = [s.ended_wh for s in states if s.ended_wh]
    assert len(ended) == 1 and abs(ended[0] - 2400 * 180 / 3600) < 1
    assert states[-1].ignore_w == 0.0


def test_oven_is_followed_after_the_maximum() -> None:
    """A rise lasting longer is normal consumption; a kettle on top is a peak."""
    f = create_spike_filter(DEFAULT_SPIKE_FILTER, {}, 2000, 300)
    states = _run(f, [300.0] * 6 + [2800.0] * 40 + [5000.0] * 6 + [2800.0] * 3)
    assert states[10].ignore_w == 2500.0  # still a candidate
    assert states[45].ignore_w == 0.0  # longer than 5 min: followed
    assert not any(s.ended_wh for s in states[:46])  # was no peak
    assert states[47].ignore_w == 2200.0  # kettle on top of the oven
    assert states[52].ended_wh > 0  # it ended: a peak


def test_small_rises_and_unknown_are_no_peak() -> None:
    f = create_spike_filter(DEFAULT_SPIKE_FILTER, {}, 2000, 300)
    states = _run(f, [300.0, 1500.0, 1500.0, None, 2600.0])
    assert all(s.ignore_w == 0.0 for s in states[:4])


def test_final_check() -> None:
    """Nonsense from a module counts as no peak; ignore stays within 0..house."""
    assert checked("x", 500.0) == SpikeState()
    assert checked(SpikeState(9999.0, -1.0), 500.0) == SpikeState(500.0, 0.0)
    assert checked(SpikeState(float("nan"), 99999.0), 500.0) == SpikeState()


def test_nom_does_not_discharge_for_excluded_or_peaks() -> None:
    """A shortage is discharged, but not for excluded devices or peaks;
    a surplus is always charged."""
    flow = PowerFlow(3000.0, 0.0, 1000.0, 0.0, 2000.0, (3000.0,))
    assert nom_balance(flow, 0.0) == -2000.0  # not the 1000 W EV
    assert nom_balance(flow, 0.0, ignore_w=1500.0) == -500.0
    assert nom_balance(flow, 0.0, ignore_w=5000.0) == 0.0
    surplus = PowerFlow(-800.0, 2000.0, 1000.0, 0.0, 200.0, (-800.0,))
    assert nom_balance(surplus, 0.0) == 800.0


def _records(days: int, peak_days) -> list[dict]:
    """One record per day at 07:00 local; a peak on ``peak_days``."""
    out = []
    for day in range(days):
        start = dt_util.as_utc(
            dt_util.as_local(T0 - timedelta(days=days - day)).replace(hour=7)
        )
        record = {
            "start": start.isoformat(),
            "minutes": 60,
            "avg_w": 500.0,
            "coverage": 1.0,
        }
        if day in peak_days:
            record["spike_w"] = 100.0
        out.append(record)
    return out


def test_regular_peaks_stay_in_the_average(hass: HomeAssistant) -> None:
    """Coffee every day at 7: regular, kept; a one-off peak is taken out."""
    every_day = _records(14, range(14))
    regular = regular_peak_hours(every_day, T0)
    assert len(regular) == 7  # every weekday at 7
    assert all(r["avg_w"] == 500.0 for r in without_spikes(every_day, regular))
    once = _records(14, {3})
    regular = regular_peak_hours(once, T0)
    assert regular == set()
    adjusted = without_spikes(once, regular)
    assert adjusted[3]["avg_w"] == 400.0 and adjusted[4]["avg_w"] == 500.0
    assert not is_regular(regular, T0)


def test_own_module_from_template(tmp_path: Path) -> None:
    """The template, copied to the own folder, loads as custom_<key>."""
    source = (PACKAGE / "template.py").read_text(encoding="utf-8")
    (tmp_path / "cap.py").write_text(
        source.replace(
            "from .base import",
            "from custom_components.homebatteryassist.engine.measure.spike_filters.base import",
        ),
        encoding="utf-8",
    )
    found = load_spike_filters_from(tmp_path)
    assert list(found) == ["custom_cap_during_the_day"]
    own = create_spike_filter("custom_cap_during_the_day", found, 1500, 120)
    assert own.threshold_w == 1500.0
    assert DEFAULT_SPIKE_FILTER in BUILTIN
