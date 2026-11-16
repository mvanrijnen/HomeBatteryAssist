"""The interface of a PV forecast source module.

A PV forecast source offers one or more forecasts (``find``) and reads a
forecast as expected energy (Wh) per clock hour (``async_read``). Several
chosen forecasts are summed per hour (e.g. one per roof). HomeBatteryAssist
keeps the final say: values that are negative, non-finite or absurd (more
than ``MAX_WH`` per hour) are dropped, and the learned PV correction and the
safety margin are applied afterwards.

A source only reads (an integration's data, a web service, a file); it never
controls anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.core import HomeAssistant

MAX_WH = 100_000.0  # per hour; anything beyond is not believed


@dataclass(frozen=True, slots=True)
class PvForecastOption:
    """One forecast a source offers (shown in the settings)."""

    id: str  # unique within the source
    label: str


class PvForecastSource:
    """Base class of a PV forecast source module.

    Subclasses set ``key`` (unique, lowercase), ``name`` and implement ``find``
    and ``async_read``.
    """

    key: str = ""
    name: str = ""
    description: str = ""

    async def async_find(self, hass: HomeAssistant) -> list[PvForecastOption]:
        """The forecasts this source offers now."""
        raise NotImplementedError

    async def async_read(
        self, hass: HomeAssistant, option_id: str
    ) -> dict[datetime, float]:
        """Expected energy (Wh) per clock hour start (timezone-aware)."""
        raise NotImplementedError
