"""HomeWizard P1 meter and kWh meters (1- and 3-phase): local API v1
(``GET /api/v1/data``, a read-only endpoint any number of clients may poll).
The address comes from the HomeWizard integration's config entry. Verified."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .direct_reading import (
    SOURCE_HOMEWIZARD,
    SOURCE_HOMEWIZARD_V2,
    DirectCandidate,
    PhaseReading,
    PollingMeter,
    per_phase,
)

# HomeWizard meters (product type = device model id) -> phases (None: depends
# on the smart meter). Energy sockets and water meters are no grid meters.
HOMEWIZARD_METERS: dict[str, int | None] = {
    "HWE-P1": None,
    "HWE-KWH1": 1,
    "SDM230-wifi": 1,
    "HWE-KWH3": 3,
    "SDM630-wifi": 3,
}


class HomeWizardP1(PollingMeter):
    """Polls a HomeWizard P1 meter's local API v1 every second."""

    label = SOURCE_HOMEWIZARD

    async def _async_read(self) -> PhaseReading | None:
        return homewizard_reading(await read_homewizard(self.hass, self.address))


async def read_homewizard(hass: HomeAssistant, address: str) -> dict[str, Any]:
    """The current measurement of a HomeWizard meter (API v1)."""
    session = async_get_clientsession(hass)
    async with asyncio.timeout(3):
        response = await session.get(f"http://{address}/api/v1/data")
        response.raise_for_status()
        return await response.json(content_type=None)


def homewizard_phases(data: dict[str, Any]) -> tuple[float, ...] | None:
    """Signed power per phase (+ import / - export) from API v1 data."""
    values = [data.get(f"active_power_l{n}_w") for n in (1, 2, 3)]
    if values[0] is None:
        return None
    if values[1] is None or values[2] is None:
        return (float(values[0]),)
    return tuple(float(v) for v in values)


def homewizard_reading(data: dict[str, Any]) -> PhaseReading | None:
    """Power, and current and voltage per phase when the meter gives them
    (``active_current_l1_a``, ``active_voltage_l1_v``; a P1 meter)."""
    power = homewizard_phases(data)
    if power is None:
        return None
    count = len(power)
    numbers = range(1, count + 1)
    return PhaseReading(
        power,
        per_phase([data.get(f"active_current_l{n}_a") for n in numbers], count),
        per_phase([data.get(f"active_voltage_l{n}_v") for n in numbers], count),
    )


def find_homewizard(hass: HomeAssistant) -> list[DirectCandidate]:
    """HomeWizard grid meters known to Home Assistant (config entries);
    also as API v2 (pushed) when the integration has a v2 token."""
    devices = dr.async_get(hass)
    found: list[DirectCandidate] = []
    for entry in hass.config_entries.async_entries(SOURCE_HOMEWIZARD):
        address = entry.data.get("ip_address")
        for device in dr.async_entries_for_config_entry(devices, entry.entry_id):
            if (
                address
                and device.model_id in HOMEWIZARD_METERS
                and not device.via_device_id  # e.g. the gas meter of a P1
            ):
                name = (
                    f"HomeWizard {device.name_by_user or device.name or device.model}"
                )
                phases = HOMEWIZARD_METERS[device.model_id]
                found.append(DirectCandidate(SOURCE_HOMEWIZARD, address, name, phases))
                if entry.data.get("token"):
                    found.append(
                        DirectCandidate(
                            SOURCE_HOMEWIZARD_V2, address, f"{name} (API v2)", phases
                        )
                    )
                break
    return found
