"""Price drivers for integrations that put their prices in sensor attributes.

ENTSO-e, EPEX Spot, Nord Pool (HACS), Frank Energie and Zonneplan (all HACS)
publish today's and tomorrow's prices as a list in an attribute of a sensor.
The common formats are read by ``prices.parse_price_forecast``. A sensor of
the integration is only offered when its attributes really contain future
prices, so a changed format shows up as "not offered" rather than as wrong
prices. Not yet verified on a real installation.
"""

from __future__ import annotations

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from ..inputs.prices import parse_price_forecast
from .base import ROLE_IMPORT, ROLE_MARKET, PriceData, PriceDriver, PriceSource


class SensorAttributeDriver(PriceDriver):
    """Prices from the attributes of the sensors of one integration."""

    def __init__(
        self,
        key: str,
        name: str,
        platform: str,
        roles: frozenset[str] = frozenset({ROLE_IMPORT}),
        days_ahead: float = 2,
    ) -> None:
        """Initialize: ``platform`` is the integration domain of the sensors."""
        self.key = key
        self.name = name
        self.platform = platform
        self.roles = roles
        self.days_ahead = days_ahead

    def find(self, hass: HomeAssistant) -> list[PriceSource]:
        """Sensors of the integration whose attributes hold future prices."""
        now = dt_util.utcnow()
        sources = []
        for entry in er.async_get(hass).entities.values():
            if entry.platform != self.platform or entry.domain != "sensor":
                continue
            points = parse_price_forecast(hass.states.get(entry.entity_id))
            if not any(p.end > now for p in points):
                continue
            state = hass.states.get(entry.entity_id)
            name = state.name if state else entry.entity_id
            sources.append(
                PriceSource(
                    self.key,
                    entry.entity_id,
                    f"{self.name}: {name}",
                    self.roles,
                    self.days_ahead,
                    forecast_only=self.forecast_only,
                )
            )
        return sources

    async def async_read(
        self, hass: HomeAssistant, source: str, role: str
    ) -> PriceData:
        """The prices in the sensor's attributes."""
        state = hass.states.get(source)
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) if state else None
        return PriceData(parse_price_forecast(state), unit)

    def watch(self, hass: HomeAssistant, source: str) -> list[str]:
        """The sensor itself."""
        return [source]


SENSOR_DRIVERS: tuple[PriceDriver, ...] = (
    SensorAttributeDriver(
        "entsoe", "ENTSO-e", "entsoe", frozenset({ROLE_IMPORT, ROLE_MARKET})
    ),
    SensorAttributeDriver(
        "epex_spot", "EPEX Spot", "epex_spot", frozenset({ROLE_IMPORT, ROLE_MARKET})
    ),
    SensorAttributeDriver("nordpool_hacs", "Nord Pool (HACS)", "nordpool"),
    SensorAttributeDriver("frank_energie", "Frank Energie", "frank_energie"),
    SensorAttributeDriver("zonneplan", "Zonneplan", "zonneplan_one"),
)
