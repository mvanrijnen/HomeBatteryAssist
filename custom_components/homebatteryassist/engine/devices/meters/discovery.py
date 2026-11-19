"""Directly read grid and PV meters: finding them and creating the reader.

One file per brand: ``homewizard.py``, ``sma.py`` (Speedwire), ``shelly.py``,
``iammeter.py``; what they share is in ``connection.py``.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .direct_reading import (
    DIRECT_SOURCES,
    SOURCE_HOMEWIZARD,
    SOURCE_HOMEWIZARD_V2,
    SOURCE_IAMMETER,
    SOURCE_NAMES,
    SOURCE_SENSORS,
    SOURCE_SHELLY,
    SOURCE_SHELLY_EM,
    SOURCE_SPEEDWIRE,
    STALE_AFTER,
    DirectCandidate,
    DirectMeter,
    PollingMeter,
)
from .homewizard import HOMEWIZARD_METERS, HomeWizardP1, find_homewizard
from .homewizard_v2 import HomeWizardPush
from .iammeter import IammeterMeter, find_iammeter
from .shelly import ShellyEmMeter, ShellyMeter, find_shelly
from .sma import SpeedwireMeter, discover_speedwire

__all__ = [
    "DIRECT_SOURCES",
    "HOMEWIZARD_METERS",
    "SOURCE_HOMEWIZARD",
    "SOURCE_HOMEWIZARD_V2",
    "SOURCE_IAMMETER",
    "SOURCE_NAMES",
    "SOURCE_SENSORS",
    "SOURCE_SHELLY",
    "SOURCE_SHELLY_EM",
    "SOURCE_SPEEDWIRE",
    "STALE_AFTER",
    "DirectCandidate",
    "DirectMeter",
    "PollingMeter",
    "create_meter",
    "discover_speedwire",
    "find_direct_meters",
]


def find_direct_meters(hass: HomeAssistant) -> list[DirectCandidate]:
    """Meters of other integrations that can also be read directly.

    Only reads config entries and the device registry; nothing is sent.
    """
    return [*find_homewizard(hass), *find_shelly(hass), *find_iammeter(hass)]


def create_meter(hass: HomeAssistant, source: str, address: str) -> DirectMeter:
    """The direct meter for a configured source."""
    if source == SOURCE_HOMEWIZARD:
        return HomeWizardP1(hass, address)
    if source == SOURCE_HOMEWIZARD_V2:
        return HomeWizardPush(hass, address)
    if source == SOURCE_SHELLY:
        return ShellyMeter(hass, address)
    if source == SOURCE_SHELLY_EM:
        return ShellyEmMeter(hass, address)
    if source == SOURCE_IAMMETER:
        return IammeterMeter(hass, address)
    return SpeedwireMeter(hass, address)
