"""Shelly energy meters: 3-phase (Gen2+ Pro 3EM / 3EM-63
``GET /rpc/EM.GetStatus?id=0``; Gen1 3EM ``GET /status``) and 1-phase EM
(Gen1 ``/status``, Gen2+ Pro EM ``/rpc/EM1.GetStatus?id=0``), read-only. The
address comes from the Shelly integration's config entry. From Shelly's API
documentation, not yet verified on a device."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .direct_reading import (
    SOURCE_SHELLY,
    SOURCE_SHELLY_EM,
    DirectCandidate,
    PollingMeter,
)

# Shelly 1-phase energy meters: model id prefix
SHELLY_EM_MODELS = ("SHEM", "SPEM-002", "S3EM-002")

# Shelly models with a 3-phase energy meter: model id prefix -> generation
SHELLY_3EM_MODELS = {"SHEM-3": 1, "SPEM-003": 2, "S3EM-003": 3}


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


def find_shelly(hass: HomeAssistant) -> list[DirectCandidate]:
    """Shelly energy meters known to Home Assistant (config entries)."""
    found = [
        DirectCandidate(SOURCE_SHELLY, host, f"Shelly 3EM ({model})", 3)
        for host, model in shelly_3em_hosts(hass).items()
    ]
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
    return found
