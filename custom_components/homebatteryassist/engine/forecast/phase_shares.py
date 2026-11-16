"""Expected grid load per phase, for the phase limits of the battery plan.

The consumption forecast is a total for the house. How it is spread over the
phases is learned from the history: every record keeps the house consumption
per phase (``phase_house_w``) and the PV production per phase
(``phase_pv_w``). The share per phase is taken per local hour of the day
(the house often uses other phases in the evening than at night), falling back
to the share over all hours, and to an even split without history.

    load_p = consumption x house share_p(hour) - PV x PV share_p

Like every forward calculation, this only covers the slots it is given (within
the planning window).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime

from homeassistant.util import dt as dt_util

from ..history.consumption_history import ConsumptionRecord
from .consumption_forecast import ForecastSlot


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
        house_all = [0.0] * phases
        pv_all = [0.0] * phases
        self.samples = 0
        for record in records:
            weight = record["minutes"] * record["coverage"]
            if (house := record.get("phase_house_w")) and len(house) == phases:
                start = dt_util.parse_datetime(record["start"])
                hour = dt_util.as_local(start).hour if start else 0
                acc = house_hour.setdefault(hour, [0.0] * phases)
                for i, value in enumerate(house):
                    acc[i] += max(value, 0.0) * weight
                    house_all[i] += max(value, 0.0) * weight
                self.samples += 1
            if (pv := record.get("phase_pv_w")) and len(pv) == phases:
                for i, value in enumerate(pv):
                    pv_all[i] += max(value, 0.0) * weight
        even = [1 / phases] * phases
        self.house = _shares(house_all) or even
        self.house_hour = {h: _shares(v) or self.house for h, v in house_hour.items()}
        self.pv = _shares(pv_all) or even

    def house_share(self, when: datetime) -> list[float]:
        """Share of the house consumption per phase at ``when``."""
        return self.house_hour.get(dt_util.as_local(when).hour, self.house)

    def loads(
        self, consumption: Sequence[ForecastSlot], pv_wh: Mapping[datetime, float]
    ) -> dict[datetime, list[float]]:
        """Expected grid power per phase (+ import / - export) per slot start."""
        result = {}
        for slot in consumption:
            hour = slot.start.replace(minute=0, second=0, microsecond=0)
            pv = pv_wh.get(hour, 0.0)
            result[slot.start] = [
                round(slot.power_w * h - pv * p, 1)
                for h, p in zip(self.house_share(slot.start), self.pv, strict=True)
            ]
        return result
