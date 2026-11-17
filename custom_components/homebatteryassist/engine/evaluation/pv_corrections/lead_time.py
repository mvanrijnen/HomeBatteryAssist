"""Built-in PV correction: one factor per lead time.

Per lead time (0-1 h ahead .. 5 days+), the measured PV energy divided by
the forecast energy of the last weeks (recent days counting more), between
0.5 and 1.5 and growing in strength with the number of hours checked. The
original correction of HomeBatteryAssist; always available.
"""

from __future__ import annotations

from collections.abc import Sequence

from .base import PvCorrectionInput, PvCorrector


class LeadTimeCorrector(PvCorrector):
    """A factor per lead time."""

    key = "lead_time"
    name = "Per lead time"

    def correct(self, data: PvCorrectionInput) -> Sequence[float | None]:
        return [wh * data.lead_factor(start) for start, wh in data.slots]
