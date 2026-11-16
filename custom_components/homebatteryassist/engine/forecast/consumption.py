"""House consumption forecast per slot of the planning window.

Made by a consumption forecaster module (``forecasts/forecasters``; default
the built-in weekday/hour profile) from the consumption history (excluded
devices such as an EV charger are not part of it), checked by
HomeBatteryAssist (``raw_forecast``).

Per slot: forecaster (``base_w``) -> learned or manual correction (``accuracy``)
-> user adjustments (``adjustments``, applied last because they are intent).
``raw_w`` (profile + adjustments, without correction) is what accuracy learns
from. Like every forward calculation, it only calculates within the planning
window.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..history.consumption import ConsumptionRecord
from .adjustments import Adjustment, apply_adjustments
from .forecasters import (
    BUILTIN,
    DEFAULT_FORECASTER,
    Forecaster,
    ForecasterInput,
    ForecasterResult,
)
from .forecasters.profile import (
    HALF_LIFE,
    METHODS,
    MIN_DAYS,
    ConsumptionProfile,
)
from .horizon import PlanningWindow

__all__ = [
    "HALF_LIFE",
    "METHODS",
    "MIN_DAYS",
    "ConsumptionProfile",
    "ForecastSlot",
    "forecast_consumption",
    "raw_forecast",
]

MAX_W = 100_000.0  # a prediction above this is not believed


@dataclass(frozen=True, slots=True)
class ForecastSlot:
    """Expected house consumption in one slot."""

    start: datetime
    end: datetime
    power_w: float  # final: corrected profile + adjustments
    base_w: float  # from the history profile
    method: str
    adjustments: tuple[str, ...] = ()  # names of applied adjustments
    raw_w: float | None = None  # profile + adjustments, without correction

    @property
    def raw(self) -> float:
        """The uncorrected prediction (learning input)."""
        return self.raw_w if self.raw_w is not None else self.power_w


def raw_forecast(
    forecaster: Forecaster | None,
    records: Sequence[ConsumptionRecord],
    window: PlanningWindow,
    step: timedelta,
    now: datetime,
    profile: list[tuple[float | None, str | None]] | None = None,
) -> list[tuple[datetime, datetime, float, str]]:
    """``forecaster``'s prediction per slot of ``window`` after
    HomeBatteryAssist's final check: a missing, negative, non-finite or absurd
    value is replaced by the built-in profile's prediction (slots without
    either are left out). Raises what the forecaster raises.
    """
    if window.is_empty:
        return []
    slots = list(window.slots(step))
    data = ForecasterInput(now, slots, records, step)
    if profile is None:
        profile = _profile(data)
    forecaster = forecaster or BUILTIN[DEFAULT_FORECASTER]
    if forecaster.key == DEFAULT_FORECASTER and type(forecaster) is type(
        BUILTIN[DEFAULT_FORECASTER]
    ):
        own = profile
    else:
        result = forecaster.forecast(data)
        if not isinstance(result, ForecasterResult):
            result = ForecasterResult(list(result))
        methods = result.methods or []
        own = [
            (
                result.values[i] if i < len(result.values) else None,
                (methods[i] if i < len(methods) else None) or forecaster.key,
            )
            for i in range(len(slots))
        ]
    out = []
    for (start, end), (value, method), (fallback, fallback_method) in zip(
        slots, own, profile, strict=True
    ):
        try:
            number = float(value) if value is not None else None
        except (TypeError, ValueError):
            number = None
        if number is None or not math.isfinite(number) or not 0 <= number <= MAX_W:
            if fallback is None:
                continue
            number, method = fallback, fallback_method or DEFAULT_FORECASTER
        out.append((start, end, round(number, 1), method or forecaster.key))
    return out


def _profile(data: ForecasterInput) -> list[tuple[float | None, str | None]]:
    result = BUILTIN[DEFAULT_FORECASTER].forecast(data)
    methods = result.methods or [None] * len(result.values)
    return list(zip(result.values, methods, strict=True))


def forecast_consumption(
    records: Iterable[ConsumptionRecord],
    window: PlanningWindow,
    step: timedelta,
    adjustments: Iterable[Adjustment] = (),
    now: datetime | None = None,
    correct: Callable[[float, datetime], float] | None = None,
    forecaster: Forecaster | None = None,
) -> list[ForecastSlot]:
    """Expected consumption per slot of ``window`` (empty without history),
    by ``forecaster`` (default: the built-in profile).

    ``correct(value, slot_start)`` applies the accuracy correction.
    """
    records = list(records)
    adjustments = list(adjustments)
    slots: list[ForecastSlot] = []
    for start, end, base, method in raw_forecast(
        forecaster, records, window, step, now or window.start
    ):
        raw, applied = apply_adjustments(base, start, end, adjustments)
        corrected = round(correct(base, start), 1) if correct else base
        power, _ = apply_adjustments(corrected, start, end, adjustments)
        slots.append(ForecastSlot(start, end, power, base, method, applied, raw))
    return slots
