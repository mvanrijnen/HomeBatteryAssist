"""Template for a new price driver — a code example only.

This driver is never registered and never offered in the settings. Copy this
file, rename the class, fill in the three methods, and add the class to
``DRIVERS`` in ``__init__.py``. See ``base.py`` for the contract.

Rules every driver follows:

- Read only. Never change settings of another integration, a supplier account
  or a device. Use what Home Assistant already has (states, registries,
  read-only actions with a response) or a public read-only API.
- Return prices per kWh in the source's currency, with ``estimated=True`` for
  forecast prices, sorted by start. Leave out the past if that is easy; the
  caller drops it anyway.
- Never raise for a missing or broken source: return ``PriceData([])`` and log
  at debug level; the forecasts then report that prices are missing.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .base import ROLE_IMPORT, PriceData, PriceDriver, PriceSource
from .price_points import PricePoint

_LOGGER = logging.getLogger(__name__)


class TemplatePriceDriver(PriceDriver):
    """Example: prices of the integration ``my_prices`` (does not exist)."""

    key = "my_prices"  # stored in the options as "my_prices:<source id>"
    name = "My prices"  # shown in the settings
    verified = False  # set to True after testing on a real installation

    def find(self, hass: HomeAssistant) -> list[PriceSource]:
        """One source per config entry of the integration, for example."""
        return [
            PriceSource(
                driver=self.key,
                id=entry.entry_id,
                title=f"{self.name}: {entry.title}",
                roles=frozenset({ROLE_IMPORT}),  # the roles you can deliver
                days_ahead=2,  # today and tomorrow (after ~13:00)
            )
            for entry in hass.config_entries.async_entries("my_prices")
        ]

    async def async_read(
        self, hass: HomeAssistant, source: str, role: str
    ) -> PriceData:
        """Read the prices; e.g. from a sensor attribute or a service response.

        Example with a read-only action that returns a response:

            response = await hass.services.async_call(
                "my_prices", "get_prices", {"config_entry": source},
                blocking=True, return_response=True,
            )
            points = [
                PricePoint(start, end, price_per_kwh, estimated=False)
                for ... in response["prices"]
            ]
        """
        points: list[PricePoint] = []
        return PriceData(points, "EUR/kWh")

    def watch(self, hass: HomeAssistant, source: str) -> list[str]:
        """Entities that change when new prices arrive (optional)."""
        return []
