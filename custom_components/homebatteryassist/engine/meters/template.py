"""Template for a new meter driver — a code example only.

Never registered and never offered. Copy this file, rename the classes, fill
in ``_async_read`` (and ``find`` if Home Assistant knows these meters), and
add the driver to ``DRIVERS`` in ``__init__.py``.

Rules: read only (a read-only local API or broadcast data), never change a
setting of the meter, never compete with its own integration. Return the
power per phase in W, + import (or + production for a PV meter), - export.
"""

from __future__ import annotations

import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .base import MeterDriver
from .direct import DirectCandidate, DirectMeter, PollingMeter


class TemplateMeter(PollingMeter):
    """Polls the example meter every second."""

    label = "my_meter"

    async def _async_read(self) -> tuple[float, ...] | None:
        """Read the power per phase, e.g. from a JSON API."""
        session = async_get_clientsession(self.hass)
        async with asyncio.timeout(3):
            response = await session.get(f"http://{self.address}/api/power")
            response.raise_for_status()
            data = await response.json(content_type=None)
        values = [data.get(f"power_l{n}") for n in (1, 2, 3)]
        return tuple(float(v) for v in values if v is not None) or None


class TemplateMeterDriver(MeterDriver):
    """Example: the meter ``my_meter`` (does not exist)."""

    key = "my_meter"
    name = "My meter"
    verified = False
    pv_capable = True

    def find(self, hass: HomeAssistant) -> list[DirectCandidate]:
        """E.g. one candidate per config entry of its integration."""
        return [
            DirectCandidate(self.key, entry.data["host"], self.name, None)
            for entry in hass.config_entries.async_entries("my_meter")
            if entry.data.get("host")
        ]

    def create(self, hass: HomeAssistant, address: str) -> DirectMeter:
        """A reader for one meter."""
        return TemplateMeter(hass, address)
