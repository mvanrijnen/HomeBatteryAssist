"""Grid meters read directly, about once a second, read-only.

Next to grid sensors of other integrations, the grid power per phase can be
read straight from a meter that allows this without disturbing anyone:

- ``homewizard``: a HomeWizard P1 meter's local API v1 (``GET /api/v1/data``,
  a read-only endpoint any number of clients may poll); the address is taken
  from the HomeWizard integration's config entry;
- ``shelly``: a Shelly 3-phase energy meter's local HTTP API (Gen2+ Pro 3EM /
  3EM-63: ``GET /rpc/EM.GetStatus?id=0``; Gen1 3EM: ``GET /status``), also
  read-only; the address comes from the Shelly integration's config entry.
  Implemented from Shelly's API documentation, not yet verified on a device;
- ``speedwire``: the telegrams an SMA Home Manager 2.0 / Energy Meter
  multicasts on the network anyway (``speedwire.py``); only received, nothing
  is ever sent to the meter.

HomeBatteryAssist never changes a setting of these meters. The values feed
the measurements directly (they are not stored as entity states every
second, which would fill the recorder database).
"""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .speedwire import GROUP, PORT, decode

_LOGGER = logging.getLogger(__name__)

SOURCE_SENSORS = "sensors"
SOURCE_HOMEWIZARD = "homewizard"
SOURCE_SPEEDWIRE = "speedwire"
SOURCE_SHELLY = "shelly"
DIRECT_SOURCES = (SOURCE_HOMEWIZARD, SOURCE_SPEEDWIRE, SOURCE_SHELLY)

# Shelly models with a 3-phase energy meter: model id prefix -> generation
SHELLY_3EM_MODELS = {"SHEM-3": 1, "SPEM-003": 2, "S3EM-003": 3}

POLL_INTERVAL = timedelta(seconds=1)
STALE_AFTER = timedelta(seconds=10)  # no value this long: unknown

type PhaseListener = Callable[[datetime], None]


class DirectMeter:
    """Latest grid power per phase from a directly read meter."""

    label = "meter"

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Initialize."""
        self.hass = hass
        self.address = address
        self.phase_w: tuple[float, ...] | None = None
        self.updated: datetime | None = None
        self.count = 0  # values received since the start
        self._listeners: list[PhaseListener] = []

    @property
    def available(self) -> bool:
        """A recent value is known."""
        return (
            self.phase_w is not None
            and self.updated is not None
            and dt_util.utcnow() - self.updated < STALE_AFTER
        )

    @callback
    def async_add_listener(self, listener: PhaseListener) -> CALLBACK_TYPE:
        """Call ``listener(time)`` on every new value."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _set(self, phase_w: tuple[float, ...]) -> None:
        now = dt_util.utcnow()
        changed = phase_w != self.phase_w or not self.available
        self.phase_w, self.updated = phase_w, now
        self.count += 1
        if changed:
            for listener in list(self._listeners):
                listener(now)

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

    async def _async_poll(self, _now: datetime | None) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            phases = await self._async_read()
        except (TimeoutError, OSError, ValueError, KeyError, TypeError) as err:
            if not self._failed:
                _LOGGER.warning("Cannot read %s: %s", self.address, err)
            self._failed = True
            return
        finally:
            self._busy = False
        if self._failed:
            _LOGGER.info("Reading %s again", self.address)
        self._failed = False
        if phases:
            self._set(phases)

    async def _async_read(self) -> tuple[float, ...] | None:
        raise NotImplementedError


class HomeWizardP1(PollingMeter):
    """Polls a HomeWizard P1 meter's local API v1 every second."""

    label = SOURCE_HOMEWIZARD

    async def _async_read(self) -> tuple[float, ...] | None:
        return homewizard_phases(await read_homewizard(self.hass, self.address))


class ShellyMeter(PollingMeter):
    """Polls a Shelly 3-phase energy meter every second (Gen1 or Gen2+)."""

    label = SOURCE_SHELLY

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Initialize."""
        super().__init__(hass, address)
        self._gen1: bool | None = None  # found out on the first read

    async def _async_read(self) -> tuple[float, ...] | None:
        session = async_get_clientsession(self.hass)
        if self._gen1 is not True:
            async with asyncio.timeout(3):
                response = await session.get(
                    f"http://{self.address}/rpc/EM.GetStatus?id=0"
                )
            if response.status != 404:
                response.raise_for_status()
                self._gen1 = False
                return shelly_gen2_phases(await response.json(content_type=None))
            self._gen1 = True
        async with asyncio.timeout(3):
            response = await session.get(f"http://{self.address}/status")
            response.raise_for_status()
            return shelly_gen1_phases(await response.json(content_type=None))


async def read_homewizard(hass: HomeAssistant, address: str) -> dict[str, Any]:
    """The current measurement of a HomeWizard meter (API v1)."""
    session = async_get_clientsession(hass)
    async with asyncio.timeout(3):
        response = await session.get(f"http://{address}/api/v1/data")
        response.raise_for_status()
        return await response.json(content_type=None)


def homewizard_phases(data: dict[str, Any]) -> tuple[float, ...] | None:
    """Signed power per phase (+ import / - export) from API v1 data."""
    values = [data.get(f"active_power_l{n}_w") for n in (1, 2, 3)]
    if values[0] is None:
        return None
    if values[1] is None or values[2] is None:
        return (float(values[0]),)
    return tuple(float(v) for v in values)


def shelly_gen2_phases(data: dict[str, Any]) -> tuple[float, ...] | None:
    """Signed power per phase from ``EM.GetStatus`` (+ consumption / - return)."""
    values = [data.get(f"{p}_act_power") for p in "abc"]
    if any(v is None for v in values):
        return None
    return tuple(float(v) for v in values)


def shelly_gen1_phases(data: dict[str, Any]) -> tuple[float, ...] | None:
    """Signed power per phase from a Gen1 3EM ``/status`` (``emeters``)."""
    meters = data.get("emeters") or []
    if len(meters) < 3 or not all(m.get("is_valid", True) for m in meters[:3]):
        return None
    return tuple(float(m["power"]) for m in meters[:3])


def shelly_3em_hosts(hass: HomeAssistant) -> dict[str, str]:
    """Hosts of Shelly 3-phase energy meters: host -> model (from config entries)."""
    return {
        entry.data["host"]: entry.data.get("model", "")
        for entry in hass.config_entries.async_entries("shelly")
        if entry.data.get("host")
        and any(
            str(entry.data.get("model", "")).startswith(prefix)
            for prefix in SHELLY_3EM_MODELS
        )
    }


class _SpeedwireProtocol(asyncio.DatagramProtocol):
    def __init__(self, handler: Callable[[bytes, str], None]) -> None:
        self._handler = handler

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        self._handler(data, addr[0])


def _multicast_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind(("", PORT))
    membership = struct.pack(
        "4s4s", socket.inet_aton(GROUP), socket.inet_aton("0.0.0.0")
    )
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    sock.setblocking(False)
    return sock


class SpeedwireMeter(DirectMeter):
    """Receives the multicast telegrams of one SMA Home Manager / Energy Meter."""

    label = SOURCE_SPEEDWIRE

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Initialize; ``address`` is the meter's IP address."""
        super().__init__(hass, address)
        self._transport: asyncio.DatagramTransport | None = None

    async def async_start(self) -> None:
        """Join the multicast group (receive only)."""
        try:
            self._transport, _ = await self.hass.loop.create_datagram_endpoint(
                lambda: _SpeedwireProtocol(self._received), sock=_multicast_socket()
            )
        except OSError as err:
            _LOGGER.warning("Cannot receive SMA Speedwire telegrams: %s", err)

    async def async_stop(self) -> None:
        """Leave the multicast group."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    @callback
    def _received(self, data: bytes, host: str) -> None:
        if host != self.address:
            return
        if (telegram := decode(data)) is not None:
            self._set(telegram.phase_w)


async def discover_speedwire(
    hass: HomeAssistant, seconds: float = 3.0
) -> dict[str, int]:
    """Listen briefly (receive only): IP address -> serial of energy meters."""
    found: dict[str, int] = {}

    def handler(data: bytes, host: str) -> None:
        if (telegram := decode(data)) is not None:
            found[host] = telegram.serial

    try:
        transport, _ = await hass.loop.create_datagram_endpoint(
            lambda: _SpeedwireProtocol(handler), sock=_multicast_socket()
        )
    except Exception as err:
        _LOGGER.debug("Speedwire not available: %s", err)
        return found
    try:
        await asyncio.sleep(seconds)
    finally:
        transport.close()
    return found


def create_meter(hass: HomeAssistant, source: str, address: str) -> DirectMeter:
    """The direct meter for a configured source."""
    if source == SOURCE_HOMEWIZARD:
        return HomeWizardP1(hass, address)
    if source == SOURCE_SHELLY:
        return ShellyMeter(hass, address)
    return SpeedwireMeter(hass, address)
