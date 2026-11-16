"""Brand: Indevolt. Ranges and types inherit from it (``flex.py`` →
``flex_*.py`` / ``solidflex_3600.py``; ``bk.py`` → ``bk1600.py``). Read
directly over the local HTTP API: ``http.py`` (prepared, not used).

A type is recognised by its model code (data point 1); one code names a
family, the exact variant (AC / Hybrid / Pro / Eco) is not readable locally.
"""

from __future__ import annotations

from ..base import BatteryModel


class Indevolt(BatteryModel):
    """Indevolt batteries."""

    brand = "Indevolt"
    api_generation: int = 2  # local API generation the data points are for
    min_firmware: str | None = None  # vendor minimum CMS firmware (f_ver)
