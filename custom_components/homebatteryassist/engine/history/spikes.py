"""Short peaks in the history: leave random ones out of the average.

The spike filter (``engine/measure/spike_filters``) records the energy of
short peaks apart (``spike_w`` per history record). A peak that comes back
regularly — on most days of the same day of the week, at the same hour (e.g.
the coffee every weekday morning) — is not random but normal consumption: it
stays in the average, and the battery covers it. Only the other peaks are left
out of the consumption forecast and its accuracy check.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

RECENT_WEEKS = 4  # weeks looked back for regular peaks
REGULAR_SHARE = 0.5  # on at least this share of those days ...
REGULAR_MIN_DAYS = 2  # ... and on at least this many days


def regular_peak_hours(
    records: Iterable[Mapping[str, Any]], now: datetime
) -> set[tuple[int, int]]:
    """(weekday, local hour) where peaks come back regularly."""
    since = now - timedelta(weeks=RECENT_WEEKS)
    measured: dict[tuple[int, int], set] = defaultdict(set)
    peaks: dict[tuple[int, int], set] = defaultdict(set)
    for record in records:
        start = dt_util.parse_datetime(str(record["start"]))
        if (
            start is None
            or start < since
            or not record.get("coverage")
            or record.get("vacation")  # vacation and excluded days
            # Imported records never know their peaks: counted as days
            # without one they would hide a regular peak for weeks.
            or record.get("source") == "import"
        ):
            continue
        local = dt_util.as_local(start)
        key = (local.weekday(), local.hour)
        measured[key].add(local.date())
        if record.get("spike_w", 0) > 0:
            peaks[key].add(local.date())
    return {
        key
        for key, days in peaks.items()
        if len(days) >= REGULAR_MIN_DAYS
        and len(days) >= REGULAR_SHARE * len(measured[key])
    }


def is_regular(regular: set[tuple[int, int]], when: datetime) -> bool:
    """Whether peaks come back regularly at ``when``."""
    local = dt_util.as_local(when)
    return (local.weekday(), local.hour) in regular


def without_spikes(
    records: Sequence[Mapping[str, Any]], regular: set[tuple[int, int]]
) -> list[Mapping[str, Any]]:
    """The records with the energy of random peaks taken out of ``avg_w``."""
    out: list[Mapping[str, Any]] = []
    for record in records:
        spike = record.get("spike_w", 0)
        if not spike:
            out.append(record)
            continue
        start = dt_util.parse_datetime(str(record["start"]))
        if start is not None and is_regular(regular, start):
            out.append(record)
            continue
        out.append({**record, "avg_w": round(max(record["avg_w"] - spike, 0.0), 1)})
    return out
