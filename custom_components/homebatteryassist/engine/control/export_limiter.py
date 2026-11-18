"""The export limit live: what the inverters would be limited to, and how
much export that would have stopped.

Advice only in this phase: every measurement the limit is worked out
(``engine/planning/export_limit.py``) on the grid as HomeBatteryAssist's
batteries make it (with a twin: the twin instead of the real battery); the
export above the limit is what the inverters would have produced less.
*Why* tells when that starts and ends (minutes, kWh, what it was worth at
the export price). No inverter driver is ever called: ``CONTROL`` is False.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.util import dt as dt_util

from ..explain import DecisionLog
from ..planning.export_limit import (
    REASON_NEVER,
    REASON_PRICE,
    ExpectedLimit,
    ExportLimit,
    expected_limits,
    export_limit,
)

# Nothing is sent to an inverter in this phase (tested).
CONTROL = False
# Export above the limit from this much on counts as "would be limited".
MIN_CURTAIL_W = 50.0
# A limit without curtailment for this long ends the episode in *Why*.
END_AFTER = timedelta(minutes=5)
# Listeners (the sensor) at most this often, unless the limit changes.
NOTIFY_EVERY = timedelta(seconds=10)


class ExportLimiter:
    """Follows the export limit and what it would curtail."""

    def __init__(
        self,
        decisions: DecisionLog,
        *,
        enabled: bool,
        threshold: float,
        fixed_w: float,
        cost: float = 0.0,
        never: bool = False,
        connection: float,
        capacity: dict[str, Any] | None = None,
        inverters: list[tuple[str, Any, str]],  # (name, driver, address)
        decimal_comma: bool = False,
    ) -> None:
        """Initialize."""
        self._decisions = decisions
        self.enabled = enabled
        self.threshold = threshold
        self.cost = cost
        self.never = never
        self.fixed_w = fixed_w
        self.connection = connection
        # How the most that can be exported was found (connection,
        # inverter breakers, batteries), for the sensor.
        self.capacity = capacity or {}
        self.inverters = inverters
        self._comma = decimal_comma
        self.limit = ExportLimit(connection, False, "none")
        self.price: float | None = None
        self.export_w: float | None = None  # export now (W, >= 0)
        self.curtailed_w = 0.0  # what the inverters would produce less now
        self._event: dict[str, Any] | None = None
        self._last: datetime | None = None
        self._day = ""
        self.today_kwh = 0.0
        self._listeners: list[Callable[[], None]] = []
        # Coming periods in which export would be limited (from the plan).
        self.expected: list[ExpectedLimit] = []
        self._told: set[datetime] = set()  # starts of periods told
        self._notified: datetime | None = None

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call ``listener`` when the limit or the curtailment changes."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _num(self, value: float, digits: int) -> str:
        text = f"{value:.{digits}f}"
        return text.replace(".", ",") if self._comma else text

    def update(self, when: datetime, grid_w: float | None, price: float | None) -> None:
        """A new measurement: the grid (W, + import) and the export price."""
        hours = (
            min((when - self._last).total_seconds(), 60.0) / 3600 if self._last else 0
        )
        self._last = when
        day = dt_util.as_local(when).date().isoformat()
        if day != self._day:
            self._day, self.today_kwh = day, 0.0
        before = (self.limit, self.curtailed_w > 0)
        self.price = price
        self.limit = export_limit(
            enabled=self.enabled,
            price=price,
            threshold=self.threshold,
            cost=self.cost,
            fixed_w=self.fixed_w,
            connection=self.connection,
            never=self.never,
        )
        self.export_w = None if grid_w is None else max(-grid_w, 0.0)
        over = (self.export_w or 0.0) - self.limit.limit_w
        self.curtailed_w = over if self.limit.limited and over >= MIN_CURTAIL_W else 0.0
        if self._event is not None and hours:
            # The energy over the time since the previous measurement.
            kwh = self._event["w"] * hours / 1000
            self._event["kwh"] += kwh
            self._event["value"] += kwh * -(self._event["price"] or 0.0)
            self.today_kwh += kwh
        self._explain(when)
        changed = (self.limit, self.curtailed_w > 0) != before
        if changed or self._notified is None or when - self._notified >= NOTIFY_EVERY:
            self._notified = when
            for listener in list(self._listeners):
                listener()

    def _explain(self, when: datetime) -> None:
        if self.curtailed_w > 0:
            if self._event is None:
                self._event = {
                    "start": when,
                    "kwh": 0.0,
                    "value": 0.0,
                    "price": self.price,
                }
                self._decisions.async_log(
                    "forecast",
                    "export_limit_started",
                    limit=f"{self.limit.limit_w:.0f} W",
                    reason=self._reason(),
                    power=f"{self.curtailed_w:.0f} W",
                    inverters=", ".join(n for n, _d, _a in self.inverters) or "-",
                )
            self._event["seen"] = when
            self._event["w"] = self.curtailed_w
            return
        if self._event is None:
            return
        self._event["w"] = 0.0
        if when - self._event["seen"] < END_AFTER and self.limit.limited:
            return
        event, self._event = self._event, None
        self._decisions.async_log(
            "forecast",
            "export_limit_ended",
            minutes=max(
                round((event["seen"] - event["start"]).total_seconds() / 60), 1
            ),
            energy=self._num(event["kwh"], 2),
            value=self._num(event["value"], 2),
        )

    def _reason(self) -> str:
        dutch = self._comma
        if self.limit.reason == REASON_NEVER:
            return "nooit terugleveren (ingesteld)" if dutch else "never export (set)"
        if self.limit.reason == REASON_PRICE:
            price = self._num((self.price or 0.0) - self.cost, 3)
            threshold = self._num(self.threshold, 3)
            return (
                f"netto terugleverprijs {price} onder {threshold}"
                if dutch
                else f"net export price {price} below {threshold}"
            )
        return "vaste grens" if dutch else "fixed limit"

    def plan_updated(
        self, slots: list[Any], now: datetime, export_factor: float = 1.0
    ) -> None:
        """A new plan: the coming periods in which export would be limited;
        a new clear one is told once in *Why* (before it starts)."""
        self.expected = expected_limits(
            slots,
            now,
            enabled=self.enabled,
            threshold=self.threshold,
            cost=self.cost,
            export_factor=export_factor,
            never=self.never,
        )
        for period in self.expected:
            if period.start in self._told or period.start <= now:
                continue
            self._told.add(period.start)
            local = dt_util.as_local
            same_day = local(period.start).date() == local(now).date()
            day = "" if same_day else f"{local(period.start):%d-%m} "
            self._decisions.async_log(
                "forecast",
                "export_limit_expected",
                start=f"{day}{local(period.start):%H:%M}",
                end=f"{local(period.end):%H:%M}",
                hours=self._num((period.end - period.start).total_seconds() / 3600, 1),
                energy=self._num(period.kwh, 1),
                why=self._why_expected(),
                price=(
                    "-"
                    if period.lowest_price is None
                    else self._num(period.lowest_price, 3)
                ),
            )
        # Forget periods long past.
        self._told = {t for t in self._told if t > now - timedelta(days=2)}

    def _why_expected(self) -> str:
        """Why export would be stopped: it costs money (limit price 0 or
        less), or it earns less than the limit price."""
        dutch = self._comma
        if self.never:
            return (
                "wordt nooit teruggeleverd (ingesteld)"
                if dutch
                else "export is switched off (set)"
            )
        if self.threshold <= 0:
            return "kost terugleveren geld" if dutch else "costs money"
        limit = self._num(self.threshold, 3)
        return (
            f"levert terugleveren minder op dan {limit}"
            if dutch
            else f"earns less than {limit}"
        )

    def would_send(self) -> list[str]:
        """Per inverter: what its driver would send for the limit now."""
        return [
            driver.describe(address, self.limit.limit_w)
            if driver is not None
            else f"{name}: -"
            for name, driver, address in self.inverters
        ]
