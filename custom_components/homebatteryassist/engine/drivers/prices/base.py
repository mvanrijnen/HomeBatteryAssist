"""The contract of a price driver: where prices come from, read the same way.

A price driver knows one kind of price source (an integration, a supplier, a
forecast model) and turns it into ``PricePoint``s: start, end, price per kWh and
whether the price is published or only estimated (forecast).

- ``find(hass)`` lists the sources of this kind that are available in Home
  Assistant (e.g. one per config entry or sensor). Only reads registries and
  states; never sends anything to a supplier or device.
- ``async_read(hass, source, role)`` returns the prices of one source for a
  role: ``import`` (what you pay), ``market`` (bare market price, e.g. EPEX) or
  ``export`` (what returning power earns). A driver only offers the roles it
  can deliver (``PriceSource.roles``).
- ``watch(hass, source)`` names entities whose updates mean new prices, so the
  forecasts are recalculated right away.

Add a driver: copy ``template.py``, fill it in, and add the class to
``DRIVERS`` in ``__init__.py``. Mark it ``verified`` only after testing it on a
real installation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant

from ...inputs.prices import PricePoint

ROLE_IMPORT = "import"
ROLE_MARKET = "market"
ROLE_EXPORT = "export"


@dataclass(frozen=True, slots=True)
class PriceSource:
    """One available source of a driver, as offered in the settings."""

    driver: str  # PriceDriver.key
    id: str  # e.g. a config entry id or entity id, unique within the driver
    title: str  # shown to the user
    roles: frozenset[str] = field(default_factory=lambda: frozenset({ROLE_IMPORT}))
    days_ahead: float | None = None  # how far it typically reaches
    # Only a prediction, not the valid tariffs: usable as extra forecast next
    # to a real price source, never as the price source itself.
    forecast_only: bool = False

    @property
    def key(self) -> str:
        """Stored in the options: ``<driver>:<id>``."""
        return f"{self.driver}:{self.id}"


@dataclass(frozen=True, slots=True)
class PriceData:
    """Prices of one source for one role."""

    points: list[PricePoint]
    unit: str | None = None  # e.g. "EUR/kWh"


class PriceDriver(ABC):
    """A kind of price source."""

    key: str = ""  # stable id, stored in the options
    name: str = ""  # shown to the user
    verified: bool = False  # tested on a real installation
    forecast_only: bool = False  # only predictions (see PriceSource)

    @abstractmethod
    def find(self, hass: HomeAssistant) -> list[PriceSource]:
        """The sources of this kind available in Home Assistant."""

    @abstractmethod
    async def async_read(
        self, hass: HomeAssistant, source: str, role: str
    ) -> PriceData:
        """Prices of ``source`` for ``role`` (import / market / export)."""

    def watch(self, hass: HomeAssistant, source: str) -> list[str]:
        """Entities whose updates mean new prices (default: none)."""
        return []
