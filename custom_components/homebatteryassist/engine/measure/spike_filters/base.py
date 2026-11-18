"""The interface of a spike filter module.

A spike filter recognises short, high consumption peaks (a kettle, a
microwave, an induction hob) in the measured house consumption, while it
happens. HomeBatteryAssist uses what it says in two ways, each switched on or
off in the settings (section *Short peaks*):

- **battery**: zero on the meter does not discharge (extra) for the part of
  the consumption the filter calls a peak (``SpikeState.ignore_w``) — the grid
  supplies it;
- **average consumption**: the energy of peaks that ended (``ended_wh``) is
  recorded apart in the history (``spike_w``) and left out of the consumption
  forecast and its accuracy check.

The filter sees the consumption as a stream: ``update`` is called with every
new value (about every 1 to 10 s) and keeps its own state. It cannot know the
future: a peak is a candidate while it lasts; when it ends within the allowed
time it was a peak, when it lasts longer it is normal consumption from then on.

HomeBatteryAssist keeps the final say: ``ignore_w`` is kept between 0 and the
consumption, ``ended_wh`` between 0 and ``MAX_SPIKE_WH``; anything else counts
as no peak.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

MAX_SPIKE_WH = 5000.0  # one peak; anything more is not believed


@dataclass(frozen=True, slots=True)
class SpikeState:
    """What the filter says about the consumption now."""

    ignore_w: float = 0.0  # part of the consumption now that is a (candidate) peak
    ended_wh: float = 0.0  # energy of a peak that just ended (once)


class SpikeFilter:
    """Base class of a spike filter module.

    Subclasses set ``key`` (unique, lowercase), ``name`` and implement
    ``update``. HomeBatteryAssist creates a fresh instance per start and sets
    ``threshold_w`` and ``max_duration_s`` from the settings before the first
    ``update``; a filter may use them or have its own rules. It runs in the
    event loop and must be quick (no I/O).
    """

    key: str = ""
    name: str = ""
    # Tested on a real setup; until then every place where it is chosen
    # says "not tested". Own modules too: set True only after testing.
    verified: bool = False
    threshold_w: float = 2000.0  # a rise of at least this much can be a peak
    max_duration_s: float = 300.0  # a peak lasts at most this long

    def update(self, when: datetime, house_w: float | None) -> SpikeState:
        """The new house consumption (W; None = unknown) at ``when``."""
        raise NotImplementedError

    def details(self) -> dict[str, Any]:
        """What the filter saw, for the diagnostics (optional)."""
        return {}
