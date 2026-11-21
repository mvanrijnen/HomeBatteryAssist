"""Actions of HomeBatteryAssist.

- ``recalculate``: recalculate the forecasts right away, e.g. from an
  automation when new prices or PV forecasts arrive.
- ``import_history``: fill the consumption history from Home Assistant's
  statistics (e.g. as starting or test data).
- ``adjust_forecast`` / ``clear_forecast_adjustments``: let users, scripts and
  other integrations influence the consumption forecast for a period.
- ``set_forecast_correction`` / ``reset_forecast_accuracy``: control how the
  consumption, PV and price forecasts are corrected from their running accuracy.
- ``exclude_consumption_days``: leave unusual days (a party, a power cut) out
  of what the consumption forecast learns, or take them back.

Both only touch HomeBatteryAssist's own data; no device is ever controlled.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
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
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.util import dt as dt_util

from .const import CONF_PLAN_MODE, DOMAIN, HISTORY_RETENTION
from .engine.evaluation.forecast_accuracy import ALL_BUCKETS, BUCKET_KEYS, KINDS, MODES
from .engine.history.history_import import async_import_history
from .engine.history.temperature_import import (
    async_import_temperatures,
    async_import_zones,
)
from .engine.planning.battery_plan import PLAN_MODES

SERVICE_RECALCULATE = "recalculate"
_LOGGER = logging.getLogger(__name__)

SERVICE_IMPORT_HISTORY = "import_history"
ATTR_DAYS = "days"
ATTR_SOURCE_ENTITY = "source_entity"
ATTR_BATTERY_POWER_HISTORY = "battery_power_history"
ATTR_REPLACE = "replace"
SERVICE_ADJUST_FORECAST = "adjust_forecast"
SERVICE_CLEAR_ADJUSTMENTS = "clear_forecast_adjustments"
ATTR_NAME = "name"
ATTR_START = "start"
ATTR_END = "end"
ATTR_DURATION = "duration"
ATTR_FACTOR = "factor"
ATTR_OFFSET = "offset_w"
ATTR_POWER = "power_w"
ATTR_ENERGY = "energy_kwh"
ATTR_PART = "part_of_forecast"
ATTR_ID = "id"
SERVICE_SET_PLAN_MODE = "set_plan_mode"
SERVICE_SET_CORRECTION = "set_forecast_correction"
SERVICE_RESET_ACCURACY = "reset_forecast_accuracy"
SERVICE_EXCLUDE_DAYS = "exclude_consumption_days"
ATTR_DATES = "dates"
ATTR_INCLUDE = "include"
ATTR_KIND = "kind"
ATTR_MODE = "mode"
ATTR_VALUE = "value"
ATTR_BUCKET = "bucket"
KIND_ALL = "all"

SET_CORRECTION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_KIND): vol.In([*KINDS, KIND_ALL]),
        vol.Required(ATTR_MODE): vol.In(MODES),
        vol.Optional(ATTR_VALUE): vol.Coerce(float),
        # "5d-plus" in the UI (translation keys cannot contain "+") is "5d+".
        vol.Optional(ATTR_BUCKET, default=ALL_BUCKETS): vol.All(
            lambda value: "5d+" if value == "5d-plus" else value,
            vol.In([ALL_BUCKETS, *BUCKET_KEYS]),
        ),
        vol.Optional(ATTR_DURATION): cv.positive_time_period,
    }
)
EXCLUDE_DAYS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DATES): vol.All(cv.ensure_list, [cv.date], vol.Length(min=1)),
        vol.Optional(ATTR_INCLUDE, default=False): cv.boolean,
    }
)
RESET_ACCURACY_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_KIND, default=KIND_ALL): vol.In([*KINDS, KIND_ALL])}
)


def _to_utc(value: datetime) -> datetime:
    """Times without a time zone are local (Home Assistant's time zone)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_util.get_default_time_zone())
    return dt_util.as_utc(value)


def describe_change(adjustment: dict[str, Any], language: str | None) -> str:
    """The change of an adjustment in a few words (for *Why*)."""
    value = adjustment["value"]
    if adjustment["kind"] == ATTR_FACTOR:
        return f"x{value:g}"
    if adjustment["kind"] == ATTR_OFFSET:
        return f"{value:+g} W"
    if adjustment["kind"] == ATTR_POWER:
        return f"= {value:g} W"
    dutch = (language or "").startswith("nl")
    amount = f"{value:g} kWh".replace(".", ",") if dutch else f"{value:g} kWh"
    if adjustment.get("part"):
        return (
            f"{amount}, deel van het verwachte verbruik van die dag"
            if dutch
            else f"{amount}, part of that day's expected consumption"
        )
    return f"+{amount}" if value >= 0 else amount


def _one_change(data: dict[str, Any]) -> dict[str, Any]:
    changes = [
        k for k in (ATTR_FACTOR, ATTR_OFFSET, ATTR_POWER, ATTR_ENERGY) if k in data
    ]
    if len(changes) != 1:
        raise vol.Invalid("give exactly one of factor, offset_w, power_w or energy_kwh")
    if data.get(ATTR_PART) and ATTR_ENERGY not in data:
        raise vol.Invalid("part_of_forecast only goes with energy_kwh")
    if (ATTR_END in data) == (ATTR_DURATION in data):
        raise vol.Invalid("give either end or duration")
    return data


ADJUST_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(ATTR_NAME): vol.All(cv.string, vol.Length(max=60)),
            vol.Optional(ATTR_START): cv.datetime,
            vol.Optional(ATTR_END): cv.datetime,
            vol.Optional(ATTR_DURATION): cv.positive_time_period,
            vol.Optional(ATTR_FACTOR): vol.All(
                vol.Coerce(float), vol.Range(min=0, max=10)
            ),
            vol.Optional(ATTR_OFFSET): vol.All(
                vol.Coerce(float), vol.Range(min=-50000, max=50000)
            ),
            vol.Optional(ATTR_POWER): vol.All(
                vol.Coerce(float), vol.Range(min=0, max=50000)
            ),
            vol.Optional(ATTR_ENERGY): vol.All(
                vol.Coerce(float), vol.Range(min=-500, max=500)
            ),
            vol.Optional(ATTR_PART, default=False): cv.boolean,
        }
    ),
    _one_change,
)
CLEAR_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ID, default=[]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_NAME, default=[]): vol.All(cv.ensure_list, [cv.string]),
    }
)

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
        forecast.explain_next = True  # by hand: show the plan in Why again
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
        # Days the user left out stay left out (also in imported records).
        history = entry.runtime_data.history
        if history.excluded_days:
            history.exclude_days([date.fromisoformat(d) for d in history.excluded_days])
            await history.async_save()  # with the excluded days marked
        # The imported records get their outdoor temperature and zones from
        # the statistics too (as at start), else the temperature effect would
        # drop out until the next restart.
        forecast = entry.runtime_data.forecast
        try:
            if forecast.outdoor_sensor:
                await async_import_temperatures(hass, history, forecast.outdoor_sensor)
            if forecast.zones:
                await async_import_zones(hass, history, forecast.zones)
        except Exception:  # the recorder may be unavailable
            _LOGGER.exception("Filling in past temperatures failed")
        entry.runtime_data.forecast.history_changed()  # learn from it at once
        await entry.runtime_data.forecast.async_request_refresh()
        entry.runtime_data.decisions.async_log(
            "history",
            "history_imported",
            count=result["imported"],
            first=dt_util.parse_datetime(result["first"]) if result["first"] else "-",
            last=dt_util.parse_datetime(result["last"]) if result["last"] else "-",
        )
        return result if call.return_response else None

    async def _adjust_forecast(call: ServiceCall) -> ServiceResponse:
        entry = _loaded_entries(hass)[0]
        start = (
            _to_utc(call.data[ATTR_START])
            if ATTR_START in call.data
            else dt_util.utcnow()
        )
        end = (
            _to_utc(call.data[ATTR_END])
            if ATTR_END in call.data
            else start + call.data[ATTR_DURATION]
        )
        if end <= start:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="end_before_start"
            )
        kind = next(
            k
            for k in (ATTR_FACTOR, ATTR_OFFSET, ATTR_POWER, ATTR_ENERGY)
            if k in call.data
        )
        forecast = entry.runtime_data.forecast
        adjustment = await forecast.adjustments.async_add(
            call.data.get(ATTR_NAME),
            start,
            end,
            kind,
            call.data[kind],
            bool(call.data.get(ATTR_PART)),
        )
        change = describe_change(adjustment, hass.config.language)
        entry.runtime_data.decisions.async_log(
            "forecast",
            "forecast_adjusted",
            name=adjustment["name"],
            change=change,
            start=start,
            end=end,
        )
        await forecast.async_refresh()
        return dict(adjustment) if call.return_response else None

    async def _clear_adjustments(call: ServiceCall) -> ServiceResponse:
        entry = _loaded_entries(hass)[0]
        forecast = entry.runtime_data.forecast
        count = await forecast.adjustments.async_clear(
            call.data[ATTR_ID], call.data[ATTR_NAME]
        )
        entry.runtime_data.decisions.async_log(
            "forecast", "forecast_adjustments_cleared", count=count
        )
        await forecast.async_refresh()
        return {"removed": count} if call.return_response else None

    async def _set_plan_mode(call: ServiceCall) -> None:
        entry = _loaded_entries(hass)[0]
        mode = call.data[ATTR_MODE]
        if mode not in PLAN_MODES and mode not in entry.runtime_data.forecast.planners:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_plan_mode",
                translation_placeholders={"mode": mode},
            )
        if entry.options.get(CONF_PLAN_MODE) == mode:
            return
        entry.runtime_data.decisions.async_log("planning", "plan_mode_set", mode=mode)
        # Stored like the other settings; the entry reloads with the new mode.
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_PLAN_MODE: mode}
        )

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_SET_PLAN_MODE,
        _set_plan_mode,
        schema=vol.Schema({vol.Required(ATTR_MODE): cv.string}),
    )

    async def _set_correction(call: ServiceCall) -> ServiceResponse:
        entry = _loaded_entries(hass)[0]
        forecast = entry.runtime_data.forecast
        mode = call.data[ATTR_MODE]
        if mode == "manual" and ATTR_VALUE not in call.data:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="manual_needs_value"
            )
        until = (
            dt_util.utcnow() + call.data[ATTR_DURATION]
            if ATTR_DURATION in call.data
            else None
        )
        kinds = KINDS if call.data[ATTR_KIND] == KIND_ALL else (call.data[ATTR_KIND],)
        value = call.data.get(ATTR_VALUE)
        if mode == "manual" and len(kinds) > 1:
            # One value cannot fit three units (W, factor, price).
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="manual_one_kind"
            )
        if mode == "manual" and kinds == ("pv",) and not 0.5 <= value <= 1.5:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="pv_factor_range"
            )
        for kind in kinds:
            forecast.accuracy.set_mode(
                kind, mode, call.data.get(ATTR_VALUE), call.data[ATTR_BUCKET], until
            )
            entry.runtime_data.decisions.async_log(
                "forecast",
                f"correction_mode_{mode}",
                kind=kind,
                value=call.data.get(ATTR_VALUE, ""),
                until="@until_set" if until else "@until_none",
                time=until or "",
            )
        await forecast.async_refresh()
        return (
            {kind: forecast.accuracy.settings[kind] for kind in kinds}
            if call.return_response
            else None
        )

    async def _reset_accuracy(call: ServiceCall) -> None:
        entry = _loaded_entries(hass)[0]
        forecast = entry.runtime_data.forecast
        kinds = KINDS if call.data[ATTR_KIND] == KIND_ALL else (call.data[ATTR_KIND],)
        for kind in kinds:
            forecast.accuracy.reset(kind)
            entry.runtime_data.decisions.async_log(
                "forecast", "accuracy_reset", kind=kind
            )
        await forecast.async_refresh()

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_SET_CORRECTION,
        _set_correction,
        schema=SET_CORRECTION_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_RESET_ACCURACY,
        _reset_accuracy,
        schema=RESET_ACCURACY_SCHEMA,
    )

    async def _exclude_days(call: ServiceCall) -> ServiceResponse:
        entry = _loaded_entries(hass)[0]
        days: list[date] = sorted(set(call.data[ATTR_DATES]))
        today = dt_util.now().date()
        oldest = today - timedelta(days=HISTORY_RETENTION.days)
        if any(d > today or d < oldest for d in days):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="days_out_of_range",
                translation_placeholders={
                    "first": oldest.isoformat(),
                    "last": today.isoformat(),
                },
            )
        include = call.data[ATTR_INCLUDE]
        history = entry.runtime_data.history
        changed = history.exclude_days(days, exclude=not include)
        await history.async_save()
        forecast = entry.runtime_data.forecast
        if not include:
            # Also what the correction already learned from those days.
            forecast.accuracy.forget_days(d.isoformat() for d in days)
        forecast.history_changed()
        entry.runtime_data.decisions.async_log(
            "history",
            "days_included" if include else "days_excluded",
            days=", ".join(d.isoformat() for d in days),
            count=changed,
        )
        await forecast.async_request_refresh()
        result = {
            "changed": changed,
            "excluded_days": sorted(history.excluded_days),
        }
        return result if call.return_response else None

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_EXCLUDE_DAYS,
        _exclude_days,
        schema=EXCLUDE_DAYS_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADJUST_FORECAST,
        _adjust_forecast,
        schema=ADJUST_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_ADJUSTMENTS,
        _clear_adjustments,
        schema=CLEAR_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RECALCULATE,
        _recalculate,
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_IMPORT_HISTORY,
        _import_history,
        schema=IMPORT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
