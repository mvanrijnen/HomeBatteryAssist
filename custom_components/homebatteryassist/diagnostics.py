"""Diagnostics download (technical): configuration and the state of each module."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .engine.evaluation.pv_corrections import BUILTIN as PV_CORRECTORS
from .models import HomeBatteryAssistConfigEntry

RECENT_RECORDS = 12
# Left out of the download (it is often attached to public issues).
TO_REDACT = {
    "weather_api_key",
    "weather_location",
    "meter_address",
    "pv_address",
    "inverter_address",
    "battery_meter_address",
    "notify_targets",
}
RECENT_DECISIONS = 25


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HomeBatteryAssistConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Secrets, addresses and the location are redacted (``TO_REDACT``).
    """
    data = entry.runtime_data
    forecast = data.forecast.data
    return {
        "config": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
            "subentries": [
                {
                    "type": s.subentry_type,
                    "title": s.title,
                    "data": async_redact_data(dict(s.data), TO_REDACT),
                }
                for s in entry.subentries.values()
            ],
        },
        "inputs": {
            "house_consumption_w": data.measurements.power,
            "missing_grid_sensors": data.measurements.missing,
            "meter": (
                data.measurements.direct.diagnostics()
                if data.measurements.direct
                else data.measurements.source
            ),
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
                # The command it has now and whether it follows it.
                "command": (
                    data.commands.state(state.config.id) if data.commands else None
                ),
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
            "plans": {
                mode: {"strategy": plan.strategy, "saving": plan.saving}
                for mode, plan in forecast.plans.items()
            },
        },
        "modules": {
            "planner": data.forecast.plan_mode,
            "planner_fallback": data.forecast.plan_fallback,
            # How long the last forecast cycle took per step (ms).
            "cycle_timings_ms": data.forecast.timings,
            # Today so far vs forecast: the shift for the rest of today.
            # After the window: what values the energy left at the end.
            "outlook": (
                {
                    "night_kwh": round(data.forecast.outlook.night_wh / 1000, 2),
                    "surplus_kwh": round(data.forecast.outlook.surplus_wh / 1000, 2),
                }
                if data.forecast.outlook
                else None
            ),
            "intraday_correction": (
                data.forecast.intraday.as_dict() if data.forecast.intraday else None
            ),
            "consumption_forecaster": data.forecast.forecaster_key,
            "forecaster_fallback": data.forecast.forecaster_fallback,
            "weather_source": data.forecast.weather_key,
            "weather": _weather(data.forecast.weather),
            "outdoor_temperature": data.forecast.outdoor_temperature(),
            "temperature_model": (
                [
                    {
                        "zone": model.name or None,
                        "target": model.target,
                        "heat_w_per_deg": model.heat_w_per_deg,
                        "cool_w_per_deg": model.cool_w_per_deg,
                        "days": model.days,
                        "gain_c": model.gain_c,
                        "heating_point_c": model.heating_point,
                        "room_day_c": model.room_temperature(day=True)
                        if model.usual_indoor
                        else None,
                        "room_night_c": model.room_temperature(day=False)
                        if model.usual_indoor
                        else None,
                        "room_day_per_weekday_c": [
                            model.room_temperature(day=True, weekday=d)
                            for d in range(7)
                        ]
                        if model.usual_indoor
                        else None,
                    }
                    for model in data.forecast.temperature_model.models
                ]
                if data.forecast.temperature_model
                else None
            ),
            "heating_zones": [
                {
                    "name": zone.name,
                    "indoor_sensor": zone.indoor_sensor,
                    "outdoor_sensor": zone.outdoor_sensor,
                }
                for zone in data.forecast.zones
            ],
            "temperature_forecast_slots": sum(
                t is not None for t in data.forecast.temperatures or []
            ),
            "interceptor": (
                data.forecast.interceptor.key if data.forecast.interceptor else None
            ),
            "interceptor_changes": data.simulator.intercepted,
            "control_quality": data.simulator.quality.summary(dt_util.utcnow()),
            "pv_corrector": data.forecast.pv_corrector_key,
            "pv_corrector_fallback": data.forecast.pv_corrector_fallback,
            "pv_corrector_learned": _pv_details(data.forecast),
            "spike_filter": _spike_details(data),
            "tariff": data.forecast.tariff_key,
            "tariff_fallback": data.forecast.tariff_fallback,
            "own": {
                "planners": sorted(data.forecast.planners),
                "forecasters": sorted(data.forecast.forecasters),
                "tariffs": sorted(data.forecast.tariffs),
                "pv_forecasts": sorted(data.forecast.pv_sources),
            },
            "forecaster_accuracy": data.forecast.accuracy.forecasters(),
        },
        "accuracy": {
            kind: {
                "settings": data.forecast.accuracy.settings[kind],
                "lead_times": data.forecast.accuracy.summary(kind),
                "pending_predictions": len(data.forecast.accuracy.predictions[kind]),
            }
            for kind in ("consumption", "pv", "price")
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


def _pv_details(forecast: Any) -> dict[str, Any] | None:
    """What the chosen PV correction learned (if it tells)."""
    key = forecast.pv_corrector_key
    corrector = forecast.pv_correctors.get(key) or PV_CORRECTORS.get(key)
    if corrector is None:
        return None
    try:
        return corrector.details()
    except Exception:  # an own module may fail in any way
        return None


def _spike_details(data: Any) -> dict[str, Any] | None:
    """The spike filter: which one, its settings, what it saw."""
    spike_filter = data.measurements.spike_filter
    if spike_filter is None:
        return None
    try:
        seen = spike_filter.details()
    except Exception:  # an own module may fail in any way
        seen = None
    return {
        "key": spike_filter.key,
        "threshold_w": spike_filter.threshold_w,
        "max_duration_s": spike_filter.max_duration_s,
        "exclude_from_average": data.forecast.spike_history,
        "no_discharge": data.forecast.spike_battery,
        "regular_peak_hours": sorted(data.forecast.regular_peaks),
        "seen": seen,
    }


def _weather(source: Any) -> str | None:
    """The weather source and its state, without the place the user set
    (``weather_location`` is redacted)."""
    if source is None:
        return None
    text = source.describe()
    settings = getattr(source, "settings", None)
    location = getattr(settings, "location", None)
    return text.replace(str(location), REDACTED) if location else text
