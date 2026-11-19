"""The interface of a consumption forecaster module.

A forecaster predicts the house consumption (average W) per slot of the
planning window from the consumption history. HomeBatteryAssist keeps the
final say (``forecasts.consumption.raw_forecast``): a missing, negative or
absurd value is replaced by the built-in profile's prediction; the learned or
manual correction and the user's adjustments are applied after that. The
accuracy of every forecaster is tracked side by side, so they can be compared.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass(frozen=True, slots=True)
class ForecasterInput:
    """Everything a forecaster gets.

    ``history``: the consumption records, oldest first (do not change them):
    dicts with ``start`` (ISO, UTC), ``minutes``, ``avg_w`` (house, W),
    ``coverage`` (0-1, measured part), optional ``pv_w``, ``excluded_w``,
    ``battery_w``, ``vacation`` (True: not the usual consumption) and
    ``source`` ("import" for imported history), and optionally
    ``heating_w`` (heating/cooling, part of ``avg_w``) and ``temp_c``
    (outdoor temperature).

    ``temperatures``: the forecast outdoor temperature per slot (°C, None =
    unknown), or None when no weather is set up.
    """

    now: datetime
    slots: list[tuple[datetime, datetime]]
    history: Sequence[Mapping[str, Any]]
    interval: timedelta
    temperatures: Sequence[float | None] | None = None


@dataclass(slots=True)
class ForecasterResult:
    """Expected consumption per slot (W, None = no idea) and optionally the
    method used per slot (shown in the explanation) and the weather it was
    made from (``reference_temps``)."""

    values: list[float | None]
    methods: list[str | None] | None = None
    # Optional per slot: the outdoor temperatures (°C) of the records a value
    # was made from. HomeBatteryAssist's temperature step then adds only the
    # difference between the forecast and that weather (None: the usual
    # weather of the profile).
    reference_temps: list[list[float] | None] | None = None


class Forecaster:
    """Base class of a consumption forecaster module.

    Subclasses set ``key`` (unique, lowercase), ``name`` and implement
    ``forecast``. It runs in the event loop and must be quick (no I/O).
    """

    key: str = ""
    name: str = ""
    # Tested on a real setup; until then every place where it is chosen
    # says "not tested". Own modules too: set True only after testing.
    verified: bool = False
    description: str = ""
    # True: the forecaster takes the temperature into account itself, so
    # HomeBatteryAssist does not add its temperature step on top.
    uses_temperature: bool = False

    def forecast(self, data: ForecasterInput) -> ForecasterResult | list[float | None]:
        """Expected consumption per slot of ``data.slots``, in W."""
        raise NotImplementedError
