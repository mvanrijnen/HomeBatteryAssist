"""The interface of a PV correction module.

A PV correction adjusts the PV forecast (Wh per clock hour) with what was
learned from earlier forecasts and the PV production measured afterwards.
It gets the raw forecast, the past results (per hour: what was measured and
what each lead time had predicted) and the built-in correction per lead time,
and returns the corrected Wh per hour.

HomeBatteryAssist keeps the final say: a missing, negative, non-finite or
absurd value (more than ``MAX_FACTOR`` times the raw forecast plus
``MAX_EXTRA_WH``) is replaced by the built-in correction per lead time. The
accuracy is always measured on the *raw* forecast, so a correction never
feeds back on itself; every correction is also checked on its own, to compare
them. A correction only reads: it never controls anything.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

MAX_FACTOR = 3.0
MAX_EXTRA_WH = 100.0


@dataclass(frozen=True, slots=True)
class PvResult:
    """One past hour: measured and predicted PV energy."""

    start: datetime  # UTC hour start
    actual: float  # measured Wh
    predictions: Mapping[str, float]  # lead time bucket -> raw forecast Wh


@dataclass(frozen=True, slots=True)
class PvCorrectionInput:
    """Everything a PV correction gets."""

    now: datetime
    slots: Sequence[tuple[datetime, float]]  # (UTC hour start, raw forecast Wh)
    results: Sequence[PvResult]  # the last weeks, oldest first
    # The built-in factor per lead time for a slot start (1.0 = none) ...
    lead_factor: Callable[[datetime], float]
    # ... and per lead time bucket ("0-1h" .. "5d+"), as learned now.
    bucket_factors: Mapping[str, float]


class PvCorrector:
    """Base class of a PV correction module.

    Subclasses set ``key`` (unique, lowercase), ``name`` and implement
    ``correct``. It runs in the event loop and must be quick (no I/O).
    """

    key: str = ""
    name: str = ""
    # Tested on a real setup; until then every place where it is chosen
    # says "not tested". Own modules too: set True only after testing.
    verified: bool = False

    def correct(self, data: PvCorrectionInput) -> Sequence[float | None]:
        """Corrected Wh per slot of ``data.slots`` (None = the built-in one)."""
        raise NotImplementedError

    def details(self) -> dict[str, Any]:
        """What was learned, for the diagnostics (optional)."""
        return {}
