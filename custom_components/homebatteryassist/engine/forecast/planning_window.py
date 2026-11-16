"""Planning window: how far ahead HomeBatteryAssist can calculate.

Every forward-looking calculation first determines the planning window and
never calculates beyond its end. The end is the configured maximum, limited by
how far the price and PV forecasts reach.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from homeassistant.util import dt as dt_util


class HorizonLimit(StrEnum):
    """What determines the end of the planning window."""

    SETTING = "setting"  # the configured maximum number of days
    PRICE = "price"  # the price forecast ends earlier
    PV = "pv"  # the PV forecast ends earlier
    NO_PRICE = "no_price"  # price forecast configured, but no data
    NO_PV = "no_pv"  # PV forecast configured, but no data


@dataclass(frozen=True, slots=True)
class PlanningWindow:
    """The period ahead that may be calculated: ``[start, end)``."""

    start: datetime
    end: datetime
    limited_by: HorizonLimit

    @property
    def duration(self) -> timedelta:
        """Length of the window (zero if no planning is possible)."""
        return max(self.end - self.start, timedelta(0))

    @property
    def hours(self) -> float:
        """Length of the window in hours."""
        return self.duration.total_seconds() / 3600

    @property
    def is_empty(self) -> bool:
        """True if nothing can be calculated ahead."""
        return self.end <= self.start

    def overlaps(self, start: datetime, end: datetime) -> bool:
        """True if the period ``[start, end)`` falls (partly) inside the window."""
        return start < self.end and end > self.start

    def slots(self, step: timedelta) -> list[tuple[datetime, datetime]]:
        """Clock-aligned periods of length ``step`` covering the window.

        The first slot starts at the boundary at or before ``start``; the last
        slot is cut off at ``end``.
        """
        if self.is_empty:
            return []
        seconds = step.total_seconds()
        ts = self.start.timestamp()
        slot_start = dt_util.utc_from_timestamp(ts - ts % seconds)
        slots: list[tuple[datetime, datetime]] = []
        while slot_start < self.end:
            slot_end = min(slot_start + step, self.end)
            slots.append((slot_start, slot_end))
            slot_start += step
        return slots


def planning_horizon(
    now: datetime,
    max_days: int,
    price_end: datetime | None,
    pv_end: datetime | None,
    *,
    price_configured: bool,
    pv_configured: bool,
) -> PlanningWindow:
    """Return the window from ``now`` to min(now + max_days, price end, PV end).

    Only configured forecasts limit the window. A configured forecast without
    (future) data makes the window empty: no planning possible.
    """
    window = PlanningWindow(now, now + timedelta(days=max_days), HorizonLimit.SETTING)
    for configured, forecast_end, limit, missing in (
        (price_configured, price_end, HorizonLimit.PRICE, HorizonLimit.NO_PRICE),
        (pv_configured, pv_end, HorizonLimit.PV, HorizonLimit.NO_PV),
    ):
        if not configured:
            continue
        if forecast_end is None or forecast_end <= now:
            return PlanningWindow(now, now, missing)
        if forecast_end < window.end:
            window = PlanningWindow(now, forecast_end, limit)
    return window
