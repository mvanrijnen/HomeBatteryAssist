"""Built-in spike filter: a rise above the threshold that ends in time.

Keeps a *baseline*: the consumption without peaks, following the measured
consumption slowly (``BASELINE_S``). When the consumption rises more than
``threshold_w`` above it, a peak may have started: the part above the
baseline is ignored for the battery. When it falls back within
``max_duration_s`` (below baseline + half the threshold), it was a peak and its
energy is reported. When it lasts longer, it is normal consumption (e.g. an
oven): the baseline jumps to it and it is followed from then on — so a kettle
on top of the oven is again a peak.

A rise that is over within ``MIN_PEAK_S`` is no peak but sensor timing: the
grid, PV and battery sensors do not update at the same moment, so the house
(grid + PV - battery) can jump for a reading or two when a battery or the
sun changes. It is not counted (no energy reported, not in the history).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import SpikeFilter, SpikeState

BASELINE_S = 120.0  # how fast the baseline follows the consumption
MAX_GAP_S = 60.0  # a longer gap between values counts as this long
MIN_PEAK_S = 15.0  # shorter: sensor timing, not a device


class ShortPeakFilter(SpikeFilter):
    """Short rises above a threshold."""

    key = "short_peaks"
    verified = True
    name = "Short peaks above a threshold"

    def __init__(self) -> None:
        self.baseline: float | None = None
        self._last: datetime | None = None
        self._start: datetime | None = None  # of the running peak
        self._excess = 0.0  # last value above the baseline (peak)
        self._wh = 0.0  # energy of the running peak
        self.peaks = 0  # peaks recognised since start
        self.peak_wh = 0.0  # their energy
        self.glitches = 0  # rises too short to be a device (sensor timing)

    def details(self) -> dict[str, Any]:
        return {
            "baseline_w": round(self.baseline, 1)
            if self.baseline is not None
            else None,
            "in_peak": self._start is not None,
            "peaks": self.peaks,
            "peak_kwh": round(self.peak_wh / 1000, 3),
            "timing_glitches": self.glitches,
        }

    def update(self, when: datetime, house_w: float | None) -> SpikeState:
        seconds = (
            min(max((when - self._last).total_seconds(), 0.0), MAX_GAP_S)
            if self._last is not None
            else 0.0
        )
        self._last = when
        if house_w is None:
            # Unknown: forget a running peak (it cannot be measured).
            self._start, self._excess, self._wh = None, 0.0, 0.0
            return SpikeState()
        if self.baseline is None:
            self.baseline = house_w
        if self._start is not None:
            self._wh += self._excess * seconds / 3600
            excess = house_w - self.baseline
            if excess < self.threshold_w / 2:
                ended = self._wh
                if (when - self._start).total_seconds() < MIN_PEAK_S:
                    ended = 0.0  # sensor timing, no device
                    self.glitches += 1
                else:
                    self.peaks += 1
                    self.peak_wh += ended
                self._start, self._excess, self._wh = None, 0.0, 0.0
                self.baseline = (
                    min(self.baseline, house_w) if excess < 0 else self.baseline
                )
                return SpikeState(0.0, ended)
            if (when - self._start).total_seconds() > self.max_duration_s:
                # Lasts too long: normal consumption from now on.
                self._start, self._excess, self._wh = None, 0.0, 0.0
                self.baseline = house_w
                return SpikeState()
            self._excess = max(excess, 0.0)
            return SpikeState(self._excess, 0.0)
        if house_w - self.baseline > self.threshold_w:
            self._start, self._wh = when, 0.0
            self._excess = house_w - self.baseline
            return SpikeState(self._excess, 0.0)
        self.baseline += (house_w - self.baseline) * min(seconds / BASELINE_S, 1.0)
        return SpikeState()
