"""Iammeter WEM3080 (1 phase) and WEM3080T (3 phases): local API
(``GET /monitorjson``). From the API documentation, not yet verified on a device."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .direct_reading import (
    SOURCE_IAMMETER,
    DirectCandidate,
    PhaseReading,
    PollingMeter,
    per_phase,
)


class IammeterMeter(PollingMeter):
    """Polls an Iammeter WEM3080 / WEM3080T every second."""

    label = SOURCE_IAMMETER

    async def _async_read(self) -> PhaseReading | None:
        session = async_get_clientsession(self.hass)
        async with asyncio.timeout(3):
            response = await session.get(f"http://{self.address}/monitorjson")
            response.raise_for_status()
            return iammeter_reading(await response.json(content_type=None))


def iammeter_phases(data: dict[str, Any]) -> tuple[float, ...] | None:
    """Signed power per phase: WEM3080T ``Datas`` (per phase [V, A, W, ...]),
    WEM3080 ``Data`` ([V, A, W, ...])."""
    if isinstance(rows := data.get("Datas"), list) and len(rows) >= 3:
        return tuple(float(row[2]) for row in rows[:3])
    if isinstance(row := data.get("Data"), list) and len(row) >= 3:
        return (float(row[2]),)
    return None


def iammeter_reading(data: dict[str, Any]) -> PhaseReading | None:
    """Power, and voltage and current per phase ([V, A, W, ...] per row)."""
    power = iammeter_phases(data)
    if power is None:
        return None
    rows = data.get("Datas") if len(power) == 3 else [data.get("Data")]
    rows = [r for r in rows or [] if isinstance(r, list) and len(r) >= 3]
    count = len(power)
    return PhaseReading(
        power,
        per_phase([r[1] for r in rows], count),
        per_phase([r[0] for r in rows], count),
    )


def find_iammeter(hass: HomeAssistant) -> list[DirectCandidate]:
    """Iammeter meters known to Home Assistant (config entries)."""
    return [
        DirectCandidate(SOURCE_IAMMETER, host, "Iammeter", None)
        for entry in hass.config_entries.async_entries(SOURCE_IAMMETER)
        if (host := entry.data.get("host"))
    ]
