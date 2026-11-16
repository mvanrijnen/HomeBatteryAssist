"""Direct battery drivers: a battery read (and later controlled) by
HomeBatteryAssist itself, not through another integration's entities.

PREPARED, NOT USED. A direct driver talks to the battery over its own
connection (Modbus TCP, local HTTP API, MQTT). Many batteries allow only one
such connection, and today another integration (e.g. Omnibattery) owns it.
So direct drivers are never offered and never connect unless ``enabled`` is
set deliberately; HomeBatteryAssist is read-only and never calls the write
methods. They exist so a switch from another integration to HomeBatteryAssist
is a matter of turning one on.

Shape, per kind of connection:

- ``DirectBatteryDriver`` — the common contract: ``async_open`` /
  ``async_read`` (a ``DirectReading``) / ``async_close``, and the (never
  called) ``async_set_power`` / ``async_release``;
- ``modbus.py`` — ``ModbusBatteryDriver``: a register map as data, read in
  blocks, decoded; a brand only adds its registers and control sequence;
- ``http.py`` — ``HttpBatteryDriver``: a local JSON API through Home
  Assistant's shared session;
- ``mqtt.py`` — ``MqttBatteryDriver``: topics through Home Assistant's own
  MQTT integration (never a second broker connection).

Conventions: power in W, + charging / - discharging (whatever the device
uses on the wire); state of charge in %.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant

from ..base import BatteryModel, BatteryTelemetry


@dataclass(slots=True)
class DirectReading:
    """One reading of a battery read directly."""

    soc: float | None = None  # %
    power_w: float | None = None  # + charging / - discharging
    telemetry: BatteryTelemetry = field(default_factory=BatteryTelemetry)
    extra: dict[str, Any] = field(default_factory=dict)  # device specific


class DirectBatteryDriver:
    """A battery read over its own connection. Disabled unless ``enabled``."""

    key: str = ""
    name: str = ""
    transport: str = ""  # "modbus_tcp", "http", "mqtt"
    models: tuple[type[BatteryModel], ...] = ()  # the types it serves
    verified: bool = False  # reading tested on a real installation
    can_write: bool = False  # write methods implemented (never called yet)
    enabled: bool = False  # never connects unless set deliberately
    source: str = ""  # where the device facts come from

    # -- How the battery must be controlled (used by engine/control) --------
    # Repeat the last command at least this often (0 = not needed), e.g. a
    # battery that drops out of external control without refreshes.
    refresh_s: float = 0.0
    # At most one new command this often, and only when it differs by at least
    # ``deadband_w`` (devices that ramp slowly or wear on writes).
    min_interval_s: float = 0.0
    deadband_w: float = 0.0
    # 0 W is not "idle" for this battery (e.g. it still limits PV): idle must be
    # a release, never a 0 W command.
    idle_is_release: bool = False
    max_charge_w: float | None = None  # hard limits of the device, if known
    max_discharge_w: float | None = None

    def __init__(self, hass: HomeAssistant, address: str, **options: Any) -> None:
        """Initialize for one battery at ``address`` (host / IP / device id)."""
        self.hass = hass
        self.address = address
        self.options = options

    async def async_open(self) -> None:
        """Open the connection (only when enabled)."""
        if not self.enabled:
            raise RuntimeError(f"{self.name}: direct driver is not enabled")

    async def async_read(self) -> DirectReading:
        """Read the battery now."""
        raise NotImplementedError

    async def async_close(self) -> None:
        """Close the connection."""

    async def async_set_power(self, power_w: float) -> None:
        """Charge (+) / discharge (-) at ``power_w``. NEVER called while
        HomeBatteryAssist is read-only."""
        raise NotImplementedError

    async def async_release(self) -> None:
        """Hand control back to the battery's own logic. NEVER called yet."""
        raise NotImplementedError
