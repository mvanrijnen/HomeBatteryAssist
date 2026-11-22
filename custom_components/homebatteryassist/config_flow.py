"""Config flow for HomeBatteryAssist.

Steps:
0. meter:      only if a known grid meter is found (``inputs.meters``, e.g. a
               HomeWizard P1): pick it to fill in phases and sensors, or choose
               them manually (steps 1 and 3)
1. user:       1-phase or 3-phase grid connection
2. max_current: connection size, i.e. fuse rating per phase (1x35A, 3x25A, ...)
3. sensors:    per phase a power (W) or current (A) sensor: signed (+ import,
               - export) or import-only with an optional separate return sensor
4. settings:   consumption history interval, planning horizon and the price / PV
               forecast inputs (all changeable later in the options flow)

Grid settings live in ``entry.data``; settings that can be changed later live in
``entry.options``.

Subentries (added/changed afterwards under the integration, any number of each):
- pv_source:     a PV production measurement
- excluded_load: a device kept out of house consumption (e.g. an EV charger)
  Both have a name, a power/current sensor and, on 3-phase connections, an
  optional phase.
- battery:       a home battery, linked read-only through entities of its own
  integration. Step "user" offers batteries found in known integrations
  (``inputs.profiles``) with all values prefilled, or manual linking; step
  "battery" holds the sensors and properties. Batteries are never controlled.

A sensor can only be used once: as grid sensor or by one subentry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, ClassVar

import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)

from .const import (
    BALANCE_INTERVAL_OPTIONS,
    BATTERY_METER_NONE,
    BATTERY_SENSOR_KEYS,
    CHARGE_ORDER_OPTIONS,
    CHARGE_SEQUENTIAL,
    CONF_BALANCE_INTERVAL,
    CONF_BATTERY_METER,
    CONF_BATTERY_METER_ADDRESS,
    CONF_CAPACITY,
    CONF_CHARGE_HYSTERESIS,
    CONF_CHARGE_ORDER,
    CONF_COMMAND_CHECK_MINUTES,
    CONF_COMMAND_CHECK_W,
    CONF_CONSUMPTION_FORECASTER,
    CONF_CYCLE_COST,
    CONF_DEVICE_PHASE_SENSORS,
    CONF_EFFICIENCY,
    CONF_ESTIMATED_MARGIN,
    CONF_EXPORT_ENTITIES,
    CONF_EXPORT_FACTOR,
    CONF_EXPORT_LIMIT,
    CONF_EXPORT_LIMIT_COST,
    CONF_EXPORT_LIMIT_MAX_W,
    CONF_EXPORT_LIMIT_PRICE,
    CONF_EXPORT_MODE,
    CONF_EXPORT_NEVER,
    CONF_FORECAST_INTERVAL,
    CONF_FULL_CHARGE_DAY,
    CONF_FULL_CHARGE_INTERVAL,
    CONF_FULL_CHARGE_SOLAR,
    CONF_FULL_CHARGE_WINDOW,
    CONF_HISTORY_INTERVAL,
    CONF_INDOOR_TEMPERATURE,
    CONF_INITIAL_SOC,
    CONF_INTERCEPTOR,
    CONF_INTRADAY,
    CONF_INVERTER_ADDRESS,
    CONF_INVERTER_DRIVER,
    CONF_INVERTER_MAX_CURRENT,
    CONF_LOSS_MAX,
    CONF_LOSS_MIN,
    CONF_MANUAL_POWER,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_CHARGE_PRICE,
    CONF_MAX_CURRENT,
    CONF_MAX_CYCLES,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_SOC,
    CONF_METER_ADDRESS,
    CONF_METER_SOURCE,
    CONF_MIN_BATTERY_POWER,
    CONF_MIN_DISCHARGE_PRICE,
    CONF_MIN_MARGIN,
    CONF_MIN_SOC,
    CONF_NIGHT_RESERVE_SOC,
    CONF_NOM_CONTROL,
    CONF_NOM_TARGET,
    CONF_NOTIFY_KINDS,
    CONF_NOTIFY_TARGETS,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_PD_HYSTERESIS,
    CONF_PD_KD,
    CONF_PD_KP,
    CONF_PD_MAX_STEP,
    CONF_PEAK_INCLUDE_EXCLUDED,
    CONF_PEAK_LIMIT,
    CONF_PEAK_RESERVE_SOC,
    CONF_PHASE,
    CONF_PHASE_CURRENT_SENSORS,
    CONF_PHASE_MARGIN,
    CONF_PHASE_RETURN_SENSORS,
    CONF_PHASE_SENSORS,
    CONF_PHASE_VOLTAGE_SENSORS,
    CONF_PHASES,
    CONF_PLAN_MODE,
    CONF_PLANNING_HORIZON,
    CONF_POWER_SENSOR,
    CONF_POWER_SIGN,
    CONF_PRICE_EXTENSION,
    CONF_PRICE_FORECAST,
    CONF_PRICE_SOURCE,
    CONF_PV_ADDRESS,
    CONF_PV_CORRECTION,
    CONF_PV_CORRECTOR,
    CONF_PV_DEVIATION_MINUTES,
    CONF_PV_DEVIATION_W,
    CONF_PV_DRIVER,
    CONF_PV_FORECAST,
    CONF_PV_MARGIN,
    CONF_PV_POSSIBLE_SENSOR,
    CONF_REACT_AVERAGE,
    CONF_REACT_INTERVAL,
    CONF_REACT_JUMP,
    CONF_REACT_JUMP_W,
    CONF_RESERVE_SOC,
    CONF_SENSOR,
    CONF_SIM_DELAY,
    CONF_SIM_RAMP,
    CONF_SOC_SENSOR,
    CONF_SOURCE,
    CONF_SPIKE_BATTERY,
    CONF_SPIKE_DURATION,
    CONF_SPIKE_FILTER,
    CONF_SPIKE_HISTORY,
    CONF_SPIKE_THRESHOLD,
    CONF_STORAGE_BACKEND,
    CONF_STORAGE_URL,
    CONF_SYSTEM_MAX_CHARGE,
    CONF_SYSTEM_MAX_DISCHARGE,
    CONF_TARIFF,
    CONF_TARIFF_ENERGY_TAX,
    CONF_TARIFF_SURCHARGE,
    CONF_TARIFF_VAT,
    CONF_TEMP_BAND,
    CONF_TEMP_DISCHARGE,
    CONF_TEMP_LIMIT,
    CONF_TEMP_MIN_POWER,
    CONF_TEMPERATURE_SENSOR,
    CONF_TWIN_OF,
    CONF_VACATION,
    CONF_WEATHER_API_KEY,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_LOCATION,
    CONF_WEATHER_SOURCE,
    DEFAULT_BALANCE_INTERVAL,
    DEFAULT_COMMAND_CHECK_MINUTES,
    DEFAULT_COMMAND_CHECK_W,
    DEFAULT_CYCLE_COST,
    DEFAULT_EFFICIENCY,
    DEFAULT_ESTIMATED_MARGIN,
    DEFAULT_EXPORT_FACTOR,
    DEFAULT_EXPORT_LIMIT,
    DEFAULT_EXPORT_LIMIT_COST,
    DEFAULT_EXPORT_LIMIT_MAX_W,
    DEFAULT_EXPORT_LIMIT_PRICE,
    DEFAULT_EXPORT_MODE,
    DEFAULT_EXPORT_NEVER,
    DEFAULT_FORECAST_INTERVAL,
    DEFAULT_FULL_CHARGE_INTERVAL,
    DEFAULT_FULL_CHARGE_WINDOW,
    DEFAULT_HISTORY_INTERVAL,
    DEFAULT_INITIAL_SOC,
    DEFAULT_LOSS_MAX,
    DEFAULT_LOSS_MIN,
    DEFAULT_MANUAL_POWER,
    DEFAULT_MAX_CURRENT,
    DEFAULT_MAX_CYCLES,
    DEFAULT_MAX_SOC,
    DEFAULT_MIN_BATTERY_POWER,
    DEFAULT_MIN_SOC,
    DEFAULT_PEAK_LIMIT,
    DEFAULT_PHASE_MARGIN,
    DEFAULT_PLANNING_HORIZON,
    DEFAULT_PV_DEVIATION_MINUTES,
    DEFAULT_PV_DEVIATION_W,
    DEFAULT_PV_MARGIN,
    DEFAULT_REACT_INTERVAL,
    DEFAULT_REACT_JUMP_W,
    DEFAULT_SPIKE_DURATION,
    DEFAULT_SPIKE_THRESHOLD,
    DEFAULT_TARIFF_VAT,
    DOMAIN,
    EXPORT_MODES,
    FORECAST_INTERVAL_OPTIONS,
    HEAVY_CONNECTION_A,
    HISTORY_INTERVAL_OPTIONS,
    INVERTER_NONE,
    MAX_CURRENT_OPTIONS,
    MAX_PLANNING_HORIZON,
    MIN_PLANNING_HORIZON,
    NAME,
    PHASE_IDS,
    PHASE_NONE,
    PHASE_OPTIONS,
    PRICE_EXTENSION_NONE,
    PRICE_SOURCE_SENSOR,
    PRICES_CHECKED,
    PV_CORRECTION_BOTH,
    PV_CORRECTION_MODES,
    PV_DRIVER_SENSOR,
    SIGN_CHARGING_POSITIVE,
    SIGN_DISCHARGING_POSITIVE,
    SOURCE_MANUAL,
    SUBENTRY_BATTERY,
    SUBENTRY_EXCLUDED_LOAD,
    SUBENTRY_HEATING_COOLING,
    SUBENTRY_PV_SOURCE,
    SUBENTRY_TIME_SLOT,
    SUBENTRY_VIRTUAL_BATTERY,
    TWIN_NONE,
    phase_return_sensor_keys,
    phase_sensor_keys,
)
from .engine.control.interceptors import BUILTIN as INTERCEPTORS
from .engine.control.interceptors import (
    DEFAULT_INTERCEPTOR,
    async_load_user_interceptors,
)
from .engine.control.pd_controller import (
    CONTROL_DIRECT,
    CONTROLS,
    DEFAULT_HYSTERESIS_W,
    DEFAULT_KD,
    DEFAULT_KP,
    DEFAULT_MAX_STEP_W,
)
from .engine.db_store import (
    BACKEND_JSON,
    BACKENDS,
    SERVER_BACKENDS,
    async_check_database,
    database_url,
)
from .engine.devices.batteries.recognition import (
    BatteryCandidate,
    find_battery_candidates,
)
from .engine.devices.inverters import DRIVERS as INVERTER_DRIVERS
from .engine.devices.meters import DRIVERS as METER_DRIVERS
from .engine.devices.meters import get_driver as get_meter_driver
from .engine.devices.meters.discovery import (
    DIRECT_SOURCES,
    SOURCE_HOMEWIZARD,
    SOURCE_HOMEWIZARD_V2,
    SOURCE_NAMES,
    SOURCE_SPEEDWIRE,
    DirectCandidate,
    discover_speedwire,
    find_direct_meters,
)
from .engine.devices.meters.via_ha_integration import (
    MeterCandidate,
    find_meter_candidates,
)
from .engine.evaluation.pv_corrections import BUILTIN as PV_CORRECTORS
from .engine.evaluation.pv_corrections import (
    DEFAULT_PV_CORRECTOR,
    async_load_user_pv_correctors,
)
from .engine.explain.notifications import KINDS as NOTIFY_KINDS
from .engine.explain.notifications import PERSISTENT
from .engine.forecast.forecasters import BUILTIN as FORECASTERS
from .engine.forecast.forecasters import (
    DEFAULT_FORECASTER,
    async_load_user_forecasters,
)
from .engine.measure.spike_filters import BUILTIN as SPIKE_FILTERS
from .engine.measure.spike_filters import (
    DEFAULT_SPIKE_FILTER,
    async_load_user_spike_filters,
)
from .engine.planning.battery_plan import DEFAULT_PLAN_MODE, PLAN_MODES
from .engine.planning.planners import async_load_user_planners
from .engine.planning.time_slots import ACTION_CHARGE, ACTIONS, WEEKDAYS
from .engine.sources.prices import find_sources, get_driver
from .engine.sources.pv_forecasts import (
    async_find_pv_forecasts,
    async_load_user_pv_sources,
)
from .engine.sources.tariffs import BUILTIN as TARIFFS
from .engine.sources.tariffs import DEFAULT_TARIFF, async_load_user_tariffs
from .engine.sources.weather import BUILTIN as WEATHER_SOURCES
from .engine.sources.weather import (
    DEFAULT_WEATHER_SOURCE,
    async_load_user_weather_sources,
)

PHASES_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PHASES, default="3"): SelectSelector(
            SelectSelectorConfig(
                options=[str(p) for p in PHASE_OPTIONS],
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_PHASES,
            )
        )
    }
)


def max_current_schema(phases: int) -> vol.Schema:
    """Build the connection-size step schema (e.g. 3x25A) for the phase count."""
    return vol.Schema(
        {
            vol.Required(
                CONF_MAX_CURRENT, default=str(DEFAULT_MAX_CURRENT[phases])
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=str(amps), label=f"{phases}x{amps}A")
                        for amps in MAX_CURRENT_OPTIONS[phases]
                    ],
                    mode=SelectSelectorMode.LIST,
                )
            )
        }
    )


PHASE_SENSOR_SELECTOR = EntitySelector(
    EntitySelectorConfig(
        domain="sensor",
        device_class=[SensorDeviceClass.POWER, SensorDeviceClass.CURRENT],
    )
)


CURRENT_SENSOR_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.CURRENT)
)
# The grid per phase: power only. A current sensor has no sign (import and
# export look the same), so export would count as import; current goes in
# the optional current fields (phase protection).
GRID_POWER_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER)
)
VOLTAGE_SENSOR_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.VOLTAGE)
)


def sensors_schema(phases: int) -> vol.Schema:
    """Build the sensor step schema for the given number of phases: power
    (and return) per phase, then optional current and voltage per phase."""
    schema: dict[Any, Any] = {}
    for key, return_key in zip(
        phase_sensor_keys(phases), phase_return_sensor_keys(phases), strict=True
    ):
        schema[vol.Required(key)] = GRID_POWER_SELECTOR
        schema[vol.Optional(return_key)] = GRID_POWER_SELECTOR
    for key in CONF_PHASE_CURRENT_SENSORS[:phases]:
        schema[vol.Optional(key)] = CURRENT_SENSOR_SELECTOR
    for key in CONF_PHASE_VOLTAGE_SENSORS[:phases]:
        schema[vol.Optional(key)] = VOLTAGE_SENSOR_SELECTOR
    return vol.Schema(schema)


def grid_sensors(data: Mapping[str, Any]) -> set[str]:
    """Return all grid sensors (import and return) configured in ``data``."""
    keys = (*phase_sensor_keys(3), *phase_return_sensor_keys(3))
    return {data[key] for key in keys if data.get(key)}


SUBENTRY_SENSOR_KEYS = (CONF_SENSOR, *CONF_DEVICE_PHASE_SENSORS, *BATTERY_SENSOR_KEYS)


def sensor_conflict(
    entry: ConfigEntry, sensor: str, current: ConfigSubentry | None
) -> str | None:
    """Return an error if ``sensor`` is already used by the grid or a subentry."""
    if sensor in grid_sensors(entry.data):
        return "sensor_is_phase_sensor"
    for subentry in entry.subentries.values():
        if current is not None and subentry.subentry_id == current.subentry_id:
            continue
        if sensor in (subentry.data.get(key) for key in SUBENTRY_SENSOR_KEYS):
            return "sensor_in_use"
    return None


def phase_selector() -> SelectSelector:
    """Optional phase of a device (3-phase connections only)."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[PHASE_NONE, *PHASE_IDS],
            mode=SelectSelectorMode.DROPDOWN,
            translation_key=CONF_PHASE,
        )
    )


def untested(verified: bool, dutch: bool) -> str:
    """The suffix for a driver or module not tested on a real setup yet
    (also own ones, until they set ``verified = True``)."""
    if verified:
        return ""
    return " (niet getest)" if dutch else " (not tested)"


def _own_label(module: Any, key: str, dutch: bool) -> str:
    """Label of an own module: its name, and "not tested" until it says so."""
    return f"{module.name or key}{untested(getattr(module, 'verified', False), dutch)}"


def _price_source_selector(
    hass: HomeAssistant,
    first: str,
    key: str,
    *,
    forecasts: bool = True,
    keep: str | None = None,
) -> SelectSelector:
    """The price sources found by the price drivers, after ``first``.

    Forecast-only sources are only offered as extra forecast (``forecasts``).
    """
    dutch = (hass.config.language or "").startswith("nl")
    only = " (alleen voorspelling)" if dutch else " (forecast only)"
    options = [SelectOptionDict(value=first, label=first)]
    for source in find_sources(hass):
        if source.forecast_only and not forecasts:
            continue
        driver = get_driver(source.driver)
        mark = untested(driver is not None and driver.verified, dutch)
        suffix = only if source.forecast_only else ""
        options.append(
            SelectOptionDict(value=source.key, label=f"{source.title}{suffix}{mark}")
        )
    if keep and keep not in {o["value"] for o in options}:
        # The chosen source is not available right now (e.g. its integration is
        # starting): keep it, so saving other settings does not drop it.
        options.append(SelectOptionDict(value=keep, label=keep))
    return SelectSelector(
        SelectSelectorConfig(
            options=options, mode=SelectSelectorMode.DROPDOWN, translation_key=key
        )
    )


# Settings grouped in collapsible sections; the rest stays at the top.
SETTINGS_SECTIONS: dict[str, tuple[str, ...]] = {
    "tariff_costs": ("tariff_surcharge", "tariff_energy_tax", "tariff_vat"),
    "export": ("export_price_mode", "export_price_entities", "export_price_factor"),
    "solar": (
        "pv_correction",
        "pv_corrector",
        "pv_forecast_margin",
        "pv_deviation_w",
        "pv_deviation_minutes",
    ),
    "planning": (
        "cycle_cost",
        "max_cycles_per_day",
        "min_arbitrage_margin",
        "estimated_price_margin",
        "min_discharge_price",
        "max_charge_price",
        "nom_target_w",
        "manual_power_w",
        "charge_hysteresis",
        "vacation",
        "intraday_correction",
        "interceptor",
    ),
    "limits": (
        "reserve_soc",
        "night_reserve_soc",
        "system_max_charge_w",
        "system_max_discharge_w",
        "min_battery_power",
        "charge_order",
        "balance_interval",
        "peak_limit_w",
        "peak_include_excluded",
        "peak_reserve_soc",
        "phase_margin",
    ),
    "spikes": (
        "spike_no_discharge",
        "spike_exclude_average",
        "spike_threshold_w",
        "spike_max_minutes",
        "spike_filter",
    ),
    "reaction": (
        "react_interval_s",
        "react_average",
        "react_jump",
        "react_jump_w",
        "nom_control",
        "pd_kp",
        "pd_kd",
        "pd_max_step_w",
        "pd_hysteresis_w",
        "sim_delay_s",
        "sim_ramp_w_s",
    ),
    "command_check": ("command_check_w", "command_check_minutes"),
    "export_limit": (
        "export_never",
        "export_limit_on",
        "export_limit_cost",
        "export_limit_price",
        "export_limit_max_w",
    ),
    "full_charge": ("full_charge_window_days", "full_charge_day", "full_charge_solar"),
    "notifications": ("notify_targets", "notify_kinds"),
    "weather": (
        "weather_source",
        "weather_entity",
        "weather_api_key",
        "weather_location",
        "outdoor_temperature_sensor",
    ),
    "storage": ("storage_backend", "storage_url"),
    "temperature": (
        "temperature_limit",
        "temperature_band",
        "temperature_min_power",
        "temperature_discharge",
    ),
}


async def settings_schema(
    hass: HomeAssistant,
    current: Mapping[str, Any] | None = None,
    values: Mapping[str, Any] | None = None,
) -> vol.Schema:
    """The settings form: main fields on top, the rest in collapsed sections.

    ``values``: the form's nested values (``settings_form_values``); each
    section gets its part as default, because the frontend shows a section
    from its default (an empty one would show every field in it empty).
    """
    flat = _keep_stored_choices(await _flat_settings_schema(hass, current), current)
    top: dict[Any, Any] = {}
    grouped: dict[str, dict[Any, Any]] = {name: {} for name in SETTINGS_SECTIONS}
    where = {key: name for name, keys in SETTINGS_SECTIONS.items() for key in keys}
    for marker, validator in flat.schema.items():
        name = where.get(str(marker))
        (grouped[name] if name else top)[marker] = validator
    for name, fields in grouped.items():
        if fields:
            shown = (values or {}).get(name) or _section_values(fields)
            top[vol.Required(name, default=dict(shown))] = section(
                vol.Schema(fields), {"collapsed": True}
            )
    return vol.Schema(top)


def _keep_stored_choices(
    schema: vol.Schema, current: Mapping[str, Any] | None
) -> vol.Schema:
    """A stored choice that is not offered now (an own module that failed to
    load or was removed, a notify service that is gone) stays a valid
    option: else saving any other setting fails on it."""
    for marker, validator in schema.schema.items():
        if not isinstance(validator, SelectSelector):
            continue
        stored = (current or {}).get(str(marker))
        values = stored if isinstance(stored, list) else [stored]
        config = validator.config
        options = list(config.get("options") or [])
        offered = {o["value"] if isinstance(o, dict) else o for o in options}
        missing = [v for v in values if isinstance(v, str) and v and v not in offered]
        if not missing:
            continue
        # Plain strings stay plain strings (a list may not mix both).
        if options and all(isinstance(o, str) for o in options):
            options += missing
        else:
            options += [SelectOptionDict(value=v, label=v) for v in missing]
        schema.schema[marker] = SelectSelector(
            SelectSelectorConfig(**{**config, "options": options})
        )
    return schema


def _section_values(fields: Mapping[Any, Any]) -> dict[str, Any]:
    """The values a section's fields start with: the suggested value, else
    the default."""
    values: dict[str, Any] = {}
    for marker in fields:
        description = getattr(marker, "description", None) or {}
        if "suggested_value" in description:
            values[str(marker)] = description["suggested_value"]
        elif marker.default is not vol.UNDEFINED:
            values[str(marker)] = marker.default()
    return {k: v for k, v in values.items() if v is not None}


# Kept when going back to the defaults: where the inputs come from.
KEEP_ON_RESET = (
    CONF_STORAGE_BACKEND,
    CONF_STORAGE_URL,
    CONF_NOTIFY_TARGETS,
    CONF_NOTIFY_KINDS,
    CONF_PRICE_SOURCE,
    CONF_PRICE_EXTENSION,
    CONF_PRICE_FORECAST,
    CONF_PV_FORECAST,
    CONF_EXPORT_ENTITIES,
    CONF_WEATHER_SOURCE,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_API_KEY,
    CONF_WEATHER_LOCATION,
    CONF_OUTDOOR_TEMPERATURE,
)


async def settings_defaults(hass: HomeAssistant) -> dict[str, Any]:
    """The default of every setting that has one."""
    flat = await _flat_settings_schema(hass, {})
    return {
        str(marker): marker.default()
        for marker in flat.schema
        if marker.default is not vol.UNDEFINED
    }


async def settings_form_values(
    hass: HomeAssistant, current: Mapping[str, Any]
) -> dict[str, Any]:
    """Values shown in the form: the defaults, overridden by the current ones.

    Select fields hold strings; stored options may be numbers.
    """
    values = {**await settings_defaults(hass), **current}
    return nest_settings(
        {
            key: str(value) if key in SELECT_OPTIONS and value is not None else value
            for key, value in values.items()
        }
    )


def nest_settings(values: Mapping[str, Any]) -> dict[str, Any]:
    """Flat options -> the form's nested values (for suggested values)."""
    where = {key: name for name, keys in SETTINGS_SECTIONS.items() for key in keys}
    nested: dict[str, Any] = {name: {} for name in SETTINGS_SECTIONS}
    for key, value in values.items():
        if key in where:
            nested[where[key]][key] = value
        else:
            nested[key] = value
    return nested


def flatten_settings(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """The form's nested input -> flat."""
    flat: dict[str, Any] = {}
    for key, value in user_input.items():
        if key in SETTINGS_SECTIONS and isinstance(value, Mapping):
            flat.update(value)
        else:
            flat[key] = value
    return flat


async def _flat_settings_schema(
    hass: HomeAssistant, current: Mapping[str, Any] | None = None
) -> vol.Schema:
    """All settings fields (setup step 4 and options), not grouped."""
    current = current or {}
    own_planners = await async_load_user_planners(hass)
    dutch = (hass.config.language or "").startswith("nl")
    schema: dict[Any, Any] = {
        vol.Required(
            CONF_HISTORY_INTERVAL,
            default=str(current.get(CONF_HISTORY_INTERVAL, DEFAULT_HISTORY_INTERVAL)),
        ): SelectSelector(
            SelectSelectorConfig(
                options=[str(m) for m in HISTORY_INTERVAL_OPTIONS],
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_HISTORY_INTERVAL,
            )
        ),
        vol.Required(
            CONF_PLANNING_HORIZON,
            default=current.get(CONF_PLANNING_HORIZON, DEFAULT_PLANNING_HORIZON),
        ): NumberSelector(
            NumberSelectorConfig(
                min=MIN_PLANNING_HORIZON,
                max=MAX_PLANNING_HORIZON,
                step=1,
                mode=NumberSelectorMode.SLIDER,
                unit_of_measurement="d",
            )
        ),
        vol.Required(
            CONF_FORECAST_INTERVAL,
            default=str(current.get(CONF_FORECAST_INTERVAL, DEFAULT_FORECAST_INTERVAL)),
        ): SelectSelector(
            SelectSelectorConfig(
                options=[str(m) for m in FORECAST_INTERVAL_OPTIONS],
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_FORECAST_INTERVAL,
            )
        ),
        vol.Required(
            CONF_PRICE_SOURCE,
            default=current.get(CONF_PRICE_SOURCE, PRICE_SOURCE_SENSOR),
        ): _price_source_selector(
            hass,
            PRICE_SOURCE_SENSOR,
            CONF_PRICE_SOURCE,
            forecasts=False,
            keep=current.get(CONF_PRICE_SOURCE),
        ),
        vol.Required(
            CONF_PRICE_EXTENSION,
            default=current.get(CONF_PRICE_EXTENSION, PRICE_EXTENSION_NONE),
        ): _price_source_selector(
            hass,
            PRICE_EXTENSION_NONE,
            CONF_PRICE_EXTENSION,
            keep=current.get(CONF_PRICE_EXTENSION),
        ),
        vol.Optional(CONF_PRICE_FORECAST): EntitySelector(
            EntitySelectorConfig(domain="sensor")
        ),
        vol.Required(
            CONF_WEATHER_SOURCE,
            default=current.get(CONF_WEATHER_SOURCE, DEFAULT_WEATHER_SOURCE),
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    *(SelectOptionDict(value=k, label=k) for k in WEATHER_SOURCES),
                    *(
                        SelectOptionDict(value=k, label=_own_label(c, k, dutch))
                        for k, c in (
                            await async_load_user_weather_sources(hass)
                        ).items()
                    ),
                ],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_WEATHER_SOURCE,
            )
        ),
        vol.Optional(CONF_WEATHER_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="weather")
        ),
        vol.Optional(CONF_WEATHER_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_WEATHER_LOCATION): TextSelector(),
        vol.Optional(CONF_OUTDOOR_TEMPERATURE): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class="temperature")
        ),
        vol.Required(
            CONF_PLAN_MODE, default=current.get(CONF_PLAN_MODE, DEFAULT_PLAN_MODE)
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    *(SelectOptionDict(value=m, label=m) for m in PLAN_MODES),
                    *(
                        SelectOptionDict(value=key, label=_own_label(p, key, dutch))
                        for key, p in own_planners.items()
                    ),
                ],
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_PLAN_MODE,
            )
        ),
        vol.Required(
            CONF_CONSUMPTION_FORECASTER,
            default=current.get(CONF_CONSUMPTION_FORECASTER, DEFAULT_FORECASTER),
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    *(SelectOptionDict(value=k, label=k) for k in FORECASTERS),
                    *(
                        SelectOptionDict(value=k, label=_own_label(f, k, dutch))
                        for k, f in (await async_load_user_forecasters(hass)).items()
                    ),
                ],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_CONSUMPTION_FORECASTER,
            )
        ),
        vol.Required(
            CONF_TARIFF, default=current.get(CONF_TARIFF, DEFAULT_TARIFF)
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    *(SelectOptionDict(value=k, label=k) for k in TARIFFS),
                    *(
                        SelectOptionDict(value=k, label=_own_label(t, k, dutch))
                        for k, t in (await async_load_user_tariffs(hass)).items()
                    ),
                ],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_TARIFF,
            )
        ),
        vol.Required(
            CONF_TARIFF_SURCHARGE, default=current.get(CONF_TARIFF_SURCHARGE, 0.0)
        ): _price_number(),
        vol.Required(
            CONF_TARIFF_ENERGY_TAX, default=current.get(CONF_TARIFF_ENERGY_TAX, 0.0)
        ): _price_number(),
        vol.Required(
            CONF_TARIFF_VAT, default=current.get(CONF_TARIFF_VAT, DEFAULT_TARIFF_VAT)
        ): _number(0, 50, 0.1, "%"),
        vol.Required(
            CONF_MANUAL_POWER,
            default=current.get(CONF_MANUAL_POWER, DEFAULT_MANUAL_POWER),
        ): _number(-20000, 20000, 50, "W"),
        vol.Required(
            CONF_RESERVE_SOC, default=current.get(CONF_RESERVE_SOC, 0)
        ): _number(0, 100, 1, "%", slider=True),
        vol.Required(
            CONF_NIGHT_RESERVE_SOC, default=current.get(CONF_NIGHT_RESERVE_SOC, 0)
        ): _number(0, 100, 1, "%", slider=True),
        vol.Required(
            CONF_PEAK_RESERVE_SOC, default=current.get(CONF_PEAK_RESERVE_SOC, 0)
        ): _number(0, 100, 1, "%", slider=True),
        vol.Required(
            CONF_SYSTEM_MAX_CHARGE, default=current.get(CONF_SYSTEM_MAX_CHARGE, 0)
        ): _number(0, 100000, 100, "W"),
        vol.Required(
            CONF_SYSTEM_MAX_DISCHARGE,
            default=current.get(CONF_SYSTEM_MAX_DISCHARGE, 0),
        ): _number(0, 100000, 100, "W"),
        vol.Required(CONF_NOM_TARGET, default=current.get(CONF_NOM_TARGET, 0)): _number(
            -2000, 2000, 10, "W"
        ),
        # Prices per kWh in Home Assistant's currency: wide bounds (CZK, SEK,
        # JPY amounts are much larger than euros).
        vol.Optional(CONF_MIN_DISCHARGE_PRICE): _number(
            -PRICE_MAX, PRICE_MAX, 0.001, ""
        ),
        vol.Optional(CONF_MAX_CHARGE_PRICE): _number(-PRICE_MAX, PRICE_MAX, 0.001, ""),
        vol.Required(CONF_MIN_MARGIN, default=current.get(CONF_MIN_MARGIN, 0)): _number(
            0, PRICE_MAX, 0.005, ""
        ),
        vol.Required(
            CONF_ESTIMATED_MARGIN,
            default=current.get(CONF_ESTIMATED_MARGIN, DEFAULT_ESTIMATED_MARGIN),
        ): _number(0, PRICE_MAX, 0.005, ""),
        vol.Required(
            CONF_CHARGE_HYSTERESIS, default=current.get(CONF_CHARGE_HYSTERESIS, 0)
        ): _number(0, 20, 1, "%"),
        vol.Required(
            CONF_VACATION, default=current.get(CONF_VACATION, False)
        ): BooleanSelector(),
        vol.Required(
            CONF_INTRADAY, default=current.get(CONF_INTRADAY, True)
        ): BooleanSelector(),
        vol.Required(
            CONF_STORAGE_BACKEND,
            default=current.get(CONF_STORAGE_BACKEND, BACKEND_JSON),
        ): SelectSelector(
            SelectSelectorConfig(
                options=list(BACKENDS),
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_STORAGE_BACKEND,
            )
        ),
        vol.Optional(
            CONF_STORAGE_URL,
            description={"suggested_value": current.get(CONF_STORAGE_URL)},
        ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        vol.Required(
            CONF_INTERCEPTOR,
            default=current.get(CONF_INTERCEPTOR, DEFAULT_INTERCEPTOR),
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    *(SelectOptionDict(value=k, label=k) for k in INTERCEPTORS),
                    *(
                        SelectOptionDict(value=k, label=_own_label(i, k, dutch))
                        for k, i in (await async_load_user_interceptors(hass)).items()
                    ),
                ],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_INTERCEPTOR,
            )
        ),
        vol.Required(
            CONF_FULL_CHARGE_DAY, default=current.get(CONF_FULL_CHARGE_DAY, "none")
        ): SelectSelector(
            SelectSelectorConfig(
                options=["none", *WEEKDAYS],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_FULL_CHARGE_DAY,
            )
        ),
        vol.Required(
            CONF_FULL_CHARGE_SOLAR, default=current.get(CONF_FULL_CHARGE_SOLAR, True)
        ): BooleanSelector(),
        vol.Optional(CONF_NOTIFY_TARGETS): SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=PERSISTENT, label=PERSISTENT),
                    *(
                        SelectOptionDict(value=name, label=f"notify.{name}")
                        for name in sorted(
                            hass.services.async_services_for_domain("notify")
                        )
                        if name not in ("send_message", "persistent_notification")
                    ),
                ],
                multiple=True,
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_NOTIFY_TARGETS,
            )
        ),
        vol.Optional(CONF_NOTIFY_KINDS): SelectSelector(
            SelectSelectorConfig(
                options=list(NOTIFY_KINDS),
                multiple=True,
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_NOTIFY_KINDS,
            )
        ),
        vol.Required(
            CONF_TEMP_LIMIT, default=current.get(CONF_TEMP_LIMIT, 40)
        ): _number(0, 80, 1, "°C"),
        vol.Required(CONF_TEMP_BAND, default=current.get(CONF_TEMP_BAND, 10)): _number(
            1, 40, 1, "°C"
        ),
        vol.Required(
            CONF_TEMP_MIN_POWER, default=current.get(CONF_TEMP_MIN_POWER, 40)
        ): _number(0, 100, 5, "%"),
        vol.Required(
            CONF_TEMP_DISCHARGE, default=current.get(CONF_TEMP_DISCHARGE, False)
        ): BooleanSelector(),
        vol.Required(
            CONF_SPIKE_BATTERY, default=current.get(CONF_SPIKE_BATTERY, True)
        ): BooleanSelector(),
        vol.Required(
            CONF_SPIKE_HISTORY, default=current.get(CONF_SPIKE_HISTORY, True)
        ): BooleanSelector(),
        vol.Required(
            CONF_SPIKE_THRESHOLD,
            default=current.get(CONF_SPIKE_THRESHOLD, DEFAULT_SPIKE_THRESHOLD),
        ): _number(500, 10000, 100, "W"),
        vol.Required(
            CONF_REACT_INTERVAL,
            default=current.get(CONF_REACT_INTERVAL, DEFAULT_REACT_INTERVAL),
        ): _number(1, 60, 1, "s"),
        vol.Required(
            CONF_REACT_AVERAGE, default=current.get(CONF_REACT_AVERAGE, True)
        ): BooleanSelector(),
        vol.Required(
            CONF_REACT_JUMP, default=current.get(CONF_REACT_JUMP, True)
        ): BooleanSelector(),
        vol.Required(
            CONF_REACT_JUMP_W,
            default=current.get(CONF_REACT_JUMP_W, DEFAULT_REACT_JUMP_W),
        ): _number(100, 10000, 100, "W"),
        vol.Required(
            CONF_NOM_CONTROL,
            default=current.get(CONF_NOM_CONTROL, CONTROL_DIRECT),
        ): SelectSelector(
            SelectSelectorConfig(
                options=list(CONTROLS),
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_NOM_CONTROL,
            )
        ),
        vol.Required(CONF_PD_KP, default=current.get(CONF_PD_KP, DEFAULT_KP)): _number(
            0.05, 1.5, 0.05, "", slider=True
        ),
        vol.Required(CONF_PD_KD, default=current.get(CONF_PD_KD, DEFAULT_KD)): _number(
            0, 1.5, 0.05, "", slider=True
        ),
        vol.Required(
            CONF_PD_MAX_STEP, default=current.get(CONF_PD_MAX_STEP, DEFAULT_MAX_STEP_W)
        ): _number(0, 5000, 50, "W"),
        vol.Required(
            CONF_PD_HYSTERESIS,
            default=current.get(CONF_PD_HYSTERESIS, DEFAULT_HYSTERESIS_W),
        ): _number(0, 500, 10, "W"),
        vol.Required(CONF_SIM_DELAY, default=current.get(CONF_SIM_DELAY, 0)): _number(
            0, 60, 1, "s"
        ),
        vol.Required(CONF_SIM_RAMP, default=current.get(CONF_SIM_RAMP, 0)): _number(
            0, 10000, 50, "W/s"
        ),
        vol.Required(
            CONF_SPIKE_DURATION,
            default=current.get(CONF_SPIKE_DURATION, DEFAULT_SPIKE_DURATION),
        ): _number(1, 60, 1, "min"),
        vol.Required(
            CONF_SPIKE_FILTER,
            default=current.get(CONF_SPIKE_FILTER, DEFAULT_SPIKE_FILTER),
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    *(SelectOptionDict(value=k, label=k) for k in SPIKE_FILTERS),
                    *(
                        SelectOptionDict(value=k, label=_own_label(f, k, dutch))
                        for k, f in (await async_load_user_spike_filters(hass)).items()
                    ),
                ],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_SPIKE_FILTER,
            )
        ),
        vol.Required(
            CONF_PEAK_INCLUDE_EXCLUDED,
            default=current.get(CONF_PEAK_INCLUDE_EXCLUDED, True),
        ): BooleanSelector(),
        vol.Required(
            CONF_PEAK_LIMIT,
            default=current.get(CONF_PEAK_LIMIT, DEFAULT_PEAK_LIMIT),
        ): _number(0, 60000, 100, "W"),
        vol.Required(
            CONF_PV_CORRECTION,
            default=current.get(CONF_PV_CORRECTION, PV_CORRECTION_BOTH),
        ): SelectSelector(
            SelectSelectorConfig(
                options=list(PV_CORRECTION_MODES),
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_PV_CORRECTION,
            )
        ),
        vol.Required(
            CONF_PV_CORRECTOR,
            default=current.get(CONF_PV_CORRECTOR, DEFAULT_PV_CORRECTOR),
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    *(SelectOptionDict(value=k, label=k) for k in PV_CORRECTORS),
                    *(
                        SelectOptionDict(value=k, label=_own_label(c, k, dutch))
                        for k, c in (await async_load_user_pv_correctors(hass)).items()
                    ),
                ],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_PV_CORRECTOR,
            )
        ),
        vol.Required(
            CONF_PV_MARGIN,
            default=current.get(CONF_PV_MARGIN, DEFAULT_PV_MARGIN),
        ): _number(0, 50, 1, "%"),
        vol.Required(
            CONF_PV_DEVIATION_W,
            default=current.get(CONF_PV_DEVIATION_W, DEFAULT_PV_DEVIATION_W),
        ): _number(100, 5000, 50, "W"),
        vol.Required(
            CONF_PV_DEVIATION_MINUTES,
            default=current.get(
                CONF_PV_DEVIATION_MINUTES, DEFAULT_PV_DEVIATION_MINUTES
            ),
        ): _number(1, 60, 1, "min"),
        vol.Required(
            CONF_COMMAND_CHECK_W,
            default=current.get(CONF_COMMAND_CHECK_W, DEFAULT_COMMAND_CHECK_W),
        ): _number(50, 2000, 50, "W"),
        vol.Required(
            CONF_COMMAND_CHECK_MINUTES,
            default=current.get(
                CONF_COMMAND_CHECK_MINUTES, DEFAULT_COMMAND_CHECK_MINUTES
            ),
        ): _number(1, 30, 1, "min"),
        vol.Required(
            CONF_EXPORT_NEVER,
            default=current.get(CONF_EXPORT_NEVER, DEFAULT_EXPORT_NEVER),
        ): BooleanSelector(),
        vol.Required(
            CONF_EXPORT_LIMIT,
            default=current.get(CONF_EXPORT_LIMIT, DEFAULT_EXPORT_LIMIT),
        ): BooleanSelector(),
        vol.Required(
            CONF_EXPORT_LIMIT_PRICE,
            default=current.get(CONF_EXPORT_LIMIT_PRICE, DEFAULT_EXPORT_LIMIT_PRICE),
        ): _number(-PRICE_MAX, PRICE_MAX, 0.001, "/kWh"),
        vol.Required(
            CONF_EXPORT_LIMIT_COST,
            default=current.get(CONF_EXPORT_LIMIT_COST, DEFAULT_EXPORT_LIMIT_COST),
        ): _number(0, PRICE_MAX, 0.001, "/kWh"),
        vol.Required(
            CONF_EXPORT_LIMIT_MAX_W,
            default=current.get(CONF_EXPORT_LIMIT_MAX_W, DEFAULT_EXPORT_LIMIT_MAX_W),
        ): _number(0, 100000, 50, "W"),
        vol.Required(
            CONF_MAX_CYCLES,
            default=current.get(CONF_MAX_CYCLES, DEFAULT_MAX_CYCLES),
        ): NumberSelector(
            NumberSelectorConfig(min=0, max=5, step=0.1, mode=NumberSelectorMode.BOX)
        ),
        vol.Required(
            CONF_EXPORT_MODE,
            default=current.get(CONF_EXPORT_MODE, DEFAULT_EXPORT_MODE),
        ): SelectSelector(
            SelectSelectorConfig(
                options=list(EXPORT_MODES),
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_EXPORT_MODE,
            )
        ),
        vol.Optional(CONF_EXPORT_ENTITIES): EntitySelector(
            EntitySelectorConfig(domain="sensor", multiple=True)
        ),
        vol.Required(
            CONF_EXPORT_FACTOR,
            default=current.get(CONF_EXPORT_FACTOR, DEFAULT_EXPORT_FACTOR),
        ): NumberSelector(
            NumberSelectorConfig(
                min=0, max=1.5, step=0.001, mode=NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            CONF_CHARGE_ORDER,
            default=current.get(CONF_CHARGE_ORDER, CHARGE_SEQUENTIAL),
        ): SelectSelector(
            SelectSelectorConfig(
                options=list(CHARGE_ORDER_OPTIONS),
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_CHARGE_ORDER,
            )
        ),
        vol.Required(
            CONF_MIN_BATTERY_POWER,
            default=current.get(CONF_MIN_BATTERY_POWER, DEFAULT_MIN_BATTERY_POWER),
        ): NumberSelector(
            NumberSelectorConfig(
                min=0,
                max=5000,
                step=10,
                unit_of_measurement="W",
                mode=NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            CONF_PHASE_MARGIN,
            default=current.get(CONF_PHASE_MARGIN, DEFAULT_PHASE_MARGIN),
        ): _number(0, 50, 1, "%"),
        vol.Required(
            CONF_FULL_CHARGE_WINDOW,
            default=current.get(CONF_FULL_CHARGE_WINDOW, DEFAULT_FULL_CHARGE_WINDOW),
        ): NumberSelector(
            NumberSelectorConfig(
                min=1,
                max=14,
                step=1,
                unit_of_measurement="d",
                mode=NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            CONF_BALANCE_INTERVAL,
            default=str(current.get(CONF_BALANCE_INTERVAL, DEFAULT_BALANCE_INTERVAL)),
        ): SelectSelector(
            SelectSelectorConfig(
                options=[str(m) for m in BALANCE_INTERVAL_OPTIONS],
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_BALANCE_INTERVAL,
            )
        ),
        vol.Required(
            CONF_CYCLE_COST, default=current.get(CONF_CYCLE_COST, DEFAULT_CYCLE_COST)
        ): NumberSelector(
            NumberSelectorConfig(
                min=0, max=PRICE_MAX, step=0.001, mode=NumberSelectorMode.BOX
            )
        ),
    }
    pv_options = [
        SelectOptionDict(value=value, label=label)
        for value, label in await async_find_pv_forecasts(
            hass, await async_load_user_pv_sources(hass), dutch
        )
    ]
    # Keep earlier choices selectable even if that integration is not loaded now.
    known = {option["value"] for option in pv_options}
    for entry_id in current.get(CONF_PV_FORECAST) or []:
        if entry_id not in known:
            entry = hass.config_entries.async_get_entry(entry_id)
            pv_options.append(
                SelectOptionDict(
                    value=entry_id, label=entry.title if entry else entry_id
                )
            )
    if pv_options:
        schema[vol.Optional(CONF_PV_FORECAST)] = SelectSelector(
            SelectSelectorConfig(
                options=pv_options,
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        )
    return vol.Schema(schema)


# Settings shown as a (single) select: their values are strings in the form.
SELECT_OPTIONS = (CONF_HISTORY_INTERVAL, CONF_FORECAST_INTERVAL, CONF_BALANCE_INTERVAL)


def _keep_flags(entry: ConfigEntry, data: dict[str, Any]) -> dict[str, Any]:
    """The grid steps rebuild the data: keep what HomeBatteryAssist set in it
    itself (the price thresholds check)."""
    if entry.data.get(PRICES_CHECKED):
        return {**data, PRICES_CHECKED: True}
    return data


def _reload_if_not_loaded(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """A loaded entry reloads through its update listener; one whose setup
    failed has none, so the fix the user just saved is tried here."""
    if entry.state not in (ConfigEntryState.LOADED, ConfigEntryState.SETUP_RETRY):
        hass.config_entries.async_schedule_reload(entry.entry_id)


async def storage_errors(
    hass: HomeAssistant,
    options: Mapping[str, Any],
    current: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """A database server needs a URL that can be reached (the data moves
    there at the next start). Only checked when the choice changes: a server
    that is down never blocks other settings."""
    backend = options.get(CONF_STORAGE_BACKEND, BACKEND_JSON)
    if backend not in SERVER_BACKENDS:
        return {}
    url = options.get(CONF_STORAGE_URL)
    if not url:
        return {"base": "storage_url_required"}
    scheme = url.split("://", 1)[0].split("+", 1)[0]
    wanted = ("postgresql",) if backend == "postgresql" else ("mysql", "mariadb")
    if scheme not in wanted:
        return {"base": "storage_url_scheme"}
    if current is not None and (
        current.get(CONF_STORAGE_BACKEND) == backend
        and current.get(CONF_STORAGE_URL) == url
    ):
        return {}
    if not await async_check_database(hass, database_url(hass, backend, url) or url):
        return {"base": "storage_unreachable"}
    return {}


def settings_from_input(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Convert the settings form input to stored options."""
    user_input = flatten_settings(user_input)
    options: dict[str, Any] = {
        CONF_HISTORY_INTERVAL: int(user_input[CONF_HISTORY_INTERVAL]),
        CONF_PLANNING_HORIZON: int(user_input[CONF_PLANNING_HORIZON]),
        CONF_FORECAST_INTERVAL: int(
            user_input.get(CONF_FORECAST_INTERVAL, DEFAULT_FORECAST_INTERVAL)
        ),
        CONF_PLAN_MODE: user_input.get(CONF_PLAN_MODE, DEFAULT_PLAN_MODE),
        CONF_CONSUMPTION_FORECASTER: user_input.get(
            CONF_CONSUMPTION_FORECASTER, DEFAULT_FORECASTER
        ),
        CONF_TARIFF: user_input.get(CONF_TARIFF, DEFAULT_TARIFF),
        CONF_TARIFF_SURCHARGE: float(user_input.get(CONF_TARIFF_SURCHARGE, 0.0)),
        CONF_TARIFF_ENERGY_TAX: float(user_input.get(CONF_TARIFF_ENERGY_TAX, 0.0)),
        CONF_TARIFF_VAT: float(user_input.get(CONF_TARIFF_VAT, DEFAULT_TARIFF_VAT)),
        CONF_EXPORT_FACTOR: float(
            user_input.get(CONF_EXPORT_FACTOR, DEFAULT_EXPORT_FACTOR)
        ),
        CONF_CYCLE_COST: float(user_input.get(CONF_CYCLE_COST, DEFAULT_CYCLE_COST)),
        CONF_MIN_BATTERY_POWER: int(
            user_input.get(CONF_MIN_BATTERY_POWER, DEFAULT_MIN_BATTERY_POWER)
        ),
        CONF_CHARGE_ORDER: user_input.get(CONF_CHARGE_ORDER, CHARGE_SEQUENTIAL),
        CONF_BALANCE_INTERVAL: int(
            user_input.get(CONF_BALANCE_INTERVAL, DEFAULT_BALANCE_INTERVAL)
        ),
        CONF_FULL_CHARGE_WINDOW: int(
            user_input.get(CONF_FULL_CHARGE_WINDOW, DEFAULT_FULL_CHARGE_WINDOW)
        ),
        CONF_PHASE_MARGIN: int(user_input.get(CONF_PHASE_MARGIN, DEFAULT_PHASE_MARGIN)),
    }
    if user_input.get(CONF_PRICE_FORECAST):
        options[CONF_PRICE_FORECAST] = user_input[CONF_PRICE_FORECAST]
    options[CONF_WEATHER_SOURCE] = user_input.get(
        CONF_WEATHER_SOURCE, DEFAULT_WEATHER_SOURCE
    )
    for key in (
        CONF_WEATHER_ENTITY,
        CONF_WEATHER_API_KEY,
        CONF_WEATHER_LOCATION,
        CONF_OUTDOOR_TEMPERATURE,
    ):
        if user_input.get(key):
            options[key] = user_input[key]
    options[CONF_PRICE_SOURCE] = user_input.get(CONF_PRICE_SOURCE, PRICE_SOURCE_SENSOR)
    options[CONF_PRICE_EXTENSION] = user_input.get(
        CONF_PRICE_EXTENSION, PRICE_EXTENSION_NONE
    )
    options[CONF_EXPORT_MODE] = user_input.get(CONF_EXPORT_MODE, DEFAULT_EXPORT_MODE)
    options[CONF_MANUAL_POWER] = int(
        user_input.get(CONF_MANUAL_POWER, DEFAULT_MANUAL_POWER)
    )
    options[CONF_RESERVE_SOC] = int(user_input.get(CONF_RESERVE_SOC, 0))
    options[CONF_NIGHT_RESERVE_SOC] = int(user_input.get(CONF_NIGHT_RESERVE_SOC, 0))
    options[CONF_PEAK_RESERVE_SOC] = int(user_input.get(CONF_PEAK_RESERVE_SOC, 0))
    options[CONF_SYSTEM_MAX_CHARGE] = int(user_input.get(CONF_SYSTEM_MAX_CHARGE, 0))
    options[CONF_SYSTEM_MAX_DISCHARGE] = int(
        user_input.get(CONF_SYSTEM_MAX_DISCHARGE, 0)
    )
    options[CONF_NOM_TARGET] = int(user_input.get(CONF_NOM_TARGET, 0))
    options[CONF_MIN_MARGIN] = float(user_input.get(CONF_MIN_MARGIN, 0))
    options[CONF_ESTIMATED_MARGIN] = float(
        user_input.get(CONF_ESTIMATED_MARGIN, DEFAULT_ESTIMATED_MARGIN)
    )
    options[CONF_CHARGE_HYSTERESIS] = int(user_input.get(CONF_CHARGE_HYSTERESIS, 0))
    options[CONF_VACATION] = bool(user_input.get(CONF_VACATION, False))
    options[CONF_INTRADAY] = bool(user_input.get(CONF_INTRADAY, True))
    options[CONF_STORAGE_BACKEND] = user_input.get(CONF_STORAGE_BACKEND, BACKEND_JSON)
    if (url := (user_input.get(CONF_STORAGE_URL) or "").strip()) and options[
        CONF_STORAGE_BACKEND
    ] in SERVER_BACKENDS:
        options[CONF_STORAGE_URL] = url
    options[CONF_INTERCEPTOR] = user_input.get(CONF_INTERCEPTOR, DEFAULT_INTERCEPTOR)
    options[CONF_FULL_CHARGE_DAY] = user_input.get(CONF_FULL_CHARGE_DAY, "none")
    options[CONF_FULL_CHARGE_SOLAR] = bool(user_input.get(CONF_FULL_CHARGE_SOLAR, True))
    options[CONF_NOTIFY_TARGETS] = list(user_input.get(CONF_NOTIFY_TARGETS) or [])
    options[CONF_NOTIFY_KINDS] = list(user_input.get(CONF_NOTIFY_KINDS) or [])
    options[CONF_TEMP_LIMIT] = int(user_input.get(CONF_TEMP_LIMIT, 40))
    options[CONF_TEMP_BAND] = int(user_input.get(CONF_TEMP_BAND, 10))
    options[CONF_TEMP_MIN_POWER] = int(user_input.get(CONF_TEMP_MIN_POWER, 40))
    options[CONF_TEMP_DISCHARGE] = bool(user_input.get(CONF_TEMP_DISCHARGE, False))
    options[CONF_SPIKE_BATTERY] = bool(user_input.get(CONF_SPIKE_BATTERY, True))
    options[CONF_SPIKE_HISTORY] = bool(user_input.get(CONF_SPIKE_HISTORY, True))
    options[CONF_REACT_INTERVAL] = int(
        user_input.get(CONF_REACT_INTERVAL, DEFAULT_REACT_INTERVAL)
    )
    options[CONF_REACT_AVERAGE] = bool(user_input.get(CONF_REACT_AVERAGE, True))
    options[CONF_REACT_JUMP] = bool(user_input.get(CONF_REACT_JUMP, True))
    options[CONF_NOM_CONTROL] = user_input.get(CONF_NOM_CONTROL, CONTROL_DIRECT)
    options[CONF_PD_KP] = float(user_input.get(CONF_PD_KP, DEFAULT_KP))
    options[CONF_PD_KD] = float(user_input.get(CONF_PD_KD, DEFAULT_KD))
    options[CONF_PD_MAX_STEP] = int(
        user_input.get(CONF_PD_MAX_STEP, DEFAULT_MAX_STEP_W)
    )
    options[CONF_PD_HYSTERESIS] = int(
        user_input.get(CONF_PD_HYSTERESIS, DEFAULT_HYSTERESIS_W)
    )
    options[CONF_SIM_DELAY] = int(user_input.get(CONF_SIM_DELAY, 0))
    options[CONF_SIM_RAMP] = int(user_input.get(CONF_SIM_RAMP, 0))
    options[CONF_REACT_JUMP_W] = int(
        user_input.get(CONF_REACT_JUMP_W, DEFAULT_REACT_JUMP_W)
    )
    options[CONF_SPIKE_THRESHOLD] = int(
        user_input.get(CONF_SPIKE_THRESHOLD, DEFAULT_SPIKE_THRESHOLD)
    )
    options[CONF_SPIKE_DURATION] = int(
        user_input.get(CONF_SPIKE_DURATION, DEFAULT_SPIKE_DURATION)
    )
    options[CONF_SPIKE_FILTER] = user_input.get(CONF_SPIKE_FILTER, DEFAULT_SPIKE_FILTER)
    options[CONF_PEAK_INCLUDE_EXCLUDED] = bool(
        user_input.get(CONF_PEAK_INCLUDE_EXCLUDED, True)
    )
    for key in (CONF_MIN_DISCHARGE_PRICE, CONF_MAX_CHARGE_PRICE):
        if user_input.get(key) is not None:
            options[key] = float(user_input[key])
    options[CONF_PEAK_LIMIT] = int(user_input.get(CONF_PEAK_LIMIT, DEFAULT_PEAK_LIMIT))
    options[CONF_PV_CORRECTION] = user_input.get(CONF_PV_CORRECTION, PV_CORRECTION_BOTH)
    options[CONF_PV_CORRECTOR] = user_input.get(CONF_PV_CORRECTOR, DEFAULT_PV_CORRECTOR)
    options[CONF_PV_MARGIN] = int(user_input.get(CONF_PV_MARGIN, DEFAULT_PV_MARGIN))
    options[CONF_PV_DEVIATION_W] = int(
        user_input.get(CONF_PV_DEVIATION_W, DEFAULT_PV_DEVIATION_W)
    )
    options[CONF_PV_DEVIATION_MINUTES] = int(
        user_input.get(CONF_PV_DEVIATION_MINUTES, DEFAULT_PV_DEVIATION_MINUTES)
    )
    options[CONF_COMMAND_CHECK_W] = int(
        user_input.get(CONF_COMMAND_CHECK_W, DEFAULT_COMMAND_CHECK_W)
    )
    options[CONF_COMMAND_CHECK_MINUTES] = int(
        user_input.get(CONF_COMMAND_CHECK_MINUTES, DEFAULT_COMMAND_CHECK_MINUTES)
    )
    options[CONF_EXPORT_LIMIT] = bool(
        user_input.get(CONF_EXPORT_LIMIT, DEFAULT_EXPORT_LIMIT)
    )
    options[CONF_EXPORT_LIMIT_PRICE] = float(
        user_input.get(CONF_EXPORT_LIMIT_PRICE, DEFAULT_EXPORT_LIMIT_PRICE)
    )
    options[CONF_EXPORT_NEVER] = bool(
        user_input.get(CONF_EXPORT_NEVER, DEFAULT_EXPORT_NEVER)
    )
    options[CONF_EXPORT_LIMIT_COST] = float(
        user_input.get(CONF_EXPORT_LIMIT_COST, DEFAULT_EXPORT_LIMIT_COST)
    )
    options[CONF_EXPORT_LIMIT_MAX_W] = int(
        user_input.get(CONF_EXPORT_LIMIT_MAX_W, DEFAULT_EXPORT_LIMIT_MAX_W)
    )
    options[CONF_MAX_CYCLES] = float(
        user_input.get(CONF_MAX_CYCLES, DEFAULT_MAX_CYCLES)
    )
    if user_input.get(CONF_EXPORT_ENTITIES):
        options[CONF_EXPORT_ENTITIES] = list(user_input[CONF_EXPORT_ENTITIES])
    if user_input.get(CONF_PV_FORECAST):
        options[CONF_PV_FORECAST] = list(user_input[CONF_PV_FORECAST])
    return options


def _direct_key(source: str | None, address: str | None) -> str:
    return f"direct:{source}:{address}"


DIRECT_MANUAL = "direct_manual"


def _direct_options(
    meters: list[MeterCandidate],
    speedwire: dict[str, int],
    direct: list[DirectCandidate],
) -> dict[str, DirectCandidate]:
    """Meters that can be read directly, by option key."""
    options: dict[str, DirectCandidate] = {}
    phases_of = {m.address: m.phases for m in meters if m.address}
    for candidate in direct:
        if candidate.phases is None and candidate.address in phases_of:
            candidate = replace(candidate, phases=phases_of[candidate.address])
        options[_direct_key(candidate.source, candidate.address)] = candidate
    for address, serial in sorted(speedwire.items()):
        # Known by its serial number (in every telegram): a new IP address
        # (DHCP) changes nothing.
        options[_direct_key(SOURCE_SPEEDWIRE, str(serial))] = DirectCandidate(
            SOURCE_SPEEDWIRE,
            str(serial),
            f"{SOURCE_NAMES[SOURCE_SPEEDWIRE]} ({address})",
            None,
        )
    return options


def _direct_label(candidate: DirectCandidate, dutch: bool) -> str:
    if candidate.source == SOURCE_HOMEWIZARD_V2:
        how = (
            "rechtstreeks, de meter stuurt elke meting, alleen lezen"
            if dutch
            else "read directly, the meter pushes every reading, read-only"
        )
    else:
        how = (
            "rechtstreeks, elke seconde, alleen lezen"
            if dutch
            else "read directly, every second, read-only"
        )
    driver = get_meter_driver(candidate.source)
    mark = untested(driver is not None and driver.verified, dutch)
    return f"{candidate.name} {candidate.address} ({how}){mark}"


class _GridSteps:
    """Steps 0-3 (grid meter, phases, connection size, sensors).

    Shared by the setup (and reconfigure) flow and the options flow, so the
    meter and the phases can also be changed under "Configure".
    """

    _data: dict[str, Any]
    hass: Any

    def _existing_entry(self) -> ConfigEntry | None:
        """The entry being changed (None at the first setup)."""
        return None

    def _init_grid(self) -> None:
        self._data = {}
        self._meters: dict[str, MeterCandidate] = {}
        self._direct: dict[str, DirectCandidate] = {}
        self._meter_offered = False
        self._from_meter = False

    async def _async_grid_done(self) -> ConfigFlowResult:
        raise NotImplementedError

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: choose a 1-phase or 3-phase connection.

        First offers the grid meters found in other integrations (step meter).
        """
        if user_input is None and not self._meter_offered:
            self._meter_offered = True
            found = find_meter_candidates(self.hass)
            self._meters = {c.device_id: c for c in found}
            self._direct = _direct_options(
                found,
                await discover_speedwire(self.hass),
                find_direct_meters(self.hass),
            )
            return await self.async_step_meter()
        if user_input is not None:
            self._data[CONF_PHASES] = int(user_input[CONF_PHASES])
            return await self.async_step_max_current()

        suggested = {CONF_PHASES: str(self._data[CONF_PHASES])} if self._data else None
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(PHASES_SCHEMA, suggested),
        )

    async def async_step_meter(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 0: a grid meter found in another integration, or manual."""
        errors: dict[str, str] = {}
        if user_input is not None:
            choice = user_input[CONF_SOURCE]
            if choice == DIRECT_MANUAL:
                return await self.async_step_direct()
            if direct := self._direct.get(choice):
                return await self.async_step_meter_choice(
                    direct.source, direct.address, direct.phases
                )
            meter = self._meters.get(choice)
            if meter is None:
                self._from_meter = False
                return await self.async_step_user()
            entry = self._existing_entry()
            if entry is not None and any(
                sensor_conflict(entry, sensor, None) == "sensor_in_use"
                for sensor in meter.sensors.values()
                if sensor
            ):
                # Every sensor once (as in the sensors step): one a subentry
                # already measures would be counted twice.
                errors["base"] = "sensor_in_use"
            else:
                self._from_meter = True
                self._data = {
                    **{k: v for k, v in self._data.items() if k == CONF_MAX_CURRENT},
                    CONF_PHASES: meter.phases,
                    **meter.sensors,
                }
                return await self.async_step_max_current()

        default = next(iter(self._direct), None) or next(
            iter(self._meters), SOURCE_MANUAL
        )
        if self._data:  # reconfigure: keep what is used now
            current = _direct_key(
                self._data.get(CONF_METER_SOURCE), self._data.get(CONF_METER_ADDRESS)
            )
            default = (
                current
                if current in self._direct
                # A meter entered by address (not found again now): keep it.
                else DIRECT_MANUAL
                if self._data.get(CONF_METER_SOURCE)
                else next(
                    (
                        c.device_id
                        for c in self._meters.values()
                        if all(self._data.get(k) == v for k, v in c.sensors.items())
                        and self._data.get(CONF_PHASES) == c.phases
                        and CONF_METER_SOURCE not in self._data
                    ),
                    SOURCE_MANUAL,
                )
            )
        dutch = (self.hass.config.language or "").startswith("nl")
        return self.async_show_form(
            step_id="meter",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SOURCE, default=default): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                *(
                                    SelectOptionDict(
                                        value=key, label=_direct_label(c, dutch)
                                    )
                                    for key, c in self._direct.items()
                                ),
                                *(
                                    SelectOptionDict(
                                        value=c.device_id,
                                        label=c.label
                                        + untested(c.profile.verified, dutch),
                                    )
                                    for c in self._meters.values()
                                ),
                                SelectOptionDict(
                                    value=DIRECT_MANUAL, label=DIRECT_MANUAL
                                ),
                                SelectOptionDict(
                                    value=SOURCE_MANUAL, label=SOURCE_MANUAL
                                ),
                            ],
                            mode=SelectSelectorMode.LIST,
                            translation_key="meter",
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_direct(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """A meter read directly at an address you enter (e.g. not in Home Assistant)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            address = str(user_input.get(CONF_METER_ADDRESS) or "").strip()
            if address:
                return await self.async_step_meter_choice(
                    user_input[CONF_METER_SOURCE], address
                )
            errors[CONF_METER_ADDRESS] = "address_required"
        suggested = {
            CONF_METER_SOURCE: self._data.get(CONF_METER_SOURCE, SOURCE_HOMEWIZARD),
            CONF_METER_ADDRESS: self._data.get(CONF_METER_ADDRESS, ""),
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_METER_SOURCE): SelectSelector(
                    SelectSelectorConfig(
                        options=list(DIRECT_SOURCES),
                        mode=SelectSelectorMode.LIST,
                        translation_key=CONF_METER_SOURCE,
                    )
                ),
                vol.Required(CONF_METER_ADDRESS): TextSelector(),
            }
        )
        return self.async_show_form(
            step_id="direct",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or suggested
            ),
            errors=errors,
        )

    async def async_step_meter_choice(
        self, source: str, address: str, phases: int | None = None
    ) -> ConfigFlowResult:
        """Use a directly read meter; ask the phases if the meter can't tell."""
        self._from_meter = True
        # Keep the grid sensors (unused meanwhile): choosing your own sensors
        # again later starts from them.
        self._data = {
            **{
                k: v
                for k, v in self._data.items()
                if k in (CONF_MAX_CURRENT, CONF_PHASES)
                or k in CONF_PHASE_SENSORS
                or k in CONF_PHASE_RETURN_SENSORS
            },
            CONF_METER_SOURCE: source,
            CONF_METER_ADDRESS: address,
        }
        if phases:
            self._data[CONF_PHASES] = phases
            return await self.async_step_max_current()
        return await self._async_ask_phases()

    async def _async_ask_phases(self) -> ConfigFlowResult:
        """The phases of a directly read meter that measures all three."""
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                PHASES_SCHEMA, {CONF_PHASES: str(self._data.get(CONF_PHASES, 3))}
            ),
        )

    async def async_step_max_current(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: maximum current per phase (main fuse rating)."""
        if user_input is not None:
            self._data[CONF_MAX_CURRENT] = int(user_input[CONF_MAX_CURRENT])
            if (
                self._data[CONF_PHASES] == 3
                and self._data[CONF_MAX_CURRENT] > HEAVY_CONNECTION_A
            ):
                return await self.async_step_heavy_connection()
            return await self._async_after_max_current()

        phases = self._data[CONF_PHASES]
        current = self._data.get(CONF_MAX_CURRENT)
        suggested = (
            {CONF_MAX_CURRENT: str(current)}
            if current in MAX_CURRENT_OPTIONS[phases]
            else None
        )
        return self.async_show_form(
            step_id="max_current",
            data_schema=self.add_suggested_values_to_schema(
                max_current_schema(phases), suggested
            ),
        )

    async def _async_after_max_current(self) -> ConfigFlowResult:
        if self._from_meter:
            return await self._async_grid_done()
        return await self.async_step_sensors()

    async def async_step_heavy_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2b: a connection heavier than 3x35A, confirmed apart with a
        warning (the phase protection's limit; a wrong choice here would let
        the batteries overload the main fuse). Not confirmed: choose again."""
        if user_input is not None:
            if user_input.get("confirm"):
                return await self._async_after_max_current()
            return await self.async_step_max_current()
        amps = self._data[CONF_MAX_CURRENT]
        return self.async_show_form(
            step_id="heavy_connection",
            data_schema=vol.Schema(
                {vol.Required("confirm", default=False): BooleanSelector()}
            ),
            description_placeholders={
                "connection": f"3x{amps}A",
                "usual": f"3x{HEAVY_CONNECTION_A}A",
                "amps": str(amps),
            },
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: the sensor that measures power or current on each phase."""
        phases = self._data[CONF_PHASES]
        errors: dict[str, str] = {}

        if user_input is not None:
            selected = [value for value in user_input.values() if value]
            if len(set(selected)) != len(selected):
                errors["base"] = "duplicate_sensor"
            if not errors and (entry := self._existing_entry()) is not None:
                # Every sensor once: not one a subentry already measures.
                for key, value in user_input.items():
                    if value and sensor_conflict(entry, value, None) == "sensor_in_use":
                        errors[key] = "sensor_in_use"
            if not errors:
                # Rebuild, so sensors of removed phases or emptied fields go away.
                self._data = {
                    CONF_PHASES: phases,
                    CONF_MAX_CURRENT: self._data[CONF_MAX_CURRENT],
                    **{key: value for key, value in user_input.items() if value},
                }
                return await self._async_grid_done()

        return self.async_show_form(
            step_id="sensors",
            data_schema=self.add_suggested_values_to_schema(
                sensors_schema(phases), user_input or self._data
            ),
            errors=errors,
        )


class HomeBatteryAssistConfigFlow(_GridSteps, ConfigFlow, domain=DOMAIN):
    """Handle the UI setup of HomeBatteryAssist."""

    VERSION = 1

    def _existing_entry(self) -> ConfigEntry | None:
        return (
            self._get_reconfigure_entry() if self.source == SOURCE_RECONFIGURE else None
        )

    def __init__(self) -> None:
        """Initialize the flow."""
        self._init_grid()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the grid connection (steps 1-3), prefilled with the current data."""
        self._data = dict(self._get_reconfigure_entry().data)
        return await self.async_step_user()

    async def _async_grid_done(self) -> ConfigFlowResult:
        """The grid connection is complete: save it (reconfigure) or continue."""
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            result = self.async_update_and_abort(
                entry, data=_keep_flags(entry, self._data)
            )
            _reload_if_not_loaded(self.hass, entry)  # else the listener reloads
            return result
        return await self.async_step_settings()

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4: history interval, planning horizon and forecast inputs."""
        errors: dict[str, str] = {}
        if user_input is not None:
            options = settings_from_input(user_input)
            if not (errors := await storage_errors(self.hass, options)):
                # A new entry: thresholds entered now are meant as they are.
                return self.async_create_entry(
                    title=NAME,
                    data={**self._data, PRICES_CHECKED: True},
                    options=options,
                )

        # After an error: what was entered (also inside the sections).
        values = user_input or await settings_form_values(self.hass, {})
        schema = await settings_schema(self.hass, None, values)
        return self.async_show_form(
            step_id="settings",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or values
            ),
            errors=errors,
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentry types: PV sources, excluded loads, batteries."""
        return {
            SUBENTRY_PV_SOURCE: PvSourceSubentryFlow,
            SUBENTRY_EXCLUDED_LOAD: ExcludedLoadSubentryFlow,
            SUBENTRY_HEATING_COOLING: HeatingCoolingSubentryFlow,
            SUBENTRY_BATTERY: BatterySubentryFlow,
            SUBENTRY_VIRTUAL_BATTERY: VirtualBatterySubentryFlow,
            SUBENTRY_TIME_SLOT: TimeSlotSubentryFlow,
        }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return HomeBatteryAssistOptionsFlow()


class HomeBatteryAssistOptionsFlow(_GridSteps, OptionsFlow):
    """Change an existing entry: settings, or the grid connection and meter."""

    def _existing_entry(self) -> ConfigEntry | None:
        return self.config_entry

    def __init__(self) -> None:
        """Initialize the flow."""
        self._init_grid()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose what to change."""
        return self.async_show_menu(
            step_id="init", menu_options=["settings", "grid", "defaults"]
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change interval, planning horizon, forecast inputs and battery settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            options = settings_from_input(user_input)
            if not (
                errors := await storage_errors(
                    self.hass, options, self.config_entry.options
                )
            ):
                _reload_if_not_loaded(self.hass, self.config_entry)
                return self.async_create_entry(data=options)

        current = self.config_entry.options
        # After an error: what was entered (also inside the sections).
        values = user_input or await settings_form_values(self.hass, current)
        schema = await settings_schema(self.hass, current, values)
        return self.async_show_form(
            step_id="settings",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or values
            ),
            errors=errors,
        )

    async def async_step_defaults(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Back to the default settings (the chosen inputs are kept)."""
        if user_input is not None:
            defaults = await settings_defaults(self.hass)
            kept = {
                key: value
                for key, value in self.config_entry.options.items()
                if key in KEEP_ON_RESET
            }
            _reload_if_not_loaded(self.hass, self.config_entry)
            return self.async_create_entry(
                data=settings_from_input({**defaults, **kept})
            )
        return self.async_show_form(step_id="defaults", data_schema=vol.Schema({}))

    async def async_step_grid(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the grid meter, phases, connection size and sensors."""
        self._data = dict(self.config_entry.data)
        return await self.async_step_user()

    async def _async_grid_done(self) -> ConfigFlowResult:
        """Save the new grid connection; the entry reloads."""
        entry = self.config_entry
        self.hass.config_entries.async_update_entry(
            entry, data=_keep_flags(entry, self._data)
        )
        _reload_if_not_loaded(self.hass, entry)
        return self.async_create_entry(data=dict(entry.options))


class _MeasuredDeviceSubentryFlow(ConfigSubentryFlow):
    """Add or change a named device with a power/current sensor and phase."""

    allow_direct = False  # PV sources: also a directly read meter
    # optional fields of this kind of device: key -> selector
    extra_fields: ClassVar[dict[str, Any]] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a new device."""
        return await self._async_step_device("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change an existing device."""
        return await self._async_step_device("reconfigure", user_input)

    async def _async_step_device(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        entry = self._get_entry()
        three_phase = entry.data[CONF_PHASES] == 3
        current = self._get_reconfigure_subentry() if step_id == "reconfigure" else None
        errors: dict[str, str] = {}

        direct = self.allow_direct
        if user_input is not None:
            driver = user_input.get(CONF_PV_DRIVER, PV_DRIVER_SENSOR)
            address = (user_input.get(CONF_PV_ADDRESS) or "").strip()
            data = {
                CONF_NAME: user_input[CONF_NAME],
                CONF_SENSOR: user_input.get(CONF_SENSOR) or "",
                CONF_PHASE: user_input.get(CONF_PHASE, PHASE_NONE),
            }
            data.update(
                {
                    key: user_input[key]
                    for key in self.extra_fields
                    if user_input.get(key)
                }
            )
            if direct:
                data[CONF_PV_DRIVER] = driver
                if driver != PV_DRIVER_SENSOR:
                    data[CONF_PV_ADDRESS] = address
            if driver == PV_DRIVER_SENSOR and not data[CONF_SENSOR]:
                errors = {CONF_SENSOR: "sensor_required"}
            elif driver != PV_DRIVER_SENSOR and not address:
                errors = {CONF_PV_ADDRESS: "address_required"}
            phase_sensors = {
                key: user_input[key]
                for key in CONF_DEVICE_PHASE_SENSORS
                if user_input.get(key)
            }
            if phase_sensors:
                # Measured per phase: a 3-phase device, not bound to one phase.
                data.update(phase_sensors)
                data[CONF_PHASE] = PHASE_NONE
            if not errors and data[CONF_SENSOR]:
                errors = self._validate_sensor(entry, data[CONF_SENSOR], current)
            for key, sensor in phase_sensors.items():
                if not errors and (error := sensor_conflict(entry, sensor, current)):
                    errors = {key: error}
            if not errors:
                unique = data[CONF_SENSOR] or f"{driver}:{address}"
                if current is None:
                    return self.async_create_entry(
                        title=data[CONF_NAME], data=data, unique_id=unique
                    )
                return self.async_update_and_abort(
                    entry,
                    current,
                    title=data[CONF_NAME],
                    data=data,
                    unique_id=unique,
                )

        schema: dict[Any, Any] = {vol.Required(CONF_NAME): TextSelector()}
        dutch = (self.hass.config.language or "").startswith("nl")
        if direct:
            schema[vol.Required(CONF_PV_DRIVER, default=PV_DRIVER_SENSOR)] = (
                SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=PV_DRIVER_SENSOR, label=PV_DRIVER_SENSOR
                            ),
                            *(
                                SelectOptionDict(
                                    value=d.key,
                                    label=f"{d.name}{untested(d.verified, dutch)}",
                                )
                                for d in METER_DRIVERS
                                if d.pv_capable
                            ),
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key=CONF_PV_DRIVER,
                    )
                )
            )
            schema[vol.Optional(CONF_SENSOR)] = PHASE_SENSOR_SELECTOR
            schema[vol.Optional(CONF_PV_ADDRESS)] = TextSelector()
        else:
            schema[vol.Required(CONF_SENSOR)] = PHASE_SENSOR_SELECTOR
        if three_phase:
            schema[vol.Required(CONF_PHASE, default=PHASE_NONE)] = phase_selector()
            for key in CONF_DEVICE_PHASE_SENSORS:
                schema[vol.Optional(key)] = PHASE_SENSOR_SELECTOR
        for key, selector in self.extra_fields.items():
            schema[vol.Optional(key)] = selector
        suggested = user_input or (dict(current.data) if current else None)
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema), suggested
            ),
            errors=errors,
        )

    @staticmethod
    def _validate_sensor(
        entry: ConfigEntry, sensor: str, current: ConfigSubentry | None
    ) -> dict[str, str]:
        """A sensor may not be a grid phase sensor or be used by another device."""
        error = sensor_conflict(entry, sensor, current)
        return {CONF_SENSOR: error} if error else {}


class PvSourceSubentryFlow(_MeasuredDeviceSubentryFlow):
    """Add or change a PV production measurement; optionally the inverter
    driver that could limit it (export limit; nothing is sent in this phase)."""

    allow_direct = True  # a PV meter may also be read directly
    extra_fields: ClassVar[dict[str, Any]] = {
        CONF_INVERTER_DRIVER: SelectSelector(
            SelectSelectorConfig(
                options=[INVERTER_NONE, *(d.key for d in INVERTER_DRIVERS)],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_INVERTER_DRIVER,
            )
        ),
        CONF_INVERTER_ADDRESS: TextSelector(),
        CONF_INVERTER_MAX_CURRENT: NumberSelector(
            NumberSelectorConfig(
                min=1,
                max=80,
                step=1,
                unit_of_measurement="A",
                mode=NumberSelectorMode.BOX,
            )
        ),
        CONF_PV_POSSIBLE_SENSOR: EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class="power")
        ),
    }


class ExcludedLoadSubentryFlow(_MeasuredDeviceSubentryFlow):
    """Add or change a device excluded from house consumption."""


class HeatingCoolingSubentryFlow(_MeasuredDeviceSubentryFlow):
    """Add or change a heating/cooling device (part of the house consumption,
    measured apart so the forecast can follow the outdoor temperature); with
    the temperature of its room (and its own outdoor sensor) it is a zone."""

    extra_fields: ClassVar[dict[str, Any]] = {
        CONF_INDOOR_TEMPERATURE: EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class="temperature")
        ),
        CONF_OUTDOOR_TEMPERATURE: EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class="temperature")
        ),
    }


PRICE_MAX = 1000.0  # per kWh in any currency (JPY, CZK, SEK, EUR, ...)


def _price_number() -> NumberSelector:
    """An amount per kWh (price unit of the source), e.g. 0.0916."""
    return NumberSelector(
        NumberSelectorConfig(
            min=-PRICE_MAX,
            max=PRICE_MAX,
            step="any",
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="/kWh",
        )
    )


def _number(
    minimum: float, maximum: float, step: float, unit: str, *, slider: bool = False
) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=NumberSelectorMode.SLIDER if slider else NumberSelectorMode.BOX,
        )
    )


def _select(options: list[str], key: str) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=options, mode=SelectSelectorMode.DROPDOWN, translation_key=key
        )
    )


SIGN_OPTIONS = [SIGN_CHARGING_POSITIVE, SIGN_DISCHARGING_POSITIVE]


def used_sensors(entry: ConfigEntry) -> set[str]:
    """All sensors already used by the grid connection or a subentry."""
    used = set(grid_sensors(entry.data))
    for subentry in entry.subentries.values():
        used.update(v for key in SUBENTRY_SENSOR_KEYS if (v := subentry.data.get(key)))
    return used


def battery_schema(
    three_phase: bool, single_phase: bool = False, dutch: bool = False
) -> vol.Schema:
    """Reading and properties of a battery. ``single_phase``: a battery
    on one phase (a plug-in battery): on a 3-phase connection its phase
    must be chosen (spreading it over all phases under-counts the phase)."""
    schema: dict[Any, Any] = {
        vol.Required(CONF_NAME): TextSelector(),
        vol.Required(CONF_SOC_SENSOR): EntitySelector(
            EntitySelectorConfig(
                domain="sensor", device_class=SensorDeviceClass.BATTERY
            )
        ),
        vol.Required(CONF_POWER_SENSOR): PHASE_SENSOR_SELECTOR,
        vol.Required(CONF_POWER_SIGN, default=SIGN_CHARGING_POSITIVE): _select(
            SIGN_OPTIONS, CONF_POWER_SIGN
        ),
        vol.Required(CONF_CAPACITY): _number(0.1, 1000, 0.01, "kWh"),
        vol.Required(CONF_MAX_CHARGE_POWER): _number(1, 50000, 1, "W"),
        vol.Required(CONF_MAX_DISCHARGE_POWER): _number(1, 50000, 1, "W"),
        vol.Required(CONF_MIN_SOC, default=DEFAULT_MIN_SOC): _number(
            0, 100, 1, "%", slider=True
        ),
        vol.Required(CONF_MAX_SOC, default=DEFAULT_MAX_SOC): _number(
            0, 100, 1, "%", slider=True
        ),
        vol.Required(CONF_EFFICIENCY, default=DEFAULT_EFFICIENCY): _number(
            50, 100, 1, "%", slider=True
        ),
        vol.Required(
            CONF_FULL_CHARGE_INTERVAL, default=DEFAULT_FULL_CHARGE_INTERVAL
        ): _number(0, 90, 1, "d"),
        vol.Optional(CONF_TEMPERATURE_SENSOR): EntitySelector(
            EntitySelectorConfig(
                domain="sensor", device_class=SensorDeviceClass.TEMPERATURE
            )
        ),
        # Optional external meter on the battery's line (read directly).
        vol.Required(CONF_BATTERY_METER, default=BATTERY_METER_NONE): SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(
                        value=BATTERY_METER_NONE, label=BATTERY_METER_NONE
                    ),
                    *(
                        SelectOptionDict(
                            value=d.key,
                            label=f"{d.name}{untested(d.verified, dutch)}",
                        )
                        for d in METER_DRIVERS
                        if d.pv_capable
                    ),
                ],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_BATTERY_METER,
            )
        ),
        vol.Optional(CONF_BATTERY_METER_ADDRESS): TextSelector(),
    }
    if three_phase and single_phase:
        schema[vol.Required(CONF_PHASE)] = SelectSelector(
            SelectSelectorConfig(
                options=list(PHASE_IDS),
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_PHASE,
            )
        )
    elif three_phase:
        schema[vol.Required(CONF_PHASE, default=PHASE_NONE)] = phase_selector()
    return vol.Schema(schema)


def _device_model(hass: HomeAssistant, subentry: ConfigSubentry) -> Any:
    """The battery type of the device behind a battery's SoC sensor, if known."""
    from .engine.devices.batteries import model_for

    entity = er.async_get(hass).async_get(subentry.data.get(CONF_SOC_SENSOR, ""))
    if entity is None or entity.device_id is None:
        return None
    device = dr.async_get(hass).async_get(entity.device_id)
    return model_for(device.model) if device else None


class BatterySubentryFlow(ConfigSubentryFlow):
    """Link a home battery (read-only): pick a detected one or link manually."""

    def __init__(self) -> None:
        """Initialize."""
        self._candidates: dict[str, BatteryCandidate] = {}
        self._suggested_data: dict[str, Any] | None = None
        self._single_phase = False  # the recognised type is on one phase

    def _current(self) -> ConfigSubentry | None:
        return (
            self._get_reconfigure_subentry() if self.source == "reconfigure" else None
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Step 1: a battery found in another integration, or manual linking."""
        if user_input is not None:
            candidate = self._candidates.get(user_input[CONF_SOURCE])
            self._suggested_data = dict(candidate.data) if candidate else None
            self._single_phase = bool(
                candidate
                and candidate.battery_model
                and candidate.battery_model.phases == 1
            )
            if (
                self._single_phase
                and self._suggested_data
                and self._suggested_data.get(CONF_PHASE) not in PHASE_IDS
            ):
                self._suggested_data.pop(CONF_PHASE, None)
            return await self.async_step_battery()

        found = find_battery_candidates(self.hass, used_sensors(self._get_entry()))
        if not found:
            return await self.async_step_battery()
        self._candidates = {c.device_id: c for c in found}
        dutch = (self.hass.config.language or "").startswith("nl")
        options = [
            SelectOptionDict(
                value=c.device_id, label=c.label + untested(c.profile.verified, dutch)
            )
            for c in found
        ]
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SOURCE, default=found[0].device_id
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                *options,
                                SelectOptionDict(
                                    value=SOURCE_MANUAL, label=SOURCE_MANUAL
                                ),
                            ],
                            mode=SelectSelectorMode.LIST,
                            translation_key=CONF_SOURCE,
                        )
                    )
                }
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change a battery."""
        if user_input is None:
            # A type on one phase (e.g. a Marstek Venus): its phase must be
            # chosen, also when it was linked before this was asked.
            model = _device_model(self.hass, self._get_reconfigure_subentry())
            self._single_phase = bool(model and model.phases == 1)
        return await self._async_step_battery("reconfigure", user_input)

    async def async_step_battery(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Step 2: sensors and properties (prefilled for a detected battery)."""
        return await self._async_step_battery("battery", user_input)

    async def _async_step_battery(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        entry = self._get_entry()
        current = self._current()
        errors: dict[str, str] = {}
        if user_input is not None:
            for key in BATTERY_SENSOR_KEYS:
                if error := sensor_conflict(entry, user_input[key], current):
                    errors[key] = error
            if user_input[CONF_SOC_SENSOR] == user_input[CONF_POWER_SENSOR]:
                errors[CONF_POWER_SENSOR] = "sensor_in_use"
            if user_input[CONF_MIN_SOC] >= user_input[CONF_MAX_SOC]:
                errors[CONF_MAX_SOC] = "soc_range"
            if (
                user_input.get(CONF_BATTERY_METER, BATTERY_METER_NONE)
                != BATTERY_METER_NONE
                and not (user_input.get(CONF_BATTERY_METER_ADDRESS) or "").strip()
            ):
                errors[CONF_BATTERY_METER_ADDRESS] = "address_required"
            if not errors:
                return self._async_finish(self._battery_data(user_input), current)

        suggested = (
            user_input
            or self._suggested_data
            or (dict(current.data) if current else None)
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                battery_schema(
                    entry.data[CONF_PHASES] == 3,
                    self._single_phase,
                    (self.hass.config.language or "").startswith("nl"),
                ),
                suggested,
            ),
            errors=errors,
        )

    @staticmethod
    def _battery_data(user_input: dict[str, Any]) -> dict[str, Any]:
        data = {**user_input}
        address = (user_input.get(CONF_BATTERY_METER_ADDRESS) or "").strip()
        if address:
            data[CONF_BATTERY_METER_ADDRESS] = address
        else:
            data.pop(CONF_BATTERY_METER_ADDRESS, None)
        return {
            **data,
            CONF_PHASE: user_input.get(CONF_PHASE, PHASE_NONE),
            CONF_CAPACITY: float(user_input[CONF_CAPACITY]),
            **{
                key: int(user_input[key])
                for key in (
                    CONF_MAX_CHARGE_POWER,
                    CONF_MAX_DISCHARGE_POWER,
                    CONF_MIN_SOC,
                    CONF_MAX_SOC,
                    CONF_EFFICIENCY,
                    CONF_FULL_CHARGE_INTERVAL,
                )
            },
        }

    @callback
    def _async_finish(
        self, data: dict[str, Any], current: ConfigSubentry | None
    ) -> SubentryFlowResult:
        title, unique_id = data[CONF_NAME], data[CONF_POWER_SENSOR]
        if current is None:
            return self.async_create_entry(title=title, data=data, unique_id=unique_id)
        return self.async_update_and_abort(
            self._get_entry(), current, title=title, data=data, unique_id=unique_id
        )


def virtual_name(name: str, language: str | None) -> str:
    """A virtual battery's name always says it is virtual, so it is never
    mistaken for a real one (e.g. "Marstek Venus 1 (virtueel)")."""
    name = name.strip()
    if "virtu" in name.lower():
        return name
    dutch = (language or "").lower().startswith("nl")
    return f"{name} ({'virtueel' if dutch else 'virtual'})"


def twin_options(entry: ConfigEntry, language: str | None) -> list[SelectOptionDict]:
    """What a virtual battery can be the twin of: none, or a real battery."""
    dutch = (language or "").lower().startswith("nl")
    return [
        SelectOptionDict(
            value=TWIN_NONE,
            label="Geen: een eigen virtuele batterij"
            if dutch
            else "None: a virtual battery of its own",
        ),
        *(
            SelectOptionDict(value=sub.subentry_id, label=sub.data[CONF_NAME])
            for sub in entry.subentries.values()
            if sub.subentry_type == SUBENTRY_BATTERY
        ),
    ]


def virtual_battery_schema(
    three_phase: bool, twins: list[SelectOptionDict] | None = None
) -> vol.Schema:
    """Properties of a virtual (simulated) battery."""
    schema: dict[Any, Any] = {
        vol.Required(CONF_NAME): TextSelector(),
    }
    if twins and len(twins) > 1:
        schema[vol.Required(CONF_TWIN_OF, default=TWIN_NONE)] = SelectSelector(
            SelectSelectorConfig(options=twins, mode=SelectSelectorMode.DROPDOWN)
        )
    schema |= {
        vol.Required(CONF_CAPACITY, default=5.12): _number(0.1, 1000, 0.01, "kWh"),
        vol.Required(CONF_MAX_CHARGE_POWER, default=2500): _number(1, 50000, 1, "W"),
        vol.Required(CONF_MAX_DISCHARGE_POWER, default=2500): _number(1, 50000, 1, "W"),
        vol.Required(CONF_MIN_SOC, default=DEFAULT_MIN_SOC): _number(
            0, 100, 1, "%", slider=True
        ),
        vol.Required(CONF_MAX_SOC, default=DEFAULT_MAX_SOC): _number(
            0, 100, 1, "%", slider=True
        ),
        vol.Required(CONF_LOSS_MIN, default=DEFAULT_LOSS_MIN): _number(0, 60, 1, "%"),
        vol.Required(CONF_LOSS_MAX, default=DEFAULT_LOSS_MAX): _number(0, 60, 1, "%"),
        vol.Required(CONF_INITIAL_SOC, default=DEFAULT_INITIAL_SOC): _number(
            0, 100, 1, "%", slider=True
        ),
        vol.Required(
            CONF_FULL_CHARGE_INTERVAL, default=DEFAULT_FULL_CHARGE_INTERVAL
        ): _number(0, 90, 1, "d"),
    }
    if three_phase:
        schema[vol.Required(CONF_PHASE, default=PHASE_NONE)] = phase_selector()
    return vol.Schema(schema)


class VirtualBatterySubentryFlow(ConfigSubentryFlow):
    """Add or change a virtual battery: a live simulation to test what-ifs."""

    def _current(self) -> ConfigSubentry | None:
        return (
            self._get_reconfigure_subentry() if self.source == "reconfigure" else None
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a virtual battery."""
        return await self._async_step("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change a virtual battery."""
        return await self._async_step("reconfigure", user_input)

    async def _async_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        entry = self._get_entry()
        current = self._current()
        errors: dict[str, str] = {}
        if user_input is not None:
            twin = user_input.get(CONF_TWIN_OF, TWIN_NONE)
            taken = {
                sub.data.get(CONF_TWIN_OF)
                for sub in entry.subentries.values()
                if sub.subentry_type == SUBENTRY_VIRTUAL_BATTERY
                and (current is None or sub.subentry_id != current.subentry_id)
            }
            if twin != TWIN_NONE and twin in taken:
                errors[CONF_TWIN_OF] = "twin_taken"
            elif user_input[CONF_MIN_SOC] >= user_input[CONF_MAX_SOC]:
                errors[CONF_MAX_SOC] = "soc_range"
            elif user_input[CONF_LOSS_MIN] > user_input[CONF_LOSS_MAX]:
                errors[CONF_LOSS_MAX] = "loss_range"
            else:
                data = {
                    CONF_NAME: virtual_name(
                        user_input[CONF_NAME], self.hass.config.language
                    ),
                    CONF_CAPACITY: float(user_input[CONF_CAPACITY]),
                    CONF_PHASE: user_input.get(CONF_PHASE, PHASE_NONE),
                    CONF_TWIN_OF: twin,
                    **{
                        key: int(user_input[key])
                        for key in (
                            CONF_MAX_CHARGE_POWER,
                            CONF_MAX_DISCHARGE_POWER,
                            CONF_MIN_SOC,
                            CONF_MAX_SOC,
                            CONF_LOSS_MIN,
                            CONF_LOSS_MAX,
                            CONF_INITIAL_SOC,
                            CONF_FULL_CHARGE_INTERVAL,
                        )
                    },
                }
                if current is None:
                    return self.async_create_entry(title=data[CONF_NAME], data=data)
                return self.async_update_and_abort(
                    entry, current, title=data[CONF_NAME], data=data
                )
        suggested = user_input or (dict(current.data) if current else None)
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                virtual_battery_schema(
                    entry.data[CONF_PHASES] == 3,
                    twin_options(entry, self.hass.config.language),
                ),
                suggested,
            ),
            errors=errors,
        )


def time_slot_schema() -> vol.Schema:
    """A time slot: when, and what the batteries do."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME): TextSelector(),
            vol.Required("start", default="01:00:00"): TimeSelector(),
            vol.Required("end", default="05:00:00"): TimeSelector(),
            vol.Required("days", default=list(WEEKDAYS)): SelectSelector(
                SelectSelectorConfig(
                    options=list(WEEKDAYS),
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                    translation_key="weekday",
                )
            ),
            vol.Required("action", default=ACTION_CHARGE): SelectSelector(
                SelectSelectorConfig(
                    options=list(ACTIONS),
                    mode=SelectSelectorMode.LIST,
                    translation_key="slot_action",
                )
            ),
            vol.Required("power", default=2000): _number(0, 20000, 50, "W"),
            vol.Optional("soc"): _number(0, 100, 1, "%", slider=True),
        }
    )


class TimeSlotSubentryFlow(ConfigSubentryFlow):
    """Add or change a time slot (used in the plan mode "time slots")."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a time slot."""
        return await self._async_step("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change a time slot."""
        return await self._async_step("reconfigure", user_input)

    async def _async_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get("days"):
                errors["days"] = "no_days"
            else:
                data = {
                    CONF_NAME: user_input[CONF_NAME],
                    "start": user_input["start"],
                    "end": user_input["end"],
                    "days": list(user_input["days"]),
                    "action": user_input["action"],
                    "power": int(user_input.get("power", 0)),
                }
                if user_input.get("soc") is not None:
                    data["soc"] = int(user_input["soc"])
                if step_id == "reconfigure":
                    return self.async_update_and_abort(
                        self._get_entry(),
                        self._get_reconfigure_subentry(),
                        data=data,
                        title=data[CONF_NAME],
                    )
                return self.async_create_entry(title=data[CONF_NAME], data=data)
        current = (
            dict(self._get_reconfigure_subentry().data)
            if step_id == "reconfigure"
            else {}
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                time_slot_schema(), user_input or current
            ),
            errors=errors,
        )
