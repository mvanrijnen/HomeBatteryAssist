"""Meter drivers for the grid connection and PV sources (see ``base.py``).

``template.py`` is an example only and not listed.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .base import MeterDriver
from .discovery import (
    SOURCE_HOMEWIZARD,
    SOURCE_IAMMETER,
    SOURCE_NAMES,
    SOURCE_SHELLY,
    SOURCE_SHELLY_EM,
    SOURCE_SPEEDWIRE,
    DirectCandidate,
    DirectMeter,
    create_meter,
    find_direct_meters,
)


class _Driver(MeterDriver):
    """A driver for one of the built-in direct meters."""

    def __init__(self, key: str, verified: bool) -> None:
        self.key = key
        self.name = SOURCE_NAMES[key]
        self.verified = verified

    def find(self, hass: HomeAssistant) -> list[DirectCandidate]:
        return [c for c in find_direct_meters(hass) if c.source == self.key]

    def create(self, hass: HomeAssistant, address: str) -> DirectMeter:
        return create_meter(hass, self.key, address)


DRIVERS: tuple[MeterDriver, ...] = (
    _Driver(SOURCE_HOMEWIZARD, verified=True),
    _Driver(SOURCE_SPEEDWIRE, verified=True),
    _Driver(SOURCE_SHELLY, verified=False),
    _Driver(SOURCE_SHELLY_EM, verified=False),
    _Driver(SOURCE_IAMMETER, verified=False),
)

__all__ = ["DRIVERS", "MeterDriver", "get_driver"]


def get_driver(key: str) -> MeterDriver | None:
    """The meter driver with this key."""
    return next((d for d in DRIVERS if d.key == key), None)
