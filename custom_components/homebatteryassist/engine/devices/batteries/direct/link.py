"""A battery's direct connection: one driver, one connection, read and write.

A battery whose subentry chooses a direct driver (``direct_driver``,
``direct_address``, ``direct_port``, ``direct_unit``) gets a ``DirectLink``
while HomeBatteryAssist runs. Choosing the driver there is the deliberate
switch: only then is the driver ``enabled`` and does it connect. Many
batteries allow ONE client (e.g. a Marstek Venus v3): the integration that
used to read it (e.g. Omnibattery) must be switched off first.

The link:

- reads the battery every ``POLL`` (``async_read``) and keeps the last
  reading; ``available`` while a reading is younger than ``STALE``;
- backs off after a failure (``BACKOFF``: 5 s, 15 s, 30 s, 60 s) instead of
  reconnecting at once (a reconnect storm can hang a single-client battery);
- is the only way to write: ``async_set_power`` / ``async_release`` go
  through the same driver (and so the same connection), used by the control
  test (``engine/control``) and, once active, the control loop;
- releases the battery when it stops while it was being controlled;
- tells its listeners after every reading or failure.

The live readings are registered in ``hass.data[LINKS_KEY]`` by battery id;
``BatteryInput`` takes the state of charge and power from there (before the
battery's sensors), ``command()`` / ``telemetry()`` the rest.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util import dt as dt_util

from .....const import DIRECT_LINKS_KEY
from .base import DirectBatteryDriver, DirectReading

_LOGGER = logging.getLogger(__name__)

LINKS_KEY = DIRECT_LINKS_KEY  # hass.data: battery id -> link
POLL = timedelta(seconds=5)
STALE = timedelta(seconds=30)
BACKOFF = (5.0, 15.0, 30.0, 60.0)  # s after 1, 2, 3, 4+ failures in a row

STATE_CONNECTING = "connecting"
STATE_CONNECTED = "connected"
STATE_ERROR = "error"
STATE_STOPPED = "stopped"
STATES = (STATE_CONNECTING, STATE_CONNECTED, STATE_ERROR, STATE_STOPPED)


class DirectLink:
    """The direct connection of one battery."""

    def __init__(
        self,
        hass: HomeAssistant,
        battery_id: str,
        name: str,
        driver: DirectBatteryDriver,
    ) -> None:
        """Initialize; ``driver`` is enabled here (the user chose it)."""
        self.hass = hass
        self.battery_id = battery_id
        self.name = name
        self.driver = driver
        driver.enabled = True  # chosen per battery: the deliberate switch
        self.reading: DirectReading | None = None
        self.read_at: datetime | None = None
        self.error: str | None = None
        self.failures = 0
        self.state = STATE_STOPPED
        self.controlled = False  # a command was sent and not yet released
        self.commanded_w: float | None = None
        self._open = False
        self._busy = False
        self._unsub_poll: CALLBACK_TYPE | None = None
        self._unsub_retry: CALLBACK_TYPE | None = None
        self._retry_at: datetime | None = None
        self._listeners: list[Callable[[datetime], None]] = []

    # -- life cycle -------------------------------------------------------
    async def async_start(self) -> None:
        """Start reading (the first read now, then every ``POLL``)."""
        self.hass.data.setdefault(LINKS_KEY, {})[self.battery_id] = self
        self.state = STATE_CONNECTING
        self._unsub_poll = async_track_time_interval(self.hass, self._async_poll, POLL)
        await self._async_poll(dt_util.utcnow())

    async def async_stop(self) -> None:
        """Stop: release the battery if it was controlled, then disconnect."""
        if self._unsub_poll is not None:
            self._unsub_poll()
            self._unsub_poll = None
        if self._unsub_retry is not None:
            self._unsub_retry()
            self._unsub_retry = None
        if self.controlled:
            try:
                await self.async_release()
            except Exception:
                _LOGGER.exception("%s: release on stop failed", self.name)
        await self._async_close()
        self.state = STATE_STOPPED
        links = self.hass.data.get(LINKS_KEY, {})
        if links.get(self.battery_id) is self:
            del links[self.battery_id]

    @callback
    def async_add_listener(self, listener: Callable[[datetime], None]) -> CALLBACK_TYPE:
        """Call ``listener(when)`` after every reading or failure."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    # -- reading ----------------------------------------------------------
    @property
    def available(self) -> bool:
        """Whether the last reading is recent enough to use."""
        return (
            self.reading is not None
            and self.read_at is not None
            and dt_util.utcnow() - self.read_at <= STALE
        )

    @property
    def soc(self) -> float | None:
        """State of charge (%) when available."""
        if not self.available or self.reading is None:
            return None
        soc = self.reading.soc
        return soc if soc is not None and 0 <= soc <= 100 else None

    @property
    def power_w(self) -> float | None:
        """Power (W, + charging / - discharging) when available."""
        if not self.available or self.reading is None:
            return None
        return self.reading.power_w

    async def _async_poll(self, now: datetime) -> None:
        if self._busy or (self._retry_at is not None and now < self._retry_at):
            return
        self._busy = True
        try:
            if not self._open:
                await self.driver.async_open()
                self._open = True
            reading = await self.driver.async_read()
        except Exception as err:
            await self._failed(now, err)
        else:
            self.reading = reading
            self.read_at = dt_util.utcnow()
            self.error = None
            self.failures = 0
            self._retry_at = None
            self.state = STATE_CONNECTED
        finally:
            self._busy = False
        self._tell(now)

    async def _failed(self, now: datetime, err: Exception) -> None:
        self.failures += 1
        self.error = str(err) or type(err).__name__
        self.state = STATE_ERROR
        delay = BACKOFF[min(self.failures, len(BACKOFF)) - 1]
        self._retry_at = now + timedelta(seconds=delay)
        if self.failures in (1, len(BACKOFF)):
            _LOGGER.warning(
                "%s: direct connection failed (%s); retrying in %.0f s",
                self.name,
                self.error,
                delay,
            )
        await self._async_close()
        # Poll again right when the back-off ends (not up to POLL later).
        if self._unsub_retry is not None:
            self._unsub_retry()
        self._unsub_retry = async_call_later(self.hass, delay, self._async_retry)

    async def _async_retry(self, now: datetime) -> None:
        self._unsub_retry = None
        await self._async_poll(now)

    async def _async_close(self) -> None:
        if self._open:
            try:
                await self.driver.async_close()
            except Exception:
                _LOGGER.debug("%s: close failed", self.name, exc_info=True)
        self._open = False

    def _tell(self, when: datetime) -> None:
        for listener in list(self._listeners):
            listener(when)

    # -- writing ----------------------------------------------------------
    @property
    def can_write(self) -> bool:
        """Whether the driver can control the battery."""
        return bool(self.driver.can_write)

    async def async_set_power(self, power_w: float) -> None:
        """Charge (+) / discharge (-) at ``power_w`` through the driver."""
        if not self._open:
            await self.driver.async_open()
            self._open = True
        self.controlled = True
        self.commanded_w = power_w
        await self.driver.async_set_power(power_w)

    async def async_release(self) -> None:
        """Hand the battery back to its own control (the driver may close the
        connection; the next poll opens it again)."""
        if not self._open:
            await self.driver.async_open()
            self._open = True
        await self.driver.async_release()
        self.controlled = False
        self.commanded_w = None
        # A driver that closes on release (single client slot freed):
        # reopen on the next poll.
        client = getattr(self.driver, "client", None)
        if client is not None and not getattr(client, "connected", True):
            self._open = False

    # -- for the status sensor --------------------------------------------
    def as_dict(self) -> dict[str, Any]:
        """The connection and the last reading."""
        reading = self.reading
        return {
            "driver": self.driver.name,
            "address": self.driver.address,
            "state": self.state,
            "error": self.error,
            "last_read": self.read_at.isoformat() if self.read_at else None,
            "soc": reading.soc if reading else None,
            "power": reading.power_w if reading else None,
            "controlled": self.controlled,
            "commanded_power": self.commanded_w,
            **(reading.telemetry.as_dict() if reading else {}),
            **({k: v for k, v in reading.extra.items()} if reading else {}),
        }


def link_for(hass: HomeAssistant, battery_id: str) -> DirectLink | None:
    """The running direct link of a battery, if it has one."""
    return hass.data.get(LINKS_KEY, {}).get(battery_id)
