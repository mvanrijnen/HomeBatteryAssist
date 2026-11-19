"""Unexpected solar surplus or shortage: what is measured now against the forecast.

The accuracy per lead time (``forecast_accuracy.py``) settles a forecast
afterwards; this check says it while it happens: when clearly more solar power
is left over than the forecast for this hour expected (a *surplus*), or
clearly less (a *shortage*: clouds, or the house uses more), *Why* tells so
once (and once more when it is over), with what it means for the batteries.

Surplus = PV - house - excluded devices (what the batteries could store);
expected = PV forecast for this hour (corrected) - consumption forecast for
this slot. Unexpected surplus: at least ``threshold_w`` measured and less than
half of it forecast; unexpected shortage: at least ``threshold_w`` forecast
and less than half of it measured (the rules are in ``house_measurement``).
Told after ``start_after`` on end (a passing gap in the clouds is no
message); over after ``END_AFTER`` without it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ..measure.house_measurement import (
    MIN_SURPLUS_W,
    unexpected_shortage,
    unexpected_surplus,
)

START_AFTER = timedelta(minutes=5)
END_AFTER = timedelta(minutes=10)
MAX_GAP = timedelta(minutes=2)  # longer without a value: start counting anew


@dataclass
class _Event:
    start: datetime
    seen: datetime
    wh: float = 0.0  # measured surplus during the event
    expected_wh: float = 0.0  # what was forecast of it
    peak_w: float = 0.0  # most surplus (surplus) / most missing (shortage)


def unexpected(
    surplus_w: float,
    expected_w: float,
    threshold_w: float = MIN_SURPLUS_W,
    shortage: bool = False,
) -> bool:
    """A surplus (or, with ``shortage``, a lack of one) the forecast did not
    see coming."""
    if shortage:
        return unexpected_shortage(surplus_w, expected_w, threshold_w)
    return unexpected_surplus(surplus_w, expected_w, threshold_w)


class UnexpectedSurplus:
    """Follows the measured surplus; ``update`` returns a message to log.

    ``shortage=True`` follows the other direction: a forecast surplus that is
    not there.
    """

    def __init__(
        self,
        decimal_comma: bool = False,
        shortage: bool = False,
        threshold_w: float = MIN_SURPLUS_W,
        start_after: timedelta = START_AFTER,
    ) -> None:
        """Initialize."""
        self._comma = decimal_comma
        self.shortage = shortage
        self.threshold_w = threshold_w
        self.start_after = start_after
        self._key = "pv_shortage_unexpected" if shortage else "pv_surplus_unexpected"
        self.event: _Event | None = None
        self._since: datetime | None = None  # unexpected since (before start)
        self._quiet: datetime | None = None  # expected again since (in event)
        self._last: datetime | None = None

    def _peak(self, surplus_w: float, expected_w: float) -> float:
        if self.shortage:
            return max(expected_w, 0.0) - max(surplus_w, 0.0)
        return surplus_w

    def update(
        self,
        when: datetime,
        surplus_w: float | None,
        expected_w: float | None,
        nom: bool = True,
    ) -> tuple[str, dict[str, Any]] | None:
        """One measurement; ``None`` values = unknown (no PV or forecast).

        ``nom``: the batteries follow zero on the meter (they store a surplus
        and cover a shortage by themselves) rather than a plan per slot.
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
        if not unexpected(surplus_w, expected_w, self.threshold_w, self.shortage):
            self._since = None
            if self.event is None:
                return None
            # Not unexpected any more: nothing is added (the total covers the
            # event up to the end the message names).
            return self._maybe_end(when)
        if self.event is not None:
            self._quiet = None
            self.event.seen = when
            self.event.peak_w = max(
                self.event.peak_w, self._peak(surplus_w, expected_w)
            )
            self._add(surplus_w, expected_w, hours)
            return None
        if self._since is None or hours == 0.0:
            self._since = when
        if when - self._since < self.start_after:
            return None
        # What was left over since it began counts too.
        start_hours = (when - self._since).total_seconds() / 3600
        self.event = _Event(
            self._since,
            when,
            wh=max(surplus_w, 0.0) * start_hours,
            expected_wh=max(expected_w, 0.0) * start_hours,
            peak_w=self._peak(surplus_w, expected_w),
        )
        self._since = None
        kind = "shortage" if self.shortage else "surplus"
        return (
            self._key,
            {
                "surplus": f"{max(surplus_w, 0.0):.0f} W",
                "expected": f"{max(expected_w, 0.0):.0f} W",
                "since": self.event.start,
                "battery": f"@{kind}_nom" if nom else f"@{kind}_plan",
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
            f"{self._key}_ended",
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
