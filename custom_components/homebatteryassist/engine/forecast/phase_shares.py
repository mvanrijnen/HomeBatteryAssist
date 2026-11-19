"""Expected grid load per phase, for the phase limits of the battery plan.

The consumption forecast is a total for the house. How it is spread over the
phases is learned from the history: every record keeps the house consumption
per phase (``phase_house_w``) and the PV production per phase
(``phase_pv_w``). The share per phase is taken per local hour of the day
(the house often uses other phases in the evening than at night), falling back
to the share over all hours, and to an even split without history.

    load_p = consumption x house share_p(hour) - PV x PV share_p(hour)

The PV share is per local hour too: roofs facing east and west, or an
inverter per roof on another phase, give the morning to other phases than
the afternoon.

The fuse sees current, not power. With a meter that measures current the
history also has the net power and current per phase; from those the
current that flows besides the power (reactive and distortion: standby
devices, chargers, motors) is learned per phase as a power ``Q_p``: the
median over the records of ``phase_q``, worked out per reading as
sqrt((V x I)^2 - P^2) at 230 V (``history.consumption_history.reactive_w``;
not from the averages of an interval, where a load switching on and off would
look like reactive power). The expected load then
counts as sqrt(load_p^2 + Q_p^2) (with the sign of load_p): what the current
will be, at nominal voltage, as the phase limit is expressed.

Like every forward calculation, this only covers the slots it is given (within
the planning window).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime

from homeassistant.util import dt as dt_util

from ..history.consumption_history import ConsumptionRecord
from .consumption_forecast import ForecastSlot

MIN_SAMPLES = 4  # records with measured current (an hour of 15 minutes)


def _shares(totals: Sequence[float]) -> list[float] | None:
    clipped = [max(v, 0.0) for v in totals]
    total = sum(clipped)
    return [v / total for v in clipped] if total > 0 else None


class PhaseProfile:
    """Share of the house consumption and PV production per phase."""

    def __init__(self, records: Iterable[ConsumptionRecord], phases: int) -> None:
        """Learn the shares from the history records."""
        self.phases = phases
        house_hour: dict[int, list[float]] = {}
        pv_hour: dict[int, list[float]] = {}
        house_all = [0.0] * phases
        pv_all = [0.0] * phases
        reactive: list[list[float]] = [[] for _ in range(phases)]
        self.samples = 0
        for record in records:
            if (q := record.get("phase_q")) and len(q) == phases:
                for i, value in enumerate(q):
                    reactive[i].append(max(float(value), 0.0))
            weight = record["minutes"] * record["coverage"]
            start = dt_util.parse_datetime(record["start"])
            hour = dt_util.as_local(start).hour if start else 0
            if (house := record.get("phase_house_w")) and len(house) == phases:
                acc = house_hour.setdefault(hour, [0.0] * phases)
                for i, value in enumerate(house):
                    acc[i] += max(value, 0.0) * weight
                    house_all[i] += max(value, 0.0) * weight
                self.samples += 1
            if (pv := record.get("phase_pv_w")) and len(pv) == phases:
                acc = pv_hour.setdefault(hour, [0.0] * phases)
                for i, value in enumerate(pv):
                    acc[i] += max(value, 0.0) * weight
                    pv_all[i] += max(value, 0.0) * weight
        even = [1 / phases] * phases
        self.house = _shares(house_all) or even
        self.house_hour = {h: _shares(v) or self.house for h, v in house_hour.items()}
        self.pv = _shares(pv_all) or even
        self.pv_hour = {h: _shares(v) or self.pv for h, v in pv_hour.items()}
        # Current besides the power per phase (W at 230 V); 0 until an hour
        # of measured current is known.
        self.reactive = [
            round(statistics.median(values), 1) if len(values) >= MIN_SAMPLES else 0.0
            for values in reactive
        ]

    def house_share(self, when: datetime) -> list[float]:
        """Share of the house consumption per phase at ``when``."""
        return self.house_hour.get(dt_util.as_local(when).hour, self.house)

    def pv_share(self, when: datetime) -> list[float]:
        """Share of the PV production per phase at ``when``."""
        return self.pv_hour.get(dt_util.as_local(when).hour, self.pv)

    def loads(
        self, consumption: Sequence[ForecastSlot], pv_wh: Mapping[datetime, float]
    ) -> dict[datetime, list[float]]:
        """Expected grid power per phase (+ import / - export) per slot start."""
        result = {}
        for slot in consumption:
            hour = slot.start.replace(minute=0, second=0, microsecond=0)
            pv = pv_wh.get(hour, 0.0)
            result[slot.start] = [
                round(self._with_reactive(slot.power_w * h - pv * p, q), 1)
                for h, p, q in zip(
                    self.house_share(slot.start),
                    self.pv_share(slot.start),
                    self.reactive,
                    strict=True,
                )
            ]
        return result

    @staticmethod
    def _with_reactive(load: float, reactive: float) -> float:
        """The load as the current it will draw (W at 230 V), signed."""
        if reactive <= 0:
            return load
        return math.copysign(math.hypot(load, reactive), load)
