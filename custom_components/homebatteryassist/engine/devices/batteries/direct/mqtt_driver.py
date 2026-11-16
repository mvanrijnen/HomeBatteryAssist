"""Generic MQTT battery driver through Home Assistant's own MQTT integration
(never a second broker connection). A brand subclass lists the state topics
and maps their JSON payloads onto a reading; it only subscribes. Publishing
commands belongs in ``async_set_power`` / ``async_release`` (never called
while HomeBatteryAssist is read-only)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .base import DirectBatteryDriver, DirectReading


class MqttBatteryDriver(DirectBatteryDriver):
    """A battery that publishes its state over MQTT (push)."""

    transport = "mqtt"

    def __init__(self, hass: Any, address: str, **options: Any) -> None:
        """Initialize; ``address`` is the device id used in the topics."""
        super().__init__(hass, address, **options)
        self.payloads: dict[str, dict[str, Any]] = {}  # topic -> last payload
        self._unsubs: list[Callable[[], None]] = []

    def topics(self) -> list[str]:
        """The state topics to follow."""
        raise NotImplementedError

    async def async_open(self) -> None:
        """Subscribe to the state topics (only when enabled)."""
        await super().async_open()
        from homeassistant.components import mqtt  # only when really used

        for topic in self.topics():

            def received(message: Any, topic: str = topic) -> None:
                try:
                    data = json.loads(message.payload)
                except (TypeError, ValueError):
                    return
                if isinstance(data, dict):
                    self.payloads[topic] = data

            self._unsubs.append(await mqtt.async_subscribe(self.hass, topic, received))

    async def async_close(self) -> None:
        """Unsubscribe."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    async def async_read(self) -> DirectReading:
        """The latest pushed state."""
        return self.reading(self.payloads)

    def reading(self, payloads: dict[str, dict[str, Any]]) -> DirectReading:
        """Map the last payloads onto a reading."""
        raise NotImplementedError
