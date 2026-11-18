"""Victron ESS: the GX limits the feed-in of the whole system (DC- and
AC-coupled PV, batteries) — PREPARED, NOT TESTED.

Modbus TCP on the GX, unit 100: **2706** = maximum system feed-in in units
of 100 W (-1 = no limit). Related: 2707 (DC-coupled PV may feed in
overvoltage, 1 = yes) and 2708 (AC-coupled PV feed-in, inverted: 1 = prevent).
Through Home Assistant's Victron GX integration this is the number
``system_ess_max_feed_in_power`` (W, -1 = no limit). The GX keeps the export
within it itself, so this limits the **export**. In this phase nothing is
sent.
"""

from __future__ import annotations

from .base import InverterDriver, Point

UNIT = 100


class VictronGxFeedInDriver(InverterDriver):
    """Victron GX: maximum system feed-in (export limit)."""

    key = "victron_gx_feed_in"
    name = "Victron GX"
    limits = "export"
    points = (
        Point(2706, "Max feed-in (x 100 W, -1 = no limit)", "{limit_w} W / 100", UNIT),
    )
