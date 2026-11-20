"""Direct driver: Hoymiles micro-storage over MQTT (S-Miles Home "MQTT
Service") — PREPARED, NOT USED.

The battery publishes discovery-style topics to the broker Home Assistant
already uses: ``homeassistant/<component>/<device id>/<object>/<suffix>``.
Reading only subscribes (passive: any number of subscribers, so it does not
compete with another integration). Battery power on the wire is
+ discharging; it is turned into + charging here.

Control (never called while HomeBatteryAssist is read-only) is a pair of
publishes in this order: EMS mode ``mqtt_ctrl``, then the setpoint in W
(+ discharging on the wire), clamped to the advertised limits; it must be
repeated about every 30 s, and released with setpoint 0 then EMS mode
``general``. Publishing would interfere with another integration that
controls the battery, which is why this stays disabled.

Device facts: Omnibattery's Hoymiles driver (GPL-3.0) as reference for facts
only; own implementation.
"""

from __future__ import annotations

import math
from typing import Any

from ..base import BatteryTelemetry
from ..direct.base import DirectReading
from ..direct.mqtt_driver import MqttBatteryDriver
from .hibattery_1920_ac import HoymilesHiBattery1920Ac
from .hibattery_4020_ac import HoymilesHiBattery4020Ac
from .hibattery_4020_x import HoymilesHiBattery4020X
from .ms_a2 import HoymilesMsA2

PREFIX = "homeassistant"
STATUS = {
    "standby": "idle",
    "charge": "charging",
    "charging": "charging",
    "discharge": "discharging",
    "discharging": "discharging",
}


def number(value: Any) -> float | None:
    """A JSON number or numeric string (older firmware); None otherwise."""
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def first(data: dict[str, Any], *keys: str) -> float | None:
    """The first of ``keys`` that holds a number (system value before unit)."""
    for key in keys:
        if (value := number(data.get(key))) is not None:
            return value
    return None


class HoymilesMqttDriver(MqttBatteryDriver):
    """Hoymiles MS-A2 / HiBattery over MQTT (address = MQTT device id)."""

    key = "hoymiles_mqtt"
    name = "Hoymiles (MQTT)"
    models = (
        HoymilesMsA2,
        HoymilesHiBattery1920Ac,
        HoymilesHiBattery4020X,
        HoymilesHiBattery4020Ac,
    )
    can_write = True  # described below; never called
    refresh_s = 30.0  # drops out of external control without a refresh
    source = "Omnibattery drivers/hoymiles.py (facts only)"

    def topic(self, component: str, obj: str, suffix: str) -> str:
        """A topic of this device."""
        return f"{PREFIX}/{component}/{self.address}/{obj}/{suffix}"

    def topics(self) -> list[str]:
        """The state topics and the power limits."""
        return [
            self.topic("sensor", "quick", "state"),
            self.topic("sensor", "device", "state"),
            self.topic("sensor", "system", "state"),
            self.topic("number", "power_ctrl", "config"),
        ]

    def reading(self, payloads: dict[str, dict[str, Any]]) -> DirectReading:
        """Merge the latest payloads into a reading (+ charging)."""
        merged: dict[str, Any] = {}
        for topic in self.topics()[:3]:
            merged.update(payloads.get(topic, {}))
        limits = payloads.get(self.topics()[3], {})
        battery = first(merged, "sys_bat_p", "bat_p")
        charged = number(merged.get("chg_e"))
        discharged = number(merged.get("dchg_e"))
        return DirectReading(
            soc=first(merged, "sys_soc", "soc"),
            power_w=None if battery is None else -battery,
            telemetry=BatteryTelemetry(
                temperature_c=number(merged.get("bat_temp")),
                voltage_v=number(merged.get("bat_v")),
                charged_today_kwh=None if charged is None else charged / 1000,
                discharged_today_kwh=None if discharged is None else discharged / 1000,
            ),
            extra={
                "ac_power_w": first(merged, "sys_plug_p", "grid_on_p"),  # + out
                "pv_power_w": first(merged, "sys_pv_p", "pv_p"),
                "off_grid_power_w": first(merged, "sys_eps_p", "grid_off_p"),
                "status": STATUS.get(str(merged.get("bat_sts", "")).lower()),
                "packs": number(merged.get("pack_num")),
                "ems_mode": merged.get("ems_mode"),
                "max_charge_w": abs(v) if (v := number(limits.get("min"))) else None,
                "max_discharge_w": number(limits.get("max")),
                "model": (limits.get("device") or {}).get("model")
                or limits.get("model"),
            },
        )

    async def async_set_power(self, power_w: float) -> None:
        """EMS mode ``mqtt_ctrl``, then the setpoint (+ discharging on the
        wire). NEVER called while HomeBatteryAssist is read-only; a real
        controller must also repeat it about every 30 s."""
        self.require_enabled()
        from homeassistant.components import mqtt

        setpoint = round(-power_w)
        await mqtt.async_publish(
            self.hass,
            self.topic("select", "ems_mode", "command"),
            "mqtt_ctrl",
            1,
            False,
        )
        await mqtt.async_publish(
            self.hass,
            self.topic("number", "power_ctrl", "set"),
            str(setpoint),
            1,
            False,
        )

    async def async_release(self) -> None:
        """Setpoint 0, then EMS mode ``general`` (the battery's own control).
        NEVER called yet."""
        self.require_enabled()
        from homeassistant.components import mqtt

        await self.async_set_power(0.0)
        await mqtt.async_publish(
            self.hass, self.topic("select", "ems_mode", "command"), "general", 1, False
        )
