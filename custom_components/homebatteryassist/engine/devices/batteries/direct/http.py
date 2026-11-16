"""Generic local-HTTP battery driver (JSON API) over Home Assistant's shared
session. A brand subclass sets the endpoint and maps the JSON onto a reading;
control payloads go in ``async_set_power`` / ``async_release`` (never called
while HomeBatteryAssist is read-only)."""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .base import DirectBatteryDriver, DirectReading


class HttpBatteryDriver(DirectBatteryDriver):
    """A battery with a local JSON API."""

    transport = "http"
    status_path: ClassVar[str] = "/"
    timeout: ClassVar[float] = 5.0

    def url(self, path: str) -> str:
        """Full URL of ``path`` on the battery."""
        return f"http://{self.address}{path}"

    def auth(self) -> Any:
        """aiohttp auth for the request (default: none)."""
        return None

    async def async_get(self, path: str) -> Any:
        """GET ``path`` as JSON."""
        session = async_get_clientsession(self.hass)
        async with asyncio.timeout(self.timeout):
            response = await session.get(self.url(path), auth=self.auth())
            response.raise_for_status()
            return await response.json(content_type=None)

    async def async_read(self) -> DirectReading:
        """Read the status endpoint and map it."""
        return self.reading(await self.async_get(self.status_path))

    def reading(self, data: Any) -> DirectReading:
        """Map the device's JSON onto a reading."""
        raise NotImplementedError
