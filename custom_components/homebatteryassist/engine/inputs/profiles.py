"""Battery profiles: recognise batteries that other integrations already expose.

A profile maps the translation keys of another integration's entities to the
fields of a battery subentry, so a battery can be linked with all values filled
in. This only reads the entity registry and states; it never talks to the
battery itself, so it cannot interfere with the integration that owns it.

Only add profiles whose entity keys were verified against a real installation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ...const import (
    CONF_CAPACITY,
    CONF_EFFICIENCY,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_PHASE,
    CONF_POWER_SENSOR,
    CONF_POWER_SIGN,
    CONF_SOC_SENSOR,
    PHASE_IDS,
    SIGN_DISCHARGING_POSITIVE,
)
from .units import parse_float


@dataclass(frozen=True, slots=True)
class BatteryProfile:
    """How a battery of another integration is exposed in Home Assistant."""

    platform: str  # integration domain that creates the entities
    label: str
    soc: str  # translation key of the state of charge sensor
    power: str  # translation key of the (AC) power sensor
    power_sign: str
    # Optional translation keys (domain, key) whose state gives a starting value
    capacity: tuple[str, str] | None = None  # kWh
    max_charge: tuple[str, str] | None = None  # W
    max_discharge: tuple[str, str] | None = None  # W
    min_soc: tuple[str, str] | None = None  # %
    max_soc: tuple[str, str] | None = None  # %
    efficiency: tuple[str, str] | None = None  # %
    phase: tuple[str, str] | None = None  # select with options l1/l2/l3


PROFILES: tuple[BatteryProfile, ...] = (
    # Omnibattery (ffunes/Omnibattery), verified with a Marstek Venus E v3.
    # ac_power is the grid side of the battery: + discharging / - charging.
    BatteryProfile(
        platform="omnibattery",
        label="Omnibattery",
        soc="battery_soc",
        power="ac_power",
        power_sign=SIGN_DISCHARGING_POSITIVE,
        capacity=("sensor", "battery_total_energy"),
        max_charge=("number", "max_charge_power"),
        max_discharge=("number", "max_discharge_power"),
        min_soc=("number", "discharging_cutoff_capacity"),
        max_soc=("number", "charging_cutoff_capacity"),
        efficiency=("sensor", "round_trip_efficiency_total"),
        phase=("select", "battery_phase"),
    ),
    # Marstek Modbus (ViperRNMC/marstek_venus_modbus), keys verified.
    BatteryProfile(
        platform="marstek_modbus",
        label="Marstek Modbus",
        soc="battery_soc",
        power="ac_power",
        power_sign=SIGN_DISCHARGING_POSITIVE,
        capacity=("sensor", "battery_rated_capacity"),
        max_charge=("number", "max_charge_power"),
        max_discharge=("number", "max_discharge_power"),
        efficiency=("sensor", "round_trip_efficiency_total"),
    ),
)


@dataclass(frozen=True, slots=True)
class BatteryCandidate:
    """A battery found in another integration, with suggested subentry data."""

    device_id: str
    name: str
    model: str | None
    profile: BatteryProfile
    data: dict[str, Any]

    @property
    def label(self) -> str:
        """Shown in the selection list, e.g. "Marstek Venus 1 - Venus E v3 (Omnibattery)"."""
        model = f" - {self.model}" if self.model else ""
        return f"{self.name}{model} ({self.profile.label})"


def _value(hass: HomeAssistant, entity_id: str | None) -> Any:
    state = hass.states.get(entity_id) if entity_id else None
    return state.state if state else None


def find_battery_candidates(
    hass: HomeAssistant, exclude_sensors: set[str]
) -> list[BatteryCandidate]:
    """Batteries exposed by known integrations that are not linked yet."""
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    candidates: list[BatteryCandidate] = []
    for profile in PROFILES:
        by_device: dict[str, dict[tuple[str, str], str]] = {}
        for entry in entities.entities.values():
            if (
                entry.platform != profile.platform
                or entry.disabled_by
                or not entry.device_id
            ):
                continue
            key = (entry.domain, entry.translation_key or "")
            by_device.setdefault(entry.device_id, {})[key] = entry.entity_id

        for device_id, keyed in by_device.items():
            soc = keyed.get(("sensor", profile.soc))
            power = keyed.get(("sensor", profile.power))
            if not soc or not power or {soc, power} & exclude_sensors:
                continue
            device = devices.async_get(device_id)
            name = (device.name_by_user or device.name) if device else soc
            candidates.append(
                BatteryCandidate(
                    device_id,
                    name or soc,
                    device.model if device else None,
                    profile,
                    _suggest(hass, profile, keyed, name, soc, power),
                )
            )
    return candidates


def _suggest(
    hass: HomeAssistant,
    profile: BatteryProfile,
    keyed: dict[tuple[str, str], str],
    name: str | None,
    soc: str,
    power: str,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        CONF_NAME: name or soc,
        CONF_SOC_SENSOR: soc,
        CONF_POWER_SENSOR: power,
        CONF_POWER_SIGN: profile.power_sign,
    }
    for field, ref in (
        (CONF_CAPACITY, profile.capacity),
        (CONF_MAX_CHARGE_POWER, profile.max_charge),
        (CONF_MAX_DISCHARGE_POWER, profile.max_discharge),
        (CONF_MIN_SOC, profile.min_soc),
        (CONF_MAX_SOC, profile.max_soc),
        (CONF_EFFICIENCY, profile.efficiency),
    ):
        if ref and (value := parse_float(_value(hass, keyed.get(ref)))) is not None:
            data[field] = round(value, 2) if field == CONF_CAPACITY else round(value)
    if profile.phase:
        phase = str(_value(hass, keyed.get(profile.phase)) or "").lower()
        if phase in PHASE_IDS:
            data[CONF_PHASE] = phase
    return data
