"""Actions of HomeBatteryAssist.

``homebatteryassist.recalculate`` recalculates the forecasts right away, e.g.
from an automation when new prices or PV forecasts arrive. It only recalculates
HomeBatteryAssist's own forecasts; it never controls any device.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN

SERVICE_RECALCULATE = "recalculate"


async def async_recalculate(hass: HomeAssistant) -> dict[str, Any]:
    """Recalculate the forecasts of every loaded entry; return the result."""
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    result: dict[str, Any] = {}
    for entry in entries:
        forecast = entry.runtime_data.forecast
        await forecast.async_refresh()
        result = forecast.summary()
    return result


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions."""

    async def _recalculate(call: ServiceCall) -> ServiceResponse:
        result = await async_recalculate(hass)
        return result if call.return_response else None

    hass.services.async_register(
        DOMAIN,
        SERVICE_RECALCULATE,
        _recalculate,
        supports_response=SupportsResponse.OPTIONAL,
    )
