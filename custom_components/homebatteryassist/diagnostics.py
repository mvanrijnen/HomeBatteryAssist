"""Diagnostics download (technical): configuration and the state of each module."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .models import HomeBatteryAssistConfigEntry

RECENT_RECORDS = 12
RECENT_DECISIONS = 25


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HomeBatteryAssistConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Contains no secrets: only entity ids, config entry ids and measured values.
    """
    data = entry.runtime_data
    forecast = data.forecast.data
    return {
        "config": {
            "data": dict(entry.data),
            "options": dict(entry.options),
            "subentries": [
                {"type": s.subentry_type, "title": s.title, "data": dict(s.data)}
                for s in entry.subentries.values()
            ],
        },
        "inputs": {
            "house_consumption_w": data.measurements.power,
            "missing_grid_sensors": data.measurements.missing,
            "sources": {
                entity_id: _state(hass, entity_id)
                for entity_id in data.measurements.source_entity_ids
            },
        },
        "batteries": [
            {
                "name": state.config.name,
                "soc": state.soc,
                "power_w": state.power_w,
                "status": state.status,
                "stored_kwh": state.stored_kwh,
                "config": {
                    "capacity_kwh": state.config.capacity_kwh,
                    "max_charge_w": state.config.max_charge_w,
                    "max_discharge_w": state.config.max_discharge_w,
                    "min_soc": state.config.min_soc,
                    "max_soc": state.config.max_soc,
                },
                "stats": data.batteries.stats.get(state.config.id),
            }
            for state in data.batteries.states.values()
        ],
        "history": {
            "interval_minutes": data.history.minutes,
            "records": len(data.history.records),
            "recent": data.history.records[-RECENT_RECORDS:],
        },
        "forecasts": {
            "window_start": forecast.window.start.isoformat(),
            "window_end": forecast.window.end.isoformat(),
            "window_hours": round(forecast.window.hours, 2),
            "window_limited_by": forecast.window.limited_by.value,
            "price_points": len(forecast.prices),
            "price_unit": forecast.price_unit,
            "price_end": forecast.price_end.isoformat() if forecast.price_end else None,
            "pv_hours": len(forecast.pv_wh),
            "pv_end": forecast.pv_end.isoformat() if forecast.pv_end else None,
            "last_update_success": data.forecast.last_update_success,
        },
        "decisions": data.decisions.entries[-RECENT_DECISIONS:],
    }


def _state(hass: HomeAssistant, entity_id: str) -> dict[str, Any] | None:
    if (state := hass.states.get(entity_id)) is None:
        return None
    return {
        "state": state.state,
        "unit": state.attributes.get("unit_of_measurement"),
        "last_updated": state.last_updated.isoformat(),
    }
