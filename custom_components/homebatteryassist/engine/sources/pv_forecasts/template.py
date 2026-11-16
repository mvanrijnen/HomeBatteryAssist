"""Template for an own PV forecast source — a code example only.

Copy this file to ``/config/homebatteryassist/pv_forecasts/`` (create the
folder), rename the class, set ``key`` and ``name``, and reload
HomeBatteryAssist. Its forecasts then appear in the settings under "PV
forecast" (as ``custom_<key>:<id>``) next to the solar forecast integrations.

``async_find`` lists the forecasts the source offers; ``async_read`` returns
one as Wh per clock hour (timezone-aware hour starts). Only read: never
control a device. Use Home Assistant's shared HTTP session
(``homeassistant.helpers.aiohttp_client.async_get_clientsession``) for web
services, and keep requests rare (the forecast is read every cycle; cache it).

This example: a forecast from a sensor whose attribute ``wh_hours`` holds
``{ISO hour: Wh}`` (e.g. made by a template or a REST sensor).
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.sources.pv_forecasts.base import (
    PvForecastOption,
    PvForecastSource,
)

ATTRIBUTE = "wh_hours"


class SensorAttributeSource(PvForecastSource):
    """Sensors with a ``wh_hours`` attribute."""

    key = "sensor_wh_hours"  # becomes "custom_sensor_wh_hours"
    name = "Sensor with wh_hours"

    async def async_find(self, hass: HomeAssistant) -> list[PvForecastOption]:
        return [
            PvForecastOption(state.entity_id, state.name)
            for state in hass.states.async_all("sensor")
            if isinstance(state.attributes.get(ATTRIBUTE), dict)
        ]

    async def async_read(
        self, hass: HomeAssistant, option_id: str
    ) -> dict[datetime, float]:
        state = hass.states.get(option_id)
        hours = state.attributes.get(ATTRIBUTE) if state else None
        result: dict[datetime, float] = {}
        for key, wh in (hours or {}).items():
            start = dt_util.parse_datetime(str(key))
            if start is not None:
                result[dt_util.as_utc(start)] = float(wh)
        return result
