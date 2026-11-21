"""Battery profiles: recognise batteries that other integrations already expose.

Each reader (``integrations/``) has a profile that maps the translation keys of its
integration's entities to the fields of a battery subentry, so a battery can be
linked with all values filled in; a recognised battery type (``marstek/...``)
fills in what the integration does not tell. This only reads the entity registry and states; it never talks to the
battery itself, so it cannot interfere with the integration that owns it.

Profiles not verified against a real installation keep ``verified = False``
and are shown as "not tested".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ....const import (
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
)
from ...units import parse_float
from .base import BatteryModel, BatteryProfile
from .integrations import READERS

PROFILES: tuple[BatteryProfile, ...] = tuple(
    r.profile for r in READERS if r.profile is not None
)


@dataclass(frozen=True, slots=True)
class BatteryCandidate:
    """A battery found in another integration, with suggested subentry data."""

    device_id: str
    name: str
    model: str | None
    profile: BatteryProfile
    data: dict[str, Any]
    battery_model: BatteryModel | None = None  # recognised battery type

    @property
    def label(self) -> str:
        """Shown in the selection list, e.g. "Marstek Venus 1 - Venus E v3 (Omnibattery)"."""
        model = f" - {self.model}" if self.model else ""
        return f"{self.name}{model} ({self.profile.label})"


def _model_for(model: str | None) -> BatteryModel | None:
    from . import model_for  # the registry imports this module's neighbours

    return model_for(model)


def _value(hass: HomeAssistant, entity_id: str | None) -> Any:
    state = hass.states.get(entity_id) if entity_id else None
    return state.state if state else None


# A start value in the form's unit (kWh for the capacity, W for powers),
# from the unit the sensor gives.
_TO_FORM_UNIT = {
    "Wh": 0.001,
    "kWh": 1.0,
    "MWh": 1000.0,
    "W": 1.0,
    "kW": 1000.0,
}


def _factor(hass: HomeAssistant, entity_id: str | None, field: str) -> float | None:
    """Factor to the form's unit; None when the unit does not fit the field
    (no start value then)."""
    state = hass.states.get(entity_id) if entity_id else None
    unit = str((state.attributes.get("unit_of_measurement") if state else "") or "")
    if field == CONF_CAPACITY:
        return (
            _TO_FORM_UNIT.get(unit, 1.0) if unit in ("", "Wh", "kWh", "MWh") else None
        )
    if field in (CONF_MAX_CHARGE_POWER, CONF_MAX_DISCHARGE_POWER):
        return _TO_FORM_UNIT.get(unit, 1.0) if unit in ("", "W", "kW") else None
    return 1.0


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
            model = device.model if device else None
            battery_model = _model_for(model)
            candidates.append(
                BatteryCandidate(
                    device_id,
                    name or soc,
                    model,
                    profile,
                    _suggest(hass, profile, keyed, name, soc, power, battery_model),
                    battery_model,
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
    battery_model: BatteryModel | None = None,
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
            if value <= 0 and field != CONF_MIN_SOC:
                continue  # e.g. -1 = "no limit" (Victron ESS): not a start value
            factor = _factor(hass, keyed.get(ref), field)
            if factor is None:
                continue  # a unit that does not fit: no start value
            value *= factor
            data[field] = round(value, 2) if field == CONF_CAPACITY else round(value)
    # What the integration does not tell, the recognised battery type may know.
    if battery_model is not None:
        for field, value in (
            (CONF_CAPACITY, battery_model.capacity_kwh),
            (CONF_MAX_CHARGE_POWER, battery_model.max_charge_w),
            (CONF_MAX_DISCHARGE_POWER, battery_model.max_discharge_w),
        ):
            if field not in data and value is not None:
                data[field] = value if field == CONF_CAPACITY else round(value)
    if profile.phase:
        phase = str(_value(hass, keyed.get(profile.phase)) or "").lower()
        if phase in PHASE_IDS:
            data[CONF_PHASE] = phase
    return data
