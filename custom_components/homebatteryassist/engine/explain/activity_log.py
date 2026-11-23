"""The activity log: what each real battery did, as periods, for 30 days.

Every minute each real battery is looked at and the minute is added to its
current period, or starts a new one when something changed:

- ``kind``: ``charge_pv`` (charging, at least half of it from a solar
  surplus), ``charge_grid``, ``discharge`` or ``idle`` (below ``IDLE_W``);
- ``source``: who decided — ``hba_nom`` / ``hba_plan`` (HomeBatteryAssist's
  control, zero on the meter / the plan), ``test`` (a test by hand),
  ``own`` (the battery's own control or its integration), ``incident`` (the
  battery does not follow its command, its connection or the grid
  measurement is gone);
- ``plan``: what the selected plan said for that moment (``charge``,
  ``discharge``, ``idle``; None without a plan), and ``follows`` whether the
  battery did that.

Per period: start, end, energy (kWh), highest power, and the average price
of that energy. Shown in the dashboard tab *Log* (websocket
``homebatteryassist/activity``), exportable as CSV there.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

STORAGE_VERSION = 1
SAMPLE = timedelta(minutes=1)
KEEP = timedelta(days=30)
IDLE_W = 50.0  # below this a battery counts as idle
SAVE_DELAY = 300  # s

KINDS = ("charge_pv", "charge_grid", "discharge", "idle")
SOURCES = ("hba_nom", "hba_plan", "test", "own", "incident")


def direction(kind: str) -> str:
    """charge / discharge / idle of a kind."""
    return "charge" if kind.startswith("charge") else kind


class ActivityLog:
    """Periods of what every real battery did, and who decided it."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        look: Callable[[], list[dict[str, Any]]],
    ) -> None:
        """``look``: per real battery now ``{"id", "name", "power_w",
        "pv_surplus_w", "source", "plan", "price"}``."""
        self.hass = hass
        self._look = look
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"homebatteryassist.{entry_id}.activity"
        )
        self.periods: list[dict[str, Any]] = []
        self._open: dict[str, dict[str, Any]] = {}  # battery id -> its period
        self._unsub: CALLBACK_TYPE | None = None

    async def async_start(self) -> None:
        """Load the log and start looking every minute."""
        data = await self._store.async_load() or {}
        self.periods = list(data.get("periods", []))
        self._unsub = async_track_time_interval(self.hass, self._sample, SAMPLE)

    async def async_stop(self) -> None:
        """Stop and save."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        await self._store.async_save(self._data())

    def _data(self) -> dict[str, Any]:
        return {"periods": self.periods}

    @callback
    def _sample(self, now: datetime) -> None:
        try:
            looks = self._look()
        except Exception:
            return
        for look in looks:
            self.add(now, look, SAMPLE)
        cutoff = (now - KEEP).isoformat()
        self.periods = [p for p in self.periods if p["end"] >= cutoff]
        self._store.async_delay_save(self._data, SAVE_DELAY)

    def add(self, now: datetime, look: dict[str, Any], span: timedelta) -> None:
        """One look at one battery, standing for ``span`` up to ``now``."""
        power = look.get("power_w")
        if power is None:
            return
        if abs(power) < IDLE_W:
            kind = "idle"
        elif power < 0:
            kind = "discharge"
        else:
            surplus = max(look.get("pv_surplus_w") or 0.0, 0.0)
            kind = "charge_pv" if surplus >= power / 2 else "charge_grid"
        plan = look.get("plan")
        follows = None if plan is None else direction(kind) == plan
        source = look.get("source") or "own"
        wh = abs(power) * span.total_seconds() / 3600
        price = look.get("price")
        period = self._open.get(look["id"])
        if (
            period is not None
            and period["kind"] == kind
            and period["source"] == source
            and period["plan"] == plan
            and period["end"] >= (now - span * 2).isoformat()
        ):
            period["end"] = now.isoformat()
        else:
            period = {
                "battery": look["id"],
                "name": look.get("name", look["id"]),
                "start": (now - span).isoformat(),
                "end": now.isoformat(),
                "kind": kind,
                "source": source,
                "plan": plan,
                "follows": follows,
                "kwh": 0.0,
                "max_w": 0.0,
                "cost": 0.0,
                "priced_kwh": 0.0,
            }
            self.periods.append(period)
            self._open[look["id"]] = period
        period["kwh"] = round(period["kwh"] + wh / 1000, 4)
        period["max_w"] = round(max(period["max_w"], abs(power)), 1)
        if price is not None and kind != "idle":
            period["cost"] = round(period["cost"] + wh / 1000 * price, 5)
            period["priced_kwh"] = round(period["priced_kwh"] + wh / 1000, 4)

    def recent(self, days: int, now: datetime | None = None) -> list[dict[str, Any]]:
        """The periods of the last ``days``, newest first, with the average
        price per period."""
        now = now or dt_util.utcnow()
        since = (now - timedelta(days=days)).isoformat()
        result = []
        for period in reversed(self.periods):
            if period["end"] < since:
                break
            priced = period.get("priced_kwh") or 0.0
            result.append(
                {
                    **{
                        k: v
                        for k, v in period.items()
                        if k not in ("cost", "priced_kwh")
                    },
                    "price": round(period["cost"] / priced, 4) if priced else None,
                }
            )
        return result
