"""Template for a new PV inverter driver — a code example only.

Never registered. Copy this file, describe how the inverter is limited
(``points``: the settings it would write, ``{limit_w}`` = the limit in W),
and add the driver to ``DRIVERS`` in ``__init__.py``. In this phase nothing
is sent: ``enabled`` stays False and ``async_set_limit`` is never called.
"""

from __future__ import annotations

from .base import InverterDriver, Point


class TemplateInverterDriver(InverterDriver):
    """Example: the inverter ``my_inverter`` (does not exist)."""

    key = "my_inverter"
    name = "My inverter"
    limits = "power"
    points = (
        Point(1000, "Power limit on", "1"),
        Point(1001, "Power limit (W)", "{limit_w}"),
    )
