"""Tibber (core integration) — IN DEVELOPMENT, not offered in the settings.

Open point: a Tibber price source is one Tibber account (config entry), while
``tibber.get_prices`` returns the prices per *home* by name. With several homes
it is not known yet which home belongs to the chosen source; this driver takes
the first one. Not tested on a real installation.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from ..actions import ActionDriver, _days, points_from
from ..base import PriceData


class TibberDriver(ActionDriver):
    """Tibber (core): ``tibber.get_prices``, per kWh incl. taxes."""

    key = "tibber"
    name = "Tibber"
    domain = "tibber"

    async def _async_fetch(
        self, hass: HomeAssistant, source: str, role: str
    ) -> PriceData:
        start, end = _days()
        response = await self._call(
            hass,
            "tibber",
            "get_prices",
            {"start": start.isoformat(), "end": end.isoformat()},
        )
        homes = response.get("prices", {})
        first = next(iter(homes.values()), [])
        return PriceData(
            points_from((p.get("start_time"), None, p.get("price")) for p in first)
        )
