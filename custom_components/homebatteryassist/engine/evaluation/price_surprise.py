"""Published prices that differ strongly from the estimate the plan used.

An estimated (forecast) price is replaced by the published one once the
source publishes it (for the Netherlands around 13:00 for the next day). When
the published price differs a lot from the estimate the plan was built on,
the plan changes noticeably at that moment; ``PriceSurprises`` finds those
periods so the *Why* log can say so.

The estimates are remembered as the plan used them (after the learned
correction, before the tariff), so they compare with the source's published
prices. A period is compared once its published prices cover it completely
(an hourly estimate against four quarter prices: the time-weighted mean).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

# A published price that differs at least this much per kWh (main currency)
# from the estimate is a surprise; smaller differences are normal noise.
SURPRISE_PER_KWH = 0.08
# Estimates whose period ended this long ago are forgotten.
KEEP = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class PriceSurprise:
    start: datetime
    end: datetime
    estimate: float
    published: float

    @property
    def difference(self) -> float:
        return self.published - self.estimate


class PriceSurprises:
    """Remembers the estimates in use and compares them when published."""

    def __init__(self, threshold: float = SURPRISE_PER_KWH) -> None:
        self.threshold = threshold
        self._estimates: dict[datetime, tuple[datetime, float]] = {}

    def remember(self, estimates: Iterable[tuple[datetime, datetime, float]]) -> None:
        """The estimated prices (start, end, price) the plan uses now."""
        for start, end, price in estimates:
            self._estimates[start] = (end, price)

    def check(
        self, published: Iterable[tuple[datetime, datetime, float]], now: datetime
    ) -> list[PriceSurprise]:
        """Settle every remembered estimate that the published prices now cover
        completely; return those that differ at least the threshold, largest
        difference first."""
        periods = sorted(published)
        surprises: list[PriceSurprise] = []
        for start, (end, estimate) in list(self._estimates.items()):
            if end <= now - KEEP:
                del self._estimates[start]
                continue
            total = covered = 0.0
            for p_start, p_end, price in periods:
                if p_end <= start or p_start >= end:
                    continue
                seconds = (min(p_end, end) - max(p_start, start)).total_seconds()
                total += price * seconds
                covered += seconds
            if covered < (end - start).total_seconds() - 1:
                continue  # not (completely) published yet
            del self._estimates[start]
            value = total / covered
            if abs(value - estimate) >= self.threshold:
                surprises.append(PriceSurprise(start, end, estimate, value))
        surprises.sort(key=lambda s: -abs(s.difference))
        return surprises
