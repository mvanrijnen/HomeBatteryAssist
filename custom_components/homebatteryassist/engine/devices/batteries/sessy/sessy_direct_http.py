"""Direct driver: Sessy home battery over the dongle's local HTTP API —
PREPARED, NOT USED.

Every request uses HTTP Basic authentication with the user name and password
printed on the dongle (``username`` / ``password`` options). The embedded
server closes keep-alive sockets without warning, so each request asks for a
fresh connection (``Connection: close``), reads the whole body, and only one
request runs at a time. ``GET /api/v1/power/status`` answers on some
firmware without credentials, so ``GET /api/v1/power/active_strategy`` is the
credentials check.

On the wire ``sessy.power`` and the setpoint are + discharging; they are
turned into + charging here. The state of charge is a 0-1 fraction and the
pack voltage is in mV. Lifetime counters come from ``/api/v1/energy/status``
(Wh). No capacity, temperatures or alarms are available.

Control (never called while HomeBatteryAssist is read-only): ``POST
active_strategy`` ``{"strategy": "POWER_STRATEGY_API"}``, then ``POST
setpoint`` ``{"setpoint": S}`` with S in W, + discharging, clamped to
[-2200, +1700]. The original strategy is read once before the first write
and written back on release. Hazards: the sign is the opposite of ours; a
battery leaving standby can take about a minute to follow the first
setpoint (an idle 0 W then is not a failure); writing competes with another
integration or Sessy's own strategy that controls the battery.

Device facts: Omnibattery's Sessy driver (GPL-3.0) as reference for facts
only, not verified against Sessy's own documentation; own implementation.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
from typing import Any

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..base import BatteryTelemetry
from ..direct.base import DirectReading
from ..direct.http_driver import HttpBatteryDriver
from .sessy import Sessy

POWER_STATUS = "/api/v1/power/status"
ENERGY_STATUS = "/api/v1/energy/status"
STRATEGY = "/api/v1/power/active_strategy"
SETPOINT = "/api/v1/power/setpoint"
API_STRATEGY = "POWER_STRATEGY_API"
MAX_CHARGE_W = 2200  # setpoint -2200 on the wire
MAX_DISCHARGE_W = 1700  # setpoint +1700 on the wire
ATTEMPTS = 2
RETRY_DELAY = 0.05  # s


def number(value: Any) -> float | None:
    """A finite JSON number or numeric string; None otherwise."""
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def section(data: Any, key: str) -> dict[str, Any]:
    """``data[key]`` when it is an object, else empty."""
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, dict) else {}


class SessyHttpDriver(HttpBatteryDriver):
    """Sessy over the dongle's local HTTP API (address = host[:port];
    options ``username`` and ``password`` from the dongle)."""

    key = "sessy_http"
    name = "Sessy (HTTP)"
    models = (Sessy,)
    can_write = True  # described below; never called
    source = "Omnibattery drivers/sessy.py (facts only)"
    status_path = POWER_STATUS
    timeout = 10.0

    def __init__(self, hass: Any, address: str, **options: Any) -> None:
        """Initialize; one request at a time per battery."""
        super().__init__(hass, address, **options)
        self._lock = asyncio.Lock()
        self.original_strategy: str | None = None

    def headers(self) -> dict[str, str]:
        """Fresh connection, plus Basic auth with the dongle's credentials."""
        headers = {"Connection": "close"}
        if user := self.options.get("username"):
            token = f"{user}:{self.options.get('password', '')}".encode()
            headers["Authorization"] = "Basic " + base64.b64encode(token).decode()
        return headers

    async def _request(self, method: str, path: str, body: Any = None) -> Any:
        """One request on a fresh connection, body read in full; retried once
        after 50 ms (all writes set absolute values)."""
        self.require_enabled()
        session = async_get_clientsession(self.hass)
        async with self._lock:
            for attempt in range(ATTEMPTS):
                try:
                    async with (
                        asyncio.timeout(self.timeout),
                        session.request(
                            method,
                            self.url(path),
                            json=body,
                            headers=self.headers(),
                        ) as response,
                    ):
                        raw = await response.read()
                        response.raise_for_status()
                except (aiohttp.ClientConnectionError, OSError, TimeoutError):
                    if attempt == ATTEMPTS - 1:
                        raise
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                if not raw:
                    return None
                try:
                    return json.loads(raw)
                except ValueError:
                    return None  # some firmware acknowledges a POST in text
        return None

    async def async_get(self, path: str) -> Any:
        """GET ``path`` as JSON (fresh connection, Basic auth)."""
        return await self._request("GET", path)

    async def async_post(self, path: str, body: dict[str, Any]) -> Any:
        """POST ``body`` as JSON to ``path``."""
        return await self._request("POST", path, body)

    async def async_open(self) -> None:
        """Check the credentials on an endpoint that needs them (only when
        enabled)."""
        await super().async_open()
        await self.async_get(STRATEGY)

    async def async_read(self) -> DirectReading:
        """Power status, then the energy counters (one at a time)."""
        status = await self.async_get(POWER_STATUS)
        energy = await self.async_get(ENERGY_STATUS)
        return self.reading(status, energy)

    def reading(self, data: Any, energy: Any = None) -> DirectReading:
        """Map power status (and energy status) onto a reading (+ charging)."""
        sessy = section(data, "sessy")
        soc = number(sessy.get("state_of_charge"))
        power = number(sessy.get("power"))  # + discharging
        setpoint = number(sessy.get("power_setpoint"))  # + discharging
        voltage = number(sessy.get("pack_voltage"))  # mV
        phases = [
            number(section(data, f"renewable_energy_phase{n}").get("power"))
            for n in (1, 2, 3)
        ]
        known = [p for p in phases if p is not None]
        counters = section(energy, "sessy_energy")
        charged = number(counters.get("import_wh"))
        discharged = number(counters.get("export_wh"))
        totals = {
            "charged_total_kwh": None if charged is None else charged / 1000,
            "discharged_total_kwh": None if discharged is None else discharged / 1000,
        }
        return DirectReading(
            soc=None if soc is None else round(soc * 100, 1),
            power_w=None if power is None else -power,
            telemetry=BatteryTelemetry(
                voltage_v=None if voltage is None else voltage / 1000,
                extra={k: v for k, v in totals.items() if v is not None},
            ),
            extra={
                "setpoint_w": None if setpoint is None else -setpoint,  # + charge
                "pv_power_w": sum(known) if known else None,
                "max_charge_w": float(MAX_CHARGE_W),
                "max_discharge_w": float(MAX_DISCHARGE_W),
                "model": Sessy.type,
            },
        )

    @staticmethod
    def setpoint(power_w: float) -> int:
        """Our + charging W → Sessy's setpoint (+ discharging), clamped."""
        return max(-MAX_CHARGE_W, min(MAX_DISCHARGE_W, round(-power_w)))

    async def async_set_power(self, power_w: float) -> None:
        """Store the original strategy (first time), set
        ``POWER_STRATEGY_API``, then the setpoint. NEVER called while
        HomeBatteryAssist is read-only; hazards in the module docstring
        (opposite sign, start-up delay of about a minute)."""
        if self.original_strategy is None:
            current = await self.async_get(STRATEGY)
            strategy = current.get("strategy") if isinstance(current, dict) else None
            self.original_strategy = str(strategy) if strategy else API_STRATEGY
        await self.async_post(STRATEGY, {"strategy": API_STRATEGY})
        await self.async_post(SETPOINT, {"setpoint": self.setpoint(power_w)})

    async def async_release(self) -> None:
        """Setpoint 0, then the strategy that was active before the first
        write (if it was not the API strategy). NEVER called yet."""
        await self.async_post(SETPOINT, {"setpoint": 0})
        original, self.original_strategy = self.original_strategy, None
        if original and original != API_STRATEGY:
            await self.async_post(STRATEGY, {"strategy": original})
