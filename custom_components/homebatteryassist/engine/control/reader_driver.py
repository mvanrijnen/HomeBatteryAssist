"""A battery controlled through the integration it is linked with
(``ReaderDriver``) or through its own direct connection (``LinkDriver``).

``BatteryController`` works with a driver (``DirectBatteryDriver``). For a
battery that is read through another integration (Omnibattery, Marstek
Modbus) this adapter turns that integration's reader into such a driver: its
``async_set_power`` / ``async_release`` (e.g. Omnibattery: the battery's
manual mode and charge/discharge power). Used by the control test
(``control_test.py``) and, once active, the control loop.

The controller's master switch decides whether anything is sent at all.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from ..devices.batteries.base import BatteryReader
from ..devices.batteries.direct.base import DirectBatteryDriver, DirectReading
from ..measure.battery_monitor import BatteryConfig


class ReaderDriver(DirectBatteryDriver):
    """A battery reached through its integration, in the shape of a driver."""

    transport = "integration"
    can_write = True
    # Integrations write through entities: not more often than this, and only
    # for a real change (each write is a state change in Home Assistant).
    min_interval_s = 5.0
    deadband_w = 50.0

    def __init__(
        self, hass: HomeAssistant, reader: BatteryReader, config: BatteryConfig
    ) -> None:
        """Initialize."""
        super().__init__(hass, config.power_sensor)
        self.reader = reader
        self.config = config
        self.name = config.name
        self.max_charge_w = config.max_charge_w
        self.max_discharge_w = config.max_discharge_w
        self.enabled = True  # the controller's master switch decides

    async def async_read(self) -> DirectReading:
        """Reading stays with ``BatteryInput``."""
        return DirectReading()

    async def async_set_power(self, power_w: float) -> None:
        """Charge (+) / discharge (-) through the integration."""
        await self.reader.async_set_power(self.hass, self.config, power_w)

    async def async_release(self) -> None:
        """Back to the integration's own control."""
        await self.reader.async_release(self.hass, self.config)


class LinkDriver(DirectBatteryDriver):
    """A battery with a direct connection (``DirectLink``), in the shape of a
    driver for ``BatteryController``: commands go through the link's driver
    over the same connection it reads with; its control needs (refresh,
    pacing, limits) are the driver's."""

    transport = "direct"
    can_write = True

    def __init__(self, hass: HomeAssistant, link: Any, config: BatteryConfig) -> None:
        """Initialize."""
        super().__init__(hass, link.driver.address)
        self.link = link
        self.config = config
        self.name = config.name
        driver = link.driver
        self.refresh_s = driver.refresh_s
        self.min_interval_s = driver.min_interval_s
        self.deadband_w = driver.deadband_w
        self.idle_is_release = driver.idle_is_release
        self.max_charge_w = min(
            config.max_charge_w, driver.max_charge_w or config.max_charge_w
        )
        self.max_discharge_w = min(
            config.max_discharge_w, driver.max_discharge_w or config.max_discharge_w
        )
        self.enabled = True  # the controller's master switch decides

    async def async_read(self) -> DirectReading:
        """Reading stays with the link (``BatteryInput``)."""
        return DirectReading()

    async def async_set_power(self, power_w: float) -> None:
        """Charge (+) / discharge (-) through the direct connection."""
        await self.link.async_set_power(power_w)

    async def async_release(self) -> None:
        """Back to the battery's own control."""
        await self.link.async_release()
