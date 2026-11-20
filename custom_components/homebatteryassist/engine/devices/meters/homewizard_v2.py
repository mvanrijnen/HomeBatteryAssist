"""HomeWizard meters through the local API v2: the meter pushes every new
measurement over a websocket (``wss://<address>/api/ws``), no polling.

API v2 needs a token. HomeBatteryAssist never creates one (that adds a user
on the meter): it uses the token Home Assistant's HomeWizard integration
already has in its config entry, when that integration talks API v2. The
subscription only reads measurements. Not tested on a device yet.

The meter's certificate is signed by HomeWizard's own CA for a name that is
not its address, so the local connection is made without checking it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .direct_reading import (
    SOURCE_HOMEWIZARD,
    SOURCE_HOMEWIZARD_V2,
    DirectMeter,
    PhaseReading,
    per_phase,
)

_LOGGER = logging.getLogger(__name__)

RETRY_S = 10  # wait before connecting again after a failure
HEARTBEAT_S = 30
TOKEN = "token"  # key of the token in the HomeWizard config entry


def homewizard_token(hass: HomeAssistant, address: str) -> str | None:
    """The API v2 token of the HomeWizard integration for this address."""
    for entry in hass.config_entries.async_entries(SOURCE_HOMEWIZARD):
        if entry.data.get("ip_address") == address and entry.data.get(TOKEN):
            return str(entry.data[TOKEN])
    return None


def homewizard_v2_reading(data: dict[str, Any]) -> PhaseReading | None:
    """Power, current and voltage per phase from an API v2 measurement
    (``power_l1_w``, ``current_l1_a``, ``voltage_l1_v``; current as size)."""
    values = [data.get(f"power_l{n}_w") for n in (1, 2, 3)]
    if values[0] is None:
        if data.get("power_w") is None:
            return None
        values = [data["power_w"], None, None]
    if (values[1] is None) != (values[2] is None):
        return None  # some phases missing: unknown, not a part counted as all
    count = 3 if values[1] is not None else 1
    power = per_phase(values, count)
    if power is None:
        return None
    numbers = range(1, count + 1)
    current = per_phase([data.get(f"current_l{n}_a") for n in numbers], count)
    return PhaseReading(
        power,
        tuple(abs(a) for a in current) if current else None,
        per_phase([data.get(f"voltage_l{n}_v") for n in numbers], count),
    )


class HomeWizardPush(DirectMeter):
    """A HomeWizard meter pushing its measurements (API v2 websocket)."""

    label = SOURCE_HOMEWIZARD_V2
    # Pushed per telegram: DSMR 5 every second, DSMR 4 every 10 s.
    stale_after = timedelta(seconds=25)

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Initialize."""
        super().__init__(hass, address)
        self._task: asyncio.Task | None = None
        self._failed = False

    async def async_start(self) -> None:
        """Connect in the background (and again after a failure)."""
        self._task = self.hass.async_create_background_task(
            self._run(), f"homebatteryassist homewizard v2 {self.address}"
        )

    async def async_stop(self) -> None:
        """Disconnect."""
        self.cancel_stale()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self._listen()
            except asyncio.CancelledError:
                raise
            except (
                TimeoutError,
                OSError,
                ValueError,
                KeyError,
                TypeError,
                aiohttp.ClientError,
            ) as err:
                if not self._failed:
                    _LOGGER.warning(
                        "HomeWizard API v2 at %s: %s (trying again)", self.address, err
                    )
                self._failed = True
            except Exception:  # anything unexpected: log it, keep reading
                _LOGGER.exception("HomeWizard API v2 at %s failed", self.address)
                self._failed = True
            await asyncio.sleep(RETRY_S)

    async def _listen(self) -> None:
        token = homewizard_token(self.hass, self.address)
        if token is None:
            raise ValueError("no API v2 token in the HomeWizard integration")
        session = async_get_clientsession(self.hass, verify_ssl=False)
        async with session.ws_connect(
            f"wss://{self.address}/api/ws", heartbeat=HEARTBEAT_S, ssl=False
        ) as ws:
            async for message in ws:
                if message.type != aiohttp.WSMsgType.TEXT:
                    if message.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
                    continue
                body = message.json()
                if not isinstance(body, dict):
                    continue
                kind = body.get("type")
                if kind == "authorization_requested":
                    await ws.send_json({"type": "authorization", "data": token})
                elif kind == "authorized":
                    await ws.send_json({"type": "subscribe", "data": "measurement"})
                    if self._failed:
                        _LOGGER.info("HomeWizard API v2 at %s again", self.address)
                    self._failed = False
                elif kind == "error":
                    raise ValueError(str(body.get("data")))
                elif kind == "measurement" and isinstance(body.get("data"), dict):
                    self.handle(body["data"])
        raise OSError("connection closed")

    def handle(self, data: dict[str, Any]) -> None:
        """Take one pushed measurement."""
        reading = homewizard_v2_reading(data)
        if reading is None:
            return
        self.phase_v, self.phase_pf = reading.phase_v, reading.phase_pf
        self._set(reading.phase_w, reading.phase_a)
