"""Grid meters read directly, about once a second, read-only.

Next to grid sensors of other integrations, the grid power per phase can be
read straight from a meter that allows this without disturbing anyone:

- ``homewizard``: a HomeWizard P1 meter's or kWh meter's (1- or 3-phase)
  local API v1 (``GET /api/v1/data``, a read-only endpoint any number of
  clients may poll); the address is taken from the HomeWizard integration's
  config entry;
- ``shelly_em``: a Shelly EM (1 phase; Gen1 ``/status``, Gen2+ Pro EM
  ``/rpc/EM1.GetStatus?id=0``), channel 1;
- ``astrameter``: the status of an AstraMeter (``GET /api/status``, read-only)
  — the grid power per phase it hands to the Marstek batteries. Needs the
  add-on option ``dashboard_direct_access`` (best with
  ``dashboard_allow_write`` off); the add-on is found via the Supervisor;
- ``iammeter``: an Iammeter WEM3080 (1 phase) or WEM3080T (3 phases) local
  API (``GET /monitorjson``). Shelly EM and Iammeter follow their API
  documentation and are not yet verified on a device;
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
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .speedwire import GROUP, PORT, decode

_LOGGER = logging.getLogger(__name__)

SOURCE_SENSORS = "sensors"
SOURCE_HOMEWIZARD = "homewizard"
SOURCE_SPEEDWIRE = "speedwire"
SOURCE_SHELLY = "shelly"
SOURCE_SHELLY_EM = "shelly_em"
SOURCE_IAMMETER = "iammeter"
SOURCE_ASTRAMETER = "astrameter"
ASTRAMETER_ADDON = "b2500_meter"  # slug suffix of the AstraMeter add-on
ASTRAMETER_PORT = 52500
DIRECT_SOURCES = (
    SOURCE_HOMEWIZARD,
    SOURCE_SPEEDWIRE,
    SOURCE_SHELLY,
    SOURCE_SHELLY_EM,
    SOURCE_IAMMETER,
    SOURCE_ASTRAMETER,
)
SOURCE_NAMES = {
    SOURCE_HOMEWIZARD: "HomeWizard",
    SOURCE_SPEEDWIRE: "SMA Home Manager / Energy Meter",
    SOURCE_SHELLY: "Shelly 3EM",
    SOURCE_SHELLY_EM: "Shelly EM",
    SOURCE_IAMMETER: "Iammeter",
    SOURCE_ASTRAMETER: "AstraMeter",
}

# HomeWizard meters (product type = device model id) -> phases (None: depends
# on the smart meter). Energy sockets and water meters are no grid meters.
HOMEWIZARD_METERS: dict[str, int | None] = {
    "HWE-P1": None,
    "HWE-KWH1": 1,
    "SDM230-wifi": 1,
    "HWE-KWH3": 3,
    "SDM630-wifi": 3,
}
# Shelly 1-phase energy meters: model id prefix
SHELLY_EM_MODELS = ("SHEM", "SPEM-002", "S3EM-002")

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


class ShellyEmMeter(PollingMeter):
    """Polls a Shelly EM (1 phase, channel 1) every second (Gen1 or Gen2+)."""

    label = SOURCE_SHELLY_EM

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Initialize."""
        super().__init__(hass, address)
        self._gen1: bool | None = None

    async def _async_read(self) -> tuple[float, ...] | None:
        session = async_get_clientsession(self.hass)
        if self._gen1 is not True:
            async with asyncio.timeout(3):
                response = await session.get(
                    f"http://{self.address}/rpc/EM1.GetStatus?id=0"
                )
            if response.status != 404:
                response.raise_for_status()
                self._gen1 = False
                data = await response.json(content_type=None)
                power = data.get("act_power")
                return None if power is None else (float(power),)
            self._gen1 = True
        async with asyncio.timeout(3):
            response = await session.get(f"http://{self.address}/status")
            response.raise_for_status()
            phases = shelly_gen1_phases(await response.json(content_type=None), count=1)
        return phases


class IammeterMeter(PollingMeter):
    """Polls an Iammeter WEM3080 / WEM3080T every second."""

    label = SOURCE_IAMMETER

    async def _async_read(self) -> tuple[float, ...] | None:
        session = async_get_clientsession(self.hass)
        async with asyncio.timeout(3):
            response = await session.get(f"http://{self.address}/monitorjson")
            response.raise_for_status()
            return iammeter_phases(await response.json(content_type=None))


class AstraMeterMeter(PollingMeter):
    """Reads the grid power per phase from an AstraMeter's status."""

    label = SOURCE_ASTRAMETER

    async def _async_read(self) -> tuple[float, ...] | None:
        session = async_get_clientsession(self.hass)
        async with asyncio.timeout(3):
            response = await session.get(f"http://{self.address}/api/status")
            response.raise_for_status()
            return astrameter_phases(await response.json(content_type=None))


def astrameter_phases(data: dict[str, Any]) -> tuple[float, ...] | None:
    """Grid power per phase (+ import) from the AstraMeter status document.

    Every field there is optional: the grid of the first emulated device that
    reports one, else the first power meter's last values.
    """
    for device in data.get("devices") or []:
        grid = device.get("grid") or {}
        if grid.get("meter_failed"):
            continue
        values = [grid.get(f"l{n}_w") for n in (1, 2, 3)]
        if values[0] is not None:
            known = [float(v) for v in values if v is not None]
            return tuple(known)
    for meter in data.get("powermeters") or []:
        if meter.get("last_read_ok") is False:
            continue
        if values := meter.get("last_values_w"):
            return tuple(float(v) for v in values[:3])
    return None


def astrameter_addresses(hass: HomeAssistant) -> list[str]:
    """Address of the AstraMeter add-on on this host, if it is installed."""
    try:
        from homeassistant.components.hassio import get_addons_info
    except ImportError:
        return []
    try:
        addons = get_addons_info(hass) or {}
    except Exception:
        return []
    if any(slug.endswith(ASTRAMETER_ADDON) for slug in addons):
        # The add-on uses host networking, like Home Assistant itself.
        return [f"127.0.0.1:{ASTRAMETER_PORT}"]
    return []


def iammeter_phases(data: dict[str, Any]) -> tuple[float, ...] | None:
    """Signed power per phase: WEM3080T ``Datas`` (per phase [V, A, W, ...]),
    WEM3080 ``Data`` ([V, A, W, ...])."""
    if isinstance(rows := data.get("Datas"), list) and len(rows) >= 3:
        return tuple(float(row[2]) for row in rows[:3])
    if isinstance(row := data.get("Data"), list) and len(row) >= 3:
        return (float(row[2]),)
    return None


def shelly_gen2_phases(data: dict[str, Any]) -> tuple[float, ...] | None:
    """Signed power per phase from ``EM.GetStatus`` (+ consumption / - return)."""
    values = [data.get(f"{p}_act_power") for p in "abc"]
    if any(v is None for v in values):
        return None
    return tuple(float(v) for v in values)


def shelly_gen1_phases(
    data: dict[str, Any], count: int = 3
) -> tuple[float, ...] | None:
    """Signed power per phase from a Gen1 3EM / EM ``/status`` (``emeters``)."""
    meters = data.get("emeters") or []
    if len(meters) < count or not all(m.get("is_valid", True) for m in meters[:count]):
        return None
    return tuple(float(m["power"]) for m in meters[:count])


@dataclass(frozen=True, slots=True)
class DirectCandidate:
    """A meter that can be read directly, found in another integration."""

    source: str
    address: str
    name: str
    phases: int | None  # None: ask (or take it from the meter's sensors)


def find_direct_meters(hass: HomeAssistant) -> list[DirectCandidate]:
    """Meters of other integrations that can also be read directly.

    Only reads config entries and the device registry; nothing is sent.
    """
    devices = dr.async_get(hass)
    found: list[DirectCandidate] = []
    for entry in hass.config_entries.async_entries(SOURCE_HOMEWIZARD):
        address = entry.data.get("ip_address")
        for device in dr.async_entries_for_config_entry(devices, entry.entry_id):
            if (
                address
                and device.model_id in HOMEWIZARD_METERS
                and not device.via_device_id  # e.g. the gas meter of a P1
            ):
                found.append(
                    DirectCandidate(
                        SOURCE_HOMEWIZARD,
                        address,
                        f"HomeWizard {device.name_by_user or device.name or device.model}",
                        HOMEWIZARD_METERS[device.model_id],
                    )
                )
                break
    for host, model in shelly_3em_hosts(hass).items():
        found.append(DirectCandidate(SOURCE_SHELLY, host, f"Shelly 3EM ({model})", 3))
    for entry in hass.config_entries.async_entries("shelly"):
        model = str(entry.data.get("model", ""))
        if (
            entry.data.get("host")
            and any(
                model == prefix
                or model.startswith(f"{prefix}-")
                or model.startswith(prefix)
                for prefix in SHELLY_EM_MODELS
            )
            and not any(model.startswith(p) for p in SHELLY_3EM_MODELS)
        ):
            found.append(
                DirectCandidate(
                    SOURCE_SHELLY_EM, entry.data["host"], f"Shelly EM ({model})", 1
                )
            )
    for entry in hass.config_entries.async_entries(SOURCE_IAMMETER):
        if host := entry.data.get("host"):
            found.append(DirectCandidate(SOURCE_IAMMETER, host, "Iammeter", None))
    for address in astrameter_addresses(hass):
        found.append(
            DirectCandidate(SOURCE_ASTRAMETER, address, "AstraMeter (add-on)", None)
        )
    return found


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
    if source == SOURCE_SHELLY_EM:
        return ShellyEmMeter(hass, address)
    if source == SOURCE_ASTRAMETER:
        return AstraMeterMeter(hass, address)
    if source == SOURCE_IAMMETER:
        return IammeterMeter(hass, address)
    return SpeedwireMeter(hass, address)
