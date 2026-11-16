"""The contract of a meter driver: a grid meter or PV meter read directly.

A meter driver knows one kind of meter that can be read without disturbing
anyone (a read-only local API or data the meter broadcasts anyway) and gives
its power per phase, about once a second:

- ``find(hass)``: meters of this kind that Home Assistant already knows (from
  config entries and the device registry); nothing is sent to find them;
- ``create(hass, address)``: a ``DirectMeter`` that reads one meter
  (``async_start`` / ``async_stop``, ``phase_w``, listeners).

The same drivers serve the grid connection and PV sources (``pv_capable``):
a kWh meter or energy meter on the solar inverter's line measures its
production.

Add a driver: copy ``template.py``, fill it in, and add an instance to
``DRIVERS`` in ``__init__.py``. Mark it ``verified`` only after testing on a
real device. Meters are only read, never configured.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .direct import DirectCandidate, DirectMeter


class MeterDriver:
    """A kind of meter that can be read directly."""

    key: str = ""  # stored as meter_source / pv_driver
    name: str = ""
    verified: bool = False  # tested on a real device
    pv_capable: bool = True  # may also measure a PV production

    def find(self, hass: HomeAssistant) -> list[DirectCandidate]:
        """Meters of this kind known to Home Assistant (default: none)."""
        return []

    def create(self, hass: HomeAssistant, address: str) -> DirectMeter:
        """A reader for the meter at ``address``."""
        raise NotImplementedError
