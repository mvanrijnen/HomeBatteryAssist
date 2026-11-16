"""The interface of a weather source.

A weather source reads the outdoor temperature now and its forecast per
clock hour (UTC hour start -> °C). HomeBatteryAssist keeps the final say:
values outside ``MIN_C``..``MAX_C`` or not finite are dropped. A source only
reads; it never controls anything.
"""

from __future__ import annotations

import math
from datetime import datetime

from homeassistant.core import HomeAssistant

MIN_C = -60.0
MAX_C = 60.0


def valid_temperature(value: object) -> float | None:
    """``value`` as °C if it is a believable outdoor temperature."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and MIN_C <= number <= MAX_C else None


class WeatherSource:
    """Base class of a weather source."""

    key: str = ""
    name: str = ""

    def temperature_now(self, hass: HomeAssistant) -> float | None:
        """The outdoor temperature now (°C), or None."""
        raise NotImplementedError

    async def async_forecast(self, hass: HomeAssistant) -> dict[datetime, float]:
        """Forecast temperature (°C) per UTC clock hour start."""
        raise NotImplementedError
