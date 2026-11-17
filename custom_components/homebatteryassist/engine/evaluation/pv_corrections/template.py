"""Example PV correction module (never registered): copy and adapt.

Copy this file to ``/config/homebatteryassist/pv_corrections/``, give the
class another ``key`` and ``name``, and change the relative import
(``from .base import``) into
``from custom_components.homebatteryassist.engine.evaluation.pv_corrections.base import``.
Restart Home Assistant and choose it in the settings (*PV correction*). To
start from a built-in correction instead, copy ``hour_and_level.py`` or
``lead_time.py`` the same way; the built-in ones always stay available.

This example keeps the built-in correction per lead time and takes off a
fixed share in the morning, e.g. for a tree that shades the panels until 10:00.
"""

from __future__ import annotations

from collections.abc import Sequence

from homeassistant.util import dt as dt_util

from .base import PvCorrectionInput, PvCorrector

SHADE_UNTIL = 10  # local hour
SHADE_FACTOR = 0.6


class MorningShadeCorrector(PvCorrector):
    """The correction per lead time, less in the morning."""

    key = "morning_shade"
    name = "Morning shade"

    def correct(self, data: PvCorrectionInput) -> Sequence[float | None]:
        out = []
        for start, wh in data.slots:
            value = wh * data.lead_factor(start)
            if dt_util.as_local(start).hour < SHADE_UNTIL:
                value *= SHADE_FACTOR
            out.append(value)
        return out
