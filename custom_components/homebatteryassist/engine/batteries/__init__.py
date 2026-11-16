"""Battery drivers (see ``base.py``). ``template.py`` is an example only."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .base import BatteryDriver, BatteryTelemetry, platform_of
from .entities import MarstekModbusDriver, OmnibatteryDriver
from .monitor import BatteryConfig

DRIVERS: tuple[BatteryDriver, ...] = (OmnibatteryDriver(), MarstekModbusDriver())

__all__ = ["DRIVERS", "BatteryDriver", "BatteryTelemetry", "driver_for", "telemetry"]


def driver_for(hass: HomeAssistant, config: BatteryConfig) -> BatteryDriver | None:
    """The driver of a (real) battery, by the integration of its sensors."""
    if config.virtual:
        return None
    platform = platform_of(hass, config)
    return next((d for d in DRIVERS if d.key == platform), None)


def telemetry(hass: HomeAssistant, config: BatteryConfig) -> BatteryTelemetry:
    """Extra live details of a battery (empty without a driver)."""
    driver = driver_for(hass, config)
    return driver.telemetry(hass, config) if driver else BatteryTelemetry()
