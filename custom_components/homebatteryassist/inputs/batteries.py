"""Home batteries: configuration, live state and monitoring counters.

A battery is linked read-only through entities of its own integration (state
of charge and power sensors), so any brand works and the integration that owns
the battery is never disturbed. HomeBatteryAssist never controls a battery.
Battery power is normalised to: positive = charging, negative = discharging.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, TypedDict

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_CAPACITY,
    CONF_EFFICIENCY,
    CONF_FULL_CHARGE_INTERVAL,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_PHASE,
    CONF_POWER_SENSOR,
    CONF_POWER_SIGN,
    CONF_SOC_SENSOR,
    DEFAULT_EFFICIENCY,
    DEFAULT_FULL_CHARGE_INTERVAL,
    DEFAULT_MAX_SOC,
    DEFAULT_MIN_SOC,
    DOMAIN,
    FULL_CHARGE_SOC,
    IDLE_THRESHOLD_W,
    PHASE_NONE,
    SIGN_CHARGING_POSITIVE,
    SIGN_DISCHARGING_POSITIVE,
    SUBENTRY_BATTERY,
)
from ..explain import DecisionLog
from .units import parse_float, state_to_watts

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY = 60  # seconds


class BatteryStatus(StrEnum):
    """What the battery is doing."""

    CHARGING = "charging"
    DISCHARGING = "discharging"
    IDLE = "idle"


@dataclass(frozen=True, slots=True)
class BatteryConfig:
    """Static properties of one battery (from its subentry)."""

    id: str  # subentry id
    name: str
    soc_sensor: str
    power_sensor: str
    power_sign: str
    capacity_kwh: float
    max_charge_w: float
    max_discharge_w: float
    min_soc: float
    max_soc: float
    efficiency: float  # round trip, 0..1
    full_charge_interval_days: int  # 0 = no periodic full charge
    phase: str

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> BatteryConfig:
        """Build from subentry data."""
        data: Mapping[str, Any] = subentry.data
        return cls(
            id=subentry.subentry_id,
            name=data[CONF_NAME],
            soc_sensor=data[CONF_SOC_SENSOR],
            power_sensor=data[CONF_POWER_SENSOR],
            power_sign=data.get(CONF_POWER_SIGN, SIGN_CHARGING_POSITIVE),
            capacity_kwh=float(data[CONF_CAPACITY]),
            max_charge_w=float(data[CONF_MAX_CHARGE_POWER]),
            max_discharge_w=float(data[CONF_MAX_DISCHARGE_POWER]),
            min_soc=float(data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)),
            max_soc=float(data.get(CONF_MAX_SOC, DEFAULT_MAX_SOC)),
            efficiency=float(data.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)) / 100,
            full_charge_interval_days=int(
                data.get(CONF_FULL_CHARGE_INTERVAL, DEFAULT_FULL_CHARGE_INTERVAL)
            ),
            phase=data.get(CONF_PHASE, PHASE_NONE),
        )


@dataclass(frozen=True, slots=True)
class BatteryState:
    """Live values of one battery, derived quantities via the config."""

    config: BatteryConfig
    soc: float | None  # %
    power_w: float | None  # + charging / - discharging

    @property
    def available(self) -> bool:
        """True when both state of charge and power are known."""
        return self.soc is not None and self.power_w is not None

    @property
    def status(self) -> BatteryStatus | None:
        """Charging, discharging or idle."""
        if self.power_w is None:
            return None
        if self.power_w > IDLE_THRESHOLD_W:
            return BatteryStatus.CHARGING
        if self.power_w < -IDLE_THRESHOLD_W:
            return BatteryStatus.DISCHARGING
        return BatteryStatus.IDLE

    def _energy(self, from_soc: float, to_soc: float) -> float | None:
        if self.soc is None:
            return None
        return round(max(to_soc - from_soc, 0.0) * self.config.capacity_kwh / 100, 3)

    @property
    def stored_kwh(self) -> float | None:
        """Energy in the battery."""
        return self._energy(0.0, self.soc) if self.soc is not None else None

    @property
    def usable_kwh(self) -> float | None:
        """Energy that may be discharged (above the minimum state of charge)."""
        return (
            self._energy(self.config.min_soc, self.soc)
            if self.soc is not None
            else None
        )

    @property
    def room_kwh(self) -> float | None:
        """Energy that may still be charged (up to the maximum state of charge)."""
        return (
            self._energy(self.soc, self.config.max_soc)
            if self.soc is not None
            else None
        )

    def time_to_target(self, now: datetime) -> datetime | None:
        """When the battery is full (charging) or empty (discharging) at this power."""
        if self.status is BatteryStatus.CHARGING and self.room_kwh is not None:
            energy, power = self.room_kwh, self.power_w
        elif self.status is BatteryStatus.DISCHARGING and self.usable_kwh is not None:
            energy, power = self.usable_kwh, -self.power_w  # type: ignore[operator]
        else:
            return None
        return now + timedelta(hours=energy * 1000 / power)  # type: ignore[operator]


def battery_configs(entry: ConfigEntry) -> list[BatteryConfig]:
    """All batteries configured as subentries."""
    return [
        BatteryConfig.from_subentry(subentry)
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_BATTERY
    ]


def _soc(state: State | None) -> float | None:
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    value = parse_float(state.state)
    if value is None or not 0 <= value <= 100:
        return None
    return value


def battery_power(hass: HomeAssistant, config: BatteryConfig) -> float | None:
    """Battery power in W, + charging / - discharging, or None if unknown."""
    watts = state_to_watts(hass.states.get(config.power_sensor))
    if watts is None:
        return None
    return -watts if config.power_sign == SIGN_DISCHARGING_POSITIVE else watts


def read_battery(hass: HomeAssistant, config: BatteryConfig) -> BatteryState:
    """Read the current state of a battery."""
    return BatteryState(
        config, _soc(hass.states.get(config.soc_sensor)), battery_power(hass, config)
    )


class BatteryStats(TypedDict):
    """Monitoring counters of one battery, persisted."""

    charged_kwh: float
    discharged_kwh: float
    last_full_charge: str | None  # ISO 8601, UTC


class BatteryInput:
    """Follows all batteries: live state, energy counters and full charges."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, decisions: DecisionLog
    ) -> None:
        """Initialize."""
        self.hass = hass
        self._decisions = decisions
        self.configs = battery_configs(entry)
        self.states: dict[str, BatteryState] = {
            c.id: BatteryState(c, None, None) for c in self.configs
        }
        self.stats: dict[str, BatteryStats] = {}
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.batteries"
        )
        self._last_power: dict[str, tuple[datetime, float]] = {}
        self._was_available: dict[str, bool] = {}
        self._listeners: list[Callable[[], None]] = []
        self._unsub: CALLBACK_TYPE | None = None

    async def async_start(self) -> None:
        """Load counters and start following the battery sensors."""
        stored = (await self._store.async_load() or {}).get("stats", {})
        for config in self.configs:
            self.stats[config.id] = BatteryStats(
                charged_kwh=0.0, discharged_kwh=0.0, last_full_charge=None
            ) | stored.get(config.id, {})
        entity_ids = [e for c in self.configs for e in (c.soc_sensor, c.power_sensor)]
        if entity_ids:
            self._unsub = async_track_state_change_event(
                self.hass, entity_ids, self._async_state_changed
            )
        now = dt_util.utcnow()
        for config in self.configs:
            self._update(config, now)

    async def async_stop(self) -> None:
        """Stop following and persist the counters."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        await self._store.async_save(self._data())

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call ``listener`` whenever a battery changes."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def full_charge_due(self, battery_id: str, now: datetime) -> datetime | None:
        """When the next periodic full charge is due, if configured."""
        config = next(c for c in self.configs if c.id == battery_id)
        if config.full_charge_interval_days <= 0:
            return None
        last = self.stats[battery_id]["last_full_charge"]
        if last is None:
            return now
        return dt_util.parse_datetime(last) + timedelta(  # type: ignore[operator]
            days=config.full_charge_interval_days
        )

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        for config in self.configs:
            if entity_id in (config.soc_sensor, config.power_sensor):
                self._update(config, event.time_fired)

    def _update(self, config: BatteryConfig, when: datetime) -> None:
        previous = self.states[config.id]
        state = read_battery(self.hass, config)
        self.states[config.id] = state

        self._count_energy(config.id, when, state.power_w)
        if (
            state.soc is not None
            and state.soc >= FULL_CHARGE_SOC
            and (previous.soc is None or previous.soc < FULL_CHARGE_SOC)
        ):
            self.stats[config.id]["last_full_charge"] = when.isoformat()
            self._decisions.async_log(
                "battery", "battery_full_charge", name=config.name
            )
        self._explain_availability(config, state.available)

        self._store.async_delay_save(self._data, SAVE_DELAY)
        for listener in list(self._listeners):
            listener()

    def _count_energy(
        self, battery_id: str, when: datetime, power: float | None
    ) -> None:
        """Integrate the previous power value up to ``when`` (kWh counters)."""
        if (last := self._last_power.pop(battery_id, None)) is not None:
            since, last_power = last
            kwh = last_power * max((when - since).total_seconds(), 0.0) / 3_600_000
            stats = self.stats[battery_id]
            if kwh > 0:
                stats["charged_kwh"] = round(stats["charged_kwh"] + kwh, 4)
            elif kwh < 0:
                stats["discharged_kwh"] = round(stats["discharged_kwh"] - kwh, 4)
        if power is not None:
            self._last_power[battery_id] = (when, power)

    def _explain_availability(self, config: BatteryConfig, available: bool) -> None:
        """Explain losing / regaining a battery (not the first state at start-up)."""
        was = self._was_available.get(config.id)
        if was is not None and was != available:
            self._decisions.async_log(
                "battery",
                "battery_restored" if available else "battery_unavailable",
                name=config.name,
            )
        if available or was is not None:
            self._was_available[config.id] = available

    def _data(self) -> dict[str, Any]:
        return {"stats": self.stats}
