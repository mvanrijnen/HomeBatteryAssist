"""Battery drivers (see ``base.py``): models per brand → type range → type,
readers per integration, and the virtual battery (simulation).

``template.py`` is an example only.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from ...measure.batteries import BatteryConfig
from .base import BatteryModel, BatteryReader, BatteryTelemetry, platform_of
from .marstek.venus_e_v3 import MarstekVenusEV3
from .readers import READERS

MODELS: tuple[BatteryModel, ...] = (MarstekVenusEV3(),)

__all__ = [
    "MODELS",
    "READERS",
    "BatteryModel",
    "BatteryReader",
    "BatteryTelemetry",
    "model_for",
    "reader_for",
    "telemetry",
]


def reader_for(hass: HomeAssistant, config: BatteryConfig) -> BatteryReader | None:
    """The reader of a (real) battery, by the integration of its sensors."""
    if config.virtual:
        return None
    platform = platform_of(hass, config)
    return next((r for r in READERS if r.key == platform), None)


def model_for(model: str | None) -> BatteryModel | None:
    """The battery type of a device model name, if known."""
    return next((m for m in MODELS if m.matches(model)), None)


def telemetry(hass: HomeAssistant, config: BatteryConfig) -> BatteryTelemetry:
    """Extra live details of a battery (empty without a reader)."""
    reader = reader_for(hass, config)
    return reader.telemetry(hass, config) if reader else BatteryTelemetry()
