"""Example spike filter module (never registered): copy and adapt.

Copy this file to ``/config/homebatteryassist/spike_filters/``, give the class
another ``key`` and ``name``, and change the relative import
(``from .base import``) into
``from custom_components.homebatteryassist.engine.measure.spike_filters.base import``.
Restart Home Assistant and choose it in the settings (*Short peaks*). To
start from the built-in filter instead, copy ``short_peaks.py`` the same way;
the built-in one always stays available.

This example ignores, for the battery, everything above a fixed level during
the day (e.g. a household whose cooking peaks should come from the grid), and
reports no peak energy, so the average consumption is left as measured.
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.util import dt as dt_util

from .base import SpikeFilter, SpikeState

LEVEL_W = 2500.0
FROM_HOUR, TO_HOUR = 7, 22  # local


class CapDuringTheDay(SpikeFilter):
    """Never discharge for more than ``LEVEL_W`` during the day."""

    key = "cap_during_the_day"
    name = "Cap during the day"

    def update(self, when: datetime, house_w: float | None) -> SpikeState:
        if house_w is None:
            return SpikeState()
        if FROM_HOUR <= dt_util.as_local(when).hour < TO_HOUR:
            return SpikeState(max(house_w - LEVEL_W, 0.0), 0.0)
        return SpikeState()
