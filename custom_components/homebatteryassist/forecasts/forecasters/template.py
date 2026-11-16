"""Template for an own consumption forecaster — a code example only.

Copy this file to ``/config/homebatteryassist/forecasters/`` (create the
folder), rename the class, set ``key`` and ``name``, and reload
HomeBatteryAssist. The forecaster then appears in the settings (Consumption
forecaster) and its accuracy is tracked next to the others on the dashboard,
also when it is not the chosen one.

``forecast`` gets the consumption history and the slots of the planning
window and returns the expected house consumption per slot (W). Return None
for a slot you cannot predict: HomeBatteryAssist then uses its built-in
profile there. Negative or absurd values are replaced too; corrections and
your adjustments are applied afterwards.

This example: the average of the last 24 hours, the same for every slot.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.forecasts.forecasters.base import (
    Forecaster,
    ForecasterInput,
    ForecasterResult,
)


class LastDayAverageForecaster(Forecaster):
    """The average consumption of the last 24 hours."""

    key = "last_day_average"  # becomes "custom_last_day_average"
    name = "Average of the last day"

    def forecast(self, data: ForecasterInput) -> ForecasterResult:
        since = data.now - timedelta(days=1)
        total = weight = 0.0
        for record in data.history:
            start = dt_util.parse_datetime(record["start"])
            if start is None or start < since:
                continue
            w = record["minutes"] * record["coverage"]
            total += record["avg_w"] * w
            weight += w
        value = round(total / weight, 1) if weight else None
        return ForecasterResult([value] * len(data.slots))
