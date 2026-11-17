"""Unexpected solar surplus: what is measured now against the forecast.

The accuracy per lead time (``forecast_accuracy.py``) settles a forecast
afterwards; this check says it while it happens: when there is clearly more
solar power left over than the forecast for this hour expected, *Why* tells
so once (and once more when it is over), with what it means for the batteries.

Surplus = PV - house - excluded devices (what the batteries could store);
expected = PV forecast for this hour (corrected) - consumption forecast for
this slot. Unexpected: at least ``MIN_SURPLUS_W`` measured, and less than
``SHARE`` of it forecast, for ``START_AFTER`` on end (a passing gap in the
clouds is no message); over after ``END_AFTER`` without it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

MIN_SURPLUS_W = 300.0
SHARE = 0.5
START_AFTER = timedelta(minutes=5)
END_AFTER = timedelta(minutes=10)
MAX_GAP = timedelta(minutes=2)  # longer without a value: start counting anew


@dataclass
class _Event:
    start: datetime
    seen: datetime
    wh: float = 0.0  # measured surplus during the event
    expected_wh: float = 0.0  # what was forecast of it
    peak_w: float = 0.0


def unexpected(surplus_w: float, expected_w: float) -> bool:
    """A surplus the forecast did not see coming."""
    return surplus_w >= MIN_SURPLUS_W and max(expected_w, 0.0) < SHARE * surplus_w


class UnexpectedSurplus:
    """Follows the measured surplus; ``update`` returns a message to log."""

    def __init__(self, decimal_comma: bool = False) -> None:
        """Initialize."""
        self._comma = decimal_comma
        self.event: _Event | None = None
        self._since: datetime | None = None  # unexpected since (before start)
        self._quiet: datetime | None = None  # expected again since (in event)
        self._last: datetime | None = None

    def update(
        self,
        when: datetime,
        surplus_w: float | None,
        expected_w: float | None,
        nom: bool = True,
    ) -> tuple[str, dict[str, Any]] | None:
        """One measurement; ``None`` values = unknown (no PV or forecast).

        ``nom``: the batteries follow zero on the meter (they store a surplus
        by themselves) rather than a plan per slot.
        """
        last, self._last = self._last, when
        if surplus_w is None or expected_w is None:
            self._since = None
            return self._maybe_end(when) if self.event else None
        hours = (
            (when - last).total_seconds() / 3600
            if last is not None and when - last <= MAX_GAP
            else 0.0
        )
        if not unexpected(surplus_w, expected_w):
            self._since = None
            if self.event is None:
                return None
            self._add(surplus_w, expected_w, hours)
            return self._maybe_end(when)
        if self.event is not None:
            self._quiet = None
            self.event.seen = when
            self.event.peak_w = max(self.event.peak_w, surplus_w)
            self._add(surplus_w, expected_w, hours)
            return None
        if self._since is None or hours == 0.0:
            self._since = when
        if when - self._since < START_AFTER:
            return None
        # What was left over since it began counts too.
        start_hours = (when - self._since).total_seconds() / 3600
        self.event = _Event(
            self._since,
            when,
            wh=surplus_w * start_hours,
            expected_wh=max(expected_w, 0.0) * start_hours,
            peak_w=surplus_w,
        )
        self._since = None
        return (
            "pv_surplus_unexpected",
            {
                "surplus": f"{surplus_w:.0f} W",
                "expected": f"{max(expected_w, 0.0):.0f} W",
                "since": self.event.start,
                "battery": "@surplus_nom" if nom else "@surplus_plan",
            },
        )

    def _add(self, surplus_w: float, expected_w: float, hours: float) -> None:
        if self.event is not None:
            self.event.wh += max(surplus_w, 0.0) * hours
            self.event.expected_wh += max(expected_w, 0.0) * hours

    def _maybe_end(self, when: datetime) -> tuple[str, dict[str, Any]] | None:
        if self._quiet is None:
            self._quiet = when
        event = self.event
        if event is None or when - self._quiet < END_AFTER:
            return None
        self.event = None
        self._quiet = None
        return (
            "pv_surplus_unexpected_ended",
            {
                "start": event.start,
                "end": event.seen,
                "energy": self._kwh(event.wh),
                "expected": self._kwh(event.expected_wh),
                "peak": f"{event.peak_w:.0f} W",
            },
        )

    def _kwh(self, wh: float) -> str:
        text = f"{wh / 1000:.2f}"
        return text.replace(".", ",") if self._comma else text
