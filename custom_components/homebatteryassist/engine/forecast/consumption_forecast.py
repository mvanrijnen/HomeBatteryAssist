"""House consumption forecast per slot of the planning window.

Made by a consumption forecaster module (``forecasts/forecasters``; default
the built-in weekday/hour profile) from the consumption history (excluded
devices such as an EV charger are not part of it), checked by
HomeBatteryAssist (``raw_forecast``).

Per slot: forecaster -> temperature step (optional, ``temperature_effect``;
together ``base_w``) -> learned or manual correction (``accuracy``)
-> user adjustments (``adjustments``, applied last because they are intent).
``raw_w`` (the forecaster's value, without correction and without the user's
adjustments — those are intent, not a forecast error) is what accuracy learns
from. Like every forward calculation, it only calculates within the planning
window.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ..history.consumption_history import ConsumptionRecord
from .forecasters import (
    BUILTIN,
    DEFAULT_FORECASTER,
    Forecaster,
    ForecasterInput,
    ForecasterResult,
)
from .forecasters.weekday_hour_profile import (
    HALF_LIFE,
    METHODS,
    MIN_DAYS,
    ConsumptionProfile,
)
from .planning_window import PlanningWindow
from .temperature_effect import TemperatureEffect
from .user_adjustments import Adjustment, apply_adjustments, rebalance_parts

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
    temperatures: Sequence[float | None] | None = None,
    temperature: TemperatureEffect | None = None,
) -> list[tuple[datetime, datetime, float, str]]:
    """``forecaster``'s prediction per slot of ``window`` after
    HomeBatteryAssist's final check: a missing, negative, non-finite or absurd
    value is replaced by the built-in profile's prediction (slots without
    either are left out). With a learned ``temperature`` model and a
    forecast per slot (``temperatures``), the temperature step is added
    (unless the forecaster does that itself). Raises what the forecaster
    raises.
    """
    if window.is_empty:
        return []
    slots = list(window.slots(step))
    data = ForecasterInput(now, slots, records, step, temperatures)
    if profile is None:
        profile = _profile(data)
    forecaster = forecaster or BUILTIN[DEFAULT_FORECASTER]
    step_on = (
        temperature is not None
        and temperature.active
        and temperatures is not None
        and not forecaster.uses_temperature
    )
    if forecaster.key == DEFAULT_FORECASTER and type(forecaster) is type(
        BUILTIN[DEFAULT_FORECASTER]
    ):
        own = profile
        refs: list = [None] * len(slots)
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
        refs = [_reference(r) for r in list(result.reference_temps or [])[: len(slots)]]
        refs += [None] * (len(slots) - len(refs))
    out = []
    for i, ((start, end), (value, method), (fallback, fallback_method)) in enumerate(
        zip(slots, own, profile, strict=True)
    ):
        try:
            number = float(value) if value is not None else None
        except (TypeError, ValueError):
            number = None
        if number is None or not math.isfinite(number) or not 0 <= number <= MAX_W:
            if fallback is None:
                continue
            number, method = fallback, fallback_method or DEFAULT_FORECASTER
            refs[i] = None  # the profile: its usual weather
        if step_on and i < len(temperatures):  # type: ignore[arg-type]
            extra = temperature.effect(start, temperatures[i], refs[i])  # type: ignore[index,union-attr]
            number = min(max(number + extra, 0.0), MAX_W)
        out.append((start, end, round(number, 1), method or forecaster.key))
    return out


def _reference(value: Any) -> list[float] | None:
    """A forecaster's reference temperatures for a slot: a list of finite
    numbers, else None (the profile's usual weather)."""
    if not isinstance(value, (list, tuple)) or not value:
        return None
    try:
        temps = [float(t) for t in value]
    except (TypeError, ValueError):
        return None
    return temps if all(math.isfinite(t) for t in temps) else None


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
    temperatures: Sequence[float | None] | None = None,
    temperature: TemperatureEffect | None = None,
) -> list[ForecastSlot]:
    """Expected consumption per slot of ``window`` (empty without history),
    by ``forecaster`` (default: the built-in profile).

    ``correct(value, slot_start)`` applies the accuracy correction.
    """
    records = list(records)
    adjustments = list(adjustments)
    rows: list[tuple[datetime, datetime, float, str, tuple[str, ...], float]] = []
    for start, end, base, method in raw_forecast(
        forecaster,
        records,
        window,
        step,
        now or window.start,
        temperatures=temperatures,
        temperature=temperature,
    ):
        corrected = round(correct(base, start), 1) if correct else base
        power, applied = apply_adjustments(corrected, start, end, adjustments)
        rows.append((start, end, base, method, applied, power))
    # Energy that is part of the learned consumption: taken from the rest of
    # its day.
    balanced = rebalance_parts(
        [(start, end, power, applied) for start, end, _b, _m, applied, power in rows],
        adjustments,
    )
    return [
        ForecastSlot(start, end, power, base, method, applied, base)
        for (start, end, base, method, _a, _p), (_s, _e, power, applied) in zip(
            rows, balanced, strict=True
        )
    ]
