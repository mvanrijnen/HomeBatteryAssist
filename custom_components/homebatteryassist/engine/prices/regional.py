"""More price drivers: Amber Electric, PVPC (Spain), Essent and Pure Energie.

- Amber Electric (core, Australia): the price sensors carry a ``forecasts``
  list (``start_time``, ``end_time``, ``per_kwh``), read by the common parser.
- PVPC (core ``pvpc_hourly_pricing``, Spain): hourly prices of today (and of
  tomorrow, once published) as attributes ``price_00h`` … ``price_23h`` and
  ``price_next_day_00h`` … ; parsed here.
- Essent / Energiedirect (HACS, jaapp/ha-essent-dynamic) and Pure Energie
  dynamic pricing (HACS): price lists in sensor attributes; only offered when
  their attributes parse.

None of these is verified on a real installation yet.
"""

from __future__ import annotations

import re
from datetime import timedelta

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from ..inputs.prices import PricePoint
from .base import ROLE_IMPORT, PriceData, PriceDriver, PriceSource
from .sensors import SensorAttributeDriver

PVPC_KEY = re.compile(r"^price_(next_day_)?(\d{2})h$")


def pvpc_points(attributes: dict) -> list[PricePoint]:
    """``price_HHh`` (today) and ``price_next_day_HHh`` (tomorrow), local time."""
    today = dt_util.start_of_local_day()
    points = []
    for key, value in attributes.items():
        match = PVPC_KEY.match(key)
        if not match or not isinstance(value, int | float):
            continue
        day = today + timedelta(days=1 if match.group(1) else 0)
        start = day + timedelta(hours=int(match.group(2)))
        points.append(PricePoint(start, start + timedelta(hours=1), float(value)))
    return sorted(points, key=lambda p: p.start)


class PvpcDriver(PriceDriver):
    """PVPC (Spain): regulated hourly prices."""

    key = "pvpc"
    name = "PVPC (ES)"
    platform = "pvpc_hourly_pricing"

    def find(self, hass: HomeAssistant) -> list[PriceSource]:
        """PVPC price sensors with hourly price attributes."""
        sources = []
        for entry in er.async_get(hass).entities.values():
            if entry.platform != self.platform or entry.domain != "sensor":
                continue
            state = hass.states.get(entry.entity_id)
            if state and pvpc_points(dict(state.attributes)):
                sources.append(
                    PriceSource(
                        self.key,
                        entry.entity_id,
                        f"{self.name}: {state.name}",
                        frozenset({ROLE_IMPORT}),
                        2,
                    )
                )
        return sources

    async def async_read(
        self, hass: HomeAssistant, source: str, role: str
    ) -> PriceData:
        """The hourly prices in the sensor's attributes."""
        state = hass.states.get(source)
        if state is None:
            return PriceData([])
        return PriceData(
            pvpc_points(dict(state.attributes)),
            state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
        )

    def watch(self, hass: HomeAssistant, source: str) -> list[str]:
        """The sensor itself."""
        return [source]


REGIONAL_DRIVERS: tuple[PriceDriver, ...] = (
    SensorAttributeDriver("amber", "Amber Electric", "amberelectric"),
    PvpcDriver(),
    SensorAttributeDriver("essent", "Essent / Energiedirect", "essent"),
    SensorAttributeDriver(
        "pure_energie_dynamic", "Pure Energie", "pure_energie_dynamic"
    ),
)
