"""Grid meter profiles: recognise meters that other integrations already expose.

Instead of choosing a sensor per phase, the user can pick a detected meter
(e.g. a HomeWizard P1 meter) and the phase sensors are filled in. Like the
battery profiles this only reads the entity registry; it never talks to the
meter, so it cannot interfere with the integration that owns it. Choosing the
sensors manually always remains possible.

Profiles not verified against a real installation keep ``verified = False``
and are shown as "not tested".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ....const import CONF_PHASE_SENSORS


@dataclass(frozen=True, slots=True)
class MeterProfile:
    """How a grid meter of another integration is exposed in Home Assistant."""

    platform: str  # integration domain that creates the entities
    label: str
    marker: str  # translation key of a sensor only grid meters have
    phase_power: str  # translation key of the signed power sensor per phase
    phase_pattern: str  # regex on the unique id, group 1 = phase number
    address_key: str | None = None  # config entry data key with the IP address
    direct: str | None = None  # direct source that can read this meter
    # Tested on a real installation (else shown as "not tested").
    verified: bool = False


PROFILES: tuple[MeterProfile, ...] = (
    # HomeWizard P1 meter (core integration "homewizard"), verified on a
    # HWE-P1 with a 3-phase DSMR 5 meter: active_power_l1_w ... l3_w, signed
    # (+ import / - export). kWh meters and sockets have no dsmr_version.
    MeterProfile(
        platform="homewizard",
        label="HomeWizard P1",
        marker="dsmr_version",
        phase_power="active_power_phase_w",
        phase_pattern=r"_active_power_l([123])_w$",
        address_key="ip_address",
        direct="homewizard",
        verified=True,
    ),
    # Victron GX (core integration "victron_gx", local MQTT): the system's
    # grid power per phase, + import; all phases share one translation key,
    # the phase is in the unique id. From the integration's library, NOT
    # tested on a real installation.
    MeterProfile(
        platform="victron_gx",
        label="Victron GX",
        marker="system_grid_phases",
        phase_power="system_grid_power_phase",
        phase_pattern=r"_system_grid_power_l([123])$",
    ),
)


@dataclass(frozen=True, slots=True)
class MeterCandidate:
    """A grid meter found in another integration, with its phase sensors."""

    device_id: str
    name: str
    model: str | None
    profile: MeterProfile
    sensors: dict[str, str]  # sensor_l1.. -> entity id (signed power)
    address: str | None = None  # IP address (from the owning config entry)

    @property
    def phases(self) -> int:
        """Number of phases the meter measures."""
        return len(self.sensors)

    @property
    def label(self) -> str:
        """Shown in the selection list, e.g. "P1 meter - HWE-P1 (HomeWizard P1, 3 phases)"."""
        model = f" - {self.model}" if self.model and self.model != self.name else ""
        return f"{self.name}{model} ({self.profile.label}, {self.phases}x)"


def find_meter_candidates(hass: HomeAssistant) -> list[MeterCandidate]:
    """Grid meters exposed by known integrations (1 or 3 phases)."""
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    candidates: list[MeterCandidate] = []
    for profile in PROFILES:
        pattern = re.compile(profile.phase_pattern)
        markers: set[str] = set()
        phases: dict[str, dict[int, str]] = {}
        for entry in entities.entities.values():
            if (
                entry.platform != profile.platform
                or entry.domain != "sensor"
                or not entry.device_id
            ):
                continue
            if entry.translation_key == profile.marker:
                markers.add(entry.device_id)
            elif (
                entry.translation_key == profile.phase_power
                and not entry.disabled_by
                and (match := pattern.search(entry.unique_id))
            ):
                phases.setdefault(entry.device_id, {})[int(match.group(1))] = (
                    entry.entity_id
                )
        for device_id in sorted(markers):
            found = phases.get(device_id, {})
            count = 3 if all(n in found for n in (1, 2, 3)) else 1 if 1 in found else 0
            if not count:
                continue
            device = devices.async_get(device_id)
            name = (device.name_by_user or device.name) if device else None
            address = next(
                (
                    entry.data.get(profile.address_key)
                    for entry_id in (device.config_entries if device else ())
                    if (entry := hass.config_entries.async_get_entry(entry_id))
                    and entry.domain == profile.platform
                    and profile.address_key
                ),
                None,
            )
            candidates.append(
                MeterCandidate(
                    device_id,
                    name or profile.label,
                    device.model if device else None,
                    profile,
                    {CONF_PHASE_SENSORS[n - 1]: found[n] for n in range(1, count + 1)},
                    address,
                )
            )
    return candidates
