"""Price drivers: every price source read the same way (see ``base.py``).

``DRIVERS`` lists the drivers offered in the settings. ``template.py`` is only
a code example for new drivers and is deliberately not listed.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .actions import ACTION_DRIVERS
from .base import (
    ROLE_EXPORT,
    ROLE_IMPORT,
    ROLE_MARKET,
    PriceData,
    PriceDriver,
    PriceSource,
)
from .dyntarnl import DynTarNLDriver
from .sensors import SENSOR_DRIVERS

DRIVERS: tuple[PriceDriver, ...] = (
    DynTarNLDriver(),
    *ACTION_DRIVERS,
    *SENSOR_DRIVERS,
)

__all__ = [
    "DRIVERS",
    "ROLE_EXPORT",
    "ROLE_IMPORT",
    "ROLE_MARKET",
    "PriceData",
    "PriceDriver",
    "PriceSource",
    "find_sources",
    "get_driver",
    "split_key",
]


def get_driver(key: str) -> PriceDriver | None:
    """The driver with this key."""
    return next((d for d in DRIVERS if d.key == key), None)


def find_sources(hass: HomeAssistant) -> list[PriceSource]:
    """All price sources available in Home Assistant, over all drivers."""
    sources: list[PriceSource] = []
    for driver in DRIVERS:
        try:
            sources += driver.find(hass)
        except Exception:
            continue
    return sources


def split_key(key: str) -> tuple[PriceDriver | None, str]:
    """``<driver>:<source id>`` -> (driver, source id)."""
    driver, _, source = key.partition(":")
    return get_driver(driver), source
