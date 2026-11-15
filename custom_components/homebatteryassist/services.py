"""Actions of HomeBatteryAssist.

- ``recalculate``: recalculate the forecasts right away, e.g. from an
  automation when new prices or PV forecasts arrive.
- ``import_history``: fill the consumption history from Home Assistant's
  statistics (e.g. as starting or test data).

Both only touch HomeBatteryAssist's own data; no device is ever controlled.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DOMAIN, HISTORY_RETENTION
from .history.importer import async_import_history

SERVICE_RECALCULATE = "recalculate"
SERVICE_IMPORT_HISTORY = "import_history"
ATTR_DAYS = "days"
ATTR_SOURCE_ENTITY = "source_entity"
ATTR_BATTERY_POWER_HISTORY = "battery_power_history"
ATTR_REPLACE = "replace"

IMPORT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_DAYS, default=HISTORY_RETENTION.days): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=HISTORY_RETENTION.days)
        ),
        vol.Optional(ATTR_SOURCE_ENTITY): cv.entity_id,
        vol.Optional(ATTR_BATTERY_POWER_HISTORY, default=[]): cv.entity_ids,
        vol.Optional(ATTR_REPLACE, default=False): cv.boolean,
    }
)


def _loaded_entries(hass: HomeAssistant) -> list[Any]:
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    return entries


async def async_recalculate(hass: HomeAssistant) -> dict[str, Any]:
    """Recalculate the forecasts of every loaded entry; return the result."""
    result: dict[str, Any] = {}
    for entry in _loaded_entries(hass):
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

    async def _import_history(call: ServiceCall) -> ServiceResponse:
        entry = _loaded_entries(hass)[0]
        result = await async_import_history(
            hass,
            entry,
            days=call.data[ATTR_DAYS],
            source_entity=call.data.get(ATTR_SOURCE_ENTITY),
            battery_power_history=call.data[ATTR_BATTERY_POWER_HISTORY],
            replace=call.data[ATTR_REPLACE],
        )
        entry.runtime_data.decisions.async_log(
            "history",
            "history_imported",
            count=result["imported"],
            first=dt_util.parse_datetime(result["first"]) if result["first"] else "-",
            last=dt_util.parse_datetime(result["last"]) if result["last"] else "-",
        )
        return result if call.return_response else None

    hass.services.async_register(
        DOMAIN,
        SERVICE_RECALCULATE,
        _recalculate,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_HISTORY,
        _import_history,
        schema=IMPORT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
