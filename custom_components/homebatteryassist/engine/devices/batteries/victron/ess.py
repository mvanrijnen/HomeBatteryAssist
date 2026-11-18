"""Type: Victron ESS (MultiPlus-II / Quattro with a GX device).

Generic: capacity and power depend on the inverters and batteries installed,
so nothing is set here; they come from the GX (ESS limits) or the user. One
Multi per phase in a 3-phase set; a single Multi is on one phase.
"""

from __future__ import annotations

from . import Victron


class VictronEss(Victron):
    """A Victron ESS."""

    range = "ESS"
    type = "ESS (MultiPlus-II / Quattro)"
