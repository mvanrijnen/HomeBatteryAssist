"""What every directly read meter shares: the latest power per phase,
listeners, polling a read-only HTTP API, and a value going stale.

HomeBatteryAssist never changes a setting of a meter; values feed the
measurements directly (not stored as entity states every second)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

SOURCE_SENSORS = "sensors"
SOURCE_HOMEWIZARD = "homewizard"
SOURCE_HOMEWIZARD_V2 = "homewizard_v2"  # API v2, pushed (websocket)
SOURCE_SPEEDWIRE = "speedwire"
SOURCE_SHELLY = "shelly"
SOURCE_SHELLY_EM = "shelly_em"
SOURCE_IAMMETER = "iammeter"
DIRECT_SOURCES = (
    SOURCE_HOMEWIZARD,
    SOURCE_HOMEWIZARD_V2,
    SOURCE_SPEEDWIRE,
    SOURCE_SHELLY,
    SOURCE_SHELLY_EM,
    SOURCE_IAMMETER,
)
SOURCE_NAMES = {
    SOURCE_HOMEWIZARD: "HomeWizard",
    SOURCE_HOMEWIZARD_V2: "HomeWizard (API v2, push)",
    SOURCE_SPEEDWIRE: "SMA Home Manager / Energy Meter",
    SOURCE_SHELLY: "Shelly 3EM",
    SOURCE_SHELLY_EM: "Shelly EM",
    SOURCE_IAMMETER: "Iammeter",
}

POLL_INTERVAL = timedelta(seconds=1)
STALE_AFTER = timedelta(seconds=10)  # no value this long: unknown

type PhaseListener = Callable[[datetime], None]


@dataclass(frozen=True, slots=True)
class DirectCandidate:
    """A meter that can be read directly, found in another integration."""

    source: str
    address: str
    name: str
    phases: int | None  # None: ask (or take it from the meter's sensors)


@dataclass(frozen=True, slots=True)
class PhaseReading:
    """One reading: power per phase (W, + import / - export) and, when the
    meter gives them, current (A), voltage (V) and power factor per phase."""

    phase_w: tuple[float, ...]
    phase_a: tuple[float, ...] | None = None
    phase_v: tuple[float, ...] | None = None
    phase_pf: tuple[float, ...] | None = None


def per_phase(values: list[Any], count: int) -> tuple[float, ...] | None:
    """``count`` numbers, or None when one is missing or not a number."""
    try:
        numbers = tuple(float(v) for v in values[:count])
    except (TypeError, ValueError):
        return None
    return numbers if len(numbers) == count else None


class DirectMeter:
    """Latest grid power per phase from a directly read meter."""

    label = "meter"
    # No value this long: unknown. A meter that pushes only on a new telegram
    # (DSMR 4: every 10 s) needs longer than one polled every second.
    stale_after = STALE_AFTER

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Initialize."""
        self.hass = hass
        self.address = address
        self.phase_w: tuple[float, ...] | None = None
        # Measured current (A), voltage (V) and power factor per phase, for
        # meters that send them (None: only power).
        self.phase_a: tuple[float, ...] | None = None
        self.phase_v: tuple[float, ...] | None = None
        self.phase_pf: tuple[float, ...] | None = None
        self.updated: datetime | None = None
        self.count = 0  # values received since the start
        self._listeners: list[PhaseListener] = []
        self._unsub_stale: CALLBACK_TYPE | None = None

    @property
    def available(self) -> bool:
        """A recent value is known."""
        return (
            self.phase_w is not None
            and self.updated is not None
            and dt_util.utcnow() - self.updated < self.stale_after
        )

    @callback
    def async_add_listener(self, listener: PhaseListener) -> CALLBACK_TYPE:
        """Call ``listener(time)`` on every new value."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _set(
        self, phase_w: tuple[float, ...], phase_a: tuple[float, ...] | None = None
    ) -> None:
        now = dt_util.utcnow()
        changed = phase_w != self.phase_w or not self.available
        self.phase_w, self.updated = phase_w, now
        self.phase_a = phase_a
        self.count += 1
        if changed:
            for listener in list(self._listeners):
                listener(now)
        # No value for STALE_AFTER: tell the listeners, so they see "unknown".
        self.cancel_stale()
        self._unsub_stale = async_call_later(
            self.hass, self.stale_after + timedelta(seconds=1), self._stale
        )

    @callback
    def _stale(self, now: datetime) -> None:
        self._unsub_stale = None
        if not self.available:
            for listener in list(self._listeners):
                listener(now)

    @callback
    def cancel_stale(self) -> None:
        """Stop watching for a missing value (when stopping)."""
        if self._unsub_stale is not None:
            self._unsub_stale()
            self._unsub_stale = None

    async def async_start(self) -> None:
        """Start reading."""

    async def async_stop(self) -> None:
        """Stop reading."""

    def diagnostics(self) -> dict[str, Any]:
        """State for the diagnostics download."""
        return {
            "type": self.label,
            "available": self.available,
            "phase_w": self.phase_w,
            "phase_a": self.phase_a,
            "phase_v": self.phase_v,
            "phase_pf": self.phase_pf,
            "updated": self.updated.isoformat() if self.updated else None,
            "values_received": self.count,
        }


class PollingMeter(DirectMeter):
    """Polls a meter's read-only HTTP API every second."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Initialize."""
        super().__init__(hass, address)
        self._unsub: CALLBACK_TYPE | None = None
        self._busy = False
        self._failed = False

    async def async_start(self) -> None:
        """Poll every ``POLL_INTERVAL``."""
        await self._async_poll(None)
        self._unsub = async_track_time_interval(
            self.hass, self._async_poll, POLL_INTERVAL
        )

    async def async_stop(self) -> None:
        """Stop polling."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        self.cancel_stale()

    async def _async_poll(self, _now: datetime | None) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            phases = await self._async_read()
        except Exception as err:
            # (TimeoutError, OSError, ClientError, or a reply in another
            # shape: AttributeError / IndexError in a parser.) Logged once.
            if not self._failed:
                _LOGGER.warning("Cannot read %s: %s", self.address, err)
            self._failed = True
            return
        finally:
            self._busy = False
        if self._failed:
            _LOGGER.info("Reading %s again", self.address)
        self._failed = False
        if isinstance(phases, PhaseReading):
            self.phase_v, self.phase_pf = phases.phase_v, phases.phase_pf
            if phases.phase_w:
                self._set(phases.phase_w, phases.phase_a)
        elif phases:
            self._set(phases)

    async def _async_read(self) -> tuple[float, ...] | PhaseReading | None:
        raise NotImplementedError
