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
from typing import Any

import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
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
    TimeSelector,
)

from .const import (
    BALANCE_INTERVAL_OPTIONS,
    BATTERY_SENSOR_KEYS,
    CONF_BALANCE_INTERVAL,
    CONF_CAPACITY,
    CONF_CHARGE_HYSTERESIS,
    CONF_CONSUMPTION_FORECASTER,
    CONF_CYCLE_COST,
    CONF_DEVICE_PHASE_SENSORS,
    CONF_EFFICIENCY,
    CONF_EXPORT_ENTITIES,
    CONF_EXPORT_FACTOR,
    CONF_EXPORT_MODE,
    CONF_FORECAST_INTERVAL,
    CONF_FULL_CHARGE_DAY,
    CONF_FULL_CHARGE_INTERVAL,
    CONF_FULL_CHARGE_SOLAR,
    CONF_FULL_CHARGE_WINDOW,
    CONF_HISTORY_INTERVAL,
    CONF_INITIAL_SOC,
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
    CONF_NOM_TARGET,
    CONF_NOTIFY_KINDS,
    CONF_NOTIFY_TARGETS,
    CONF_PEAK_INCLUDE_EXCLUDED,
    CONF_PEAK_LIMIT,
    CONF_PHASE,
    CONF_PHASE_MARGIN,
    CONF_PHASE_RETURN_SENSORS,
    CONF_PHASE_SENSORS,
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
    CONF_PV_DRIVER,
    CONF_PV_FORECAST,
    CONF_PV_MARGIN,
    CONF_RESERVE_SOC,
    CONF_SENSOR,
    CONF_SOC_SENSOR,
    CONF_SOURCE,
    CONF_SYSTEM_MAX_CHARGE,
    CONF_SYSTEM_MAX_DISCHARGE,
    CONF_TARIFF,
    CONF_TEMP_BAND,
    CONF_TEMP_DISCHARGE,
    CONF_TEMP_LIMIT,
    CONF_TEMP_MIN_POWER,
    CONF_TEMPERATURE_SENSOR,
    CONF_VACATION,
    DEFAULT_BALANCE_INTERVAL,
    DEFAULT_CYCLE_COST,
    DEFAULT_EFFICIENCY,
    DEFAULT_EXPORT_FACTOR,
    DEFAULT_EXPORT_MODE,
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
    DEFAULT_PV_MARGIN,
    DOMAIN,
    EXPORT_MODES,
    FORECAST_INTERVAL_OPTIONS,
    HISTORY_INTERVAL_OPTIONS,
    MAX_CURRENT_OPTIONS,
    MAX_PLANNING_HORIZON,
    MIN_PLANNING_HORIZON,
    NAME,
    PHASE_IDS,
    PHASE_NONE,
    PHASE_OPTIONS,
    PRICE_EXTENSION_NONE,
    PRICE_SOURCE_SENSOR,
    PV_CORRECTION_BOTH,
    PV_CORRECTION_MODES,
    PV_DRIVER_SENSOR,
    SIGN_CHARGING_POSITIVE,
    SIGN_DISCHARGING_POSITIVE,
    SOURCE_MANUAL,
    SUBENTRY_BATTERY,
    SUBENTRY_EXCLUDED_LOAD,
    SUBENTRY_PV_SOURCE,
    SUBENTRY_TIME_SLOT,
    SUBENTRY_VIRTUAL_BATTERY,
    phase_return_sensor_keys,
    phase_sensor_keys,
)
from .explain.notify import KINDS as NOTIFY_KINDS
from .explain.notify import PERSISTENT
from .forecasts.forecasters import BUILTIN as FORECASTERS
from .forecasts.forecasters import DEFAULT_FORECASTER, async_load_user_forecasters
from .inputs.direct import (
    DIRECT_SOURCES,
    SOURCE_HOMEWIZARD,
    SOURCE_NAMES,
    SOURCE_SPEEDWIRE,
    DirectCandidate,
    discover_speedwire,
    find_direct_meters,
)
from .inputs.meter_drivers import DRIVERS as METER_DRIVERS
from .inputs.meters import MeterCandidate, find_meter_candidates
from .inputs.price_drivers import find_sources, get_driver
from .inputs.profiles import BatteryCandidate, find_battery_candidates
from .inputs.pv_forecasts import async_find_pv_forecasts, async_load_user_pv_sources
from .inputs.tariffs import BUILTIN as TARIFFS
from .inputs.tariffs import DEFAULT_TARIFF, async_load_user_tariffs
from .planning.battery_plan import DEFAULT_PLAN_MODE, PLAN_MODES
from .planning.planners import async_load_user_planners
from .planning.schedule import ACTION_CHARGE, ACTIONS, WEEKDAYS

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


def sensors_schema(phases: int) -> vol.Schema:
    """Build the sensor step schema for the given number of phases."""
    schema: dict[Any, Any] = {}
    for key, return_key in zip(
        phase_sensor_keys(phases), phase_return_sensor_keys(phases), strict=True
    ):
        schema[vol.Required(key)] = PHASE_SENSOR_SELECTOR
        schema[vol.Optional(return_key)] = PHASE_SENSOR_SELECTOR
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


def _price_source_selector(
    hass: HomeAssistant, first: str, key: str, *, forecasts: bool = True
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
        untested = "" if driver is None or driver.verified else " *"
        suffix = only if source.forecast_only else ""
        options.append(
            SelectOptionDict(
                value=source.key, label=f"{source.title}{suffix}{untested}"
            )
        )
    return SelectSelector(
        SelectSelectorConfig(
            options=options, mode=SelectSelectorMode.DROPDOWN, translation_key=key
        )
    )


# Settings grouped in collapsible sections; the rest stays at the top.
SETTINGS_SECTIONS: dict[str, tuple[str, ...]] = {
    "export": ("export_price_mode", "export_price_entities", "export_price_factor"),
    "solar": ("pv_correction", "pv_forecast_margin"),
    "planning": (
        "cycle_cost",
        "max_cycles_per_day",
        "min_arbitrage_margin",
        "min_discharge_price",
        "max_charge_price",
        "nom_target_w",
        "manual_power_w",
        "charge_hysteresis",
        "vacation",
    ),
    "limits": (
        "reserve_soc",
        "system_max_charge_w",
        "system_max_discharge_w",
        "min_battery_power",
        "balance_interval",
        "peak_limit_w",
        "peak_include_excluded",
        "phase_margin",
    ),
    "full_charge": ("full_charge_window_days", "full_charge_day", "full_charge_solar"),
    "notifications": ("notify_targets", "notify_kinds"),
    "temperature": (
        "temperature_limit",
        "temperature_band",
        "temperature_min_power",
        "temperature_discharge",
    ),
}


async def settings_schema(
    hass: HomeAssistant, current: Mapping[str, Any] | None = None
) -> vol.Schema:
    """The settings form: main fields on top, the rest in collapsed sections."""
    flat = await _flat_settings_schema(hass, current)
    top: dict[Any, Any] = {}
    grouped: dict[str, dict[Any, Any]] = {name: {} for name in SETTINGS_SECTIONS}
    where = {key: name for name, keys in SETTINGS_SECTIONS.items() for key in keys}
    for marker, validator in flat.schema.items():
        name = where.get(str(marker))
        (grouped[name] if name else top)[marker] = validator
    for name, fields in grouped.items():
        if fields:
            top[vol.Required(name, default={})] = section(
                vol.Schema(fields), {"collapsed": True}
            )
    return vol.Schema(top)


# Kept when going back to the defaults: where the inputs come from.
KEEP_ON_RESET = (
    CONF_NOTIFY_TARGETS,
    CONF_NOTIFY_KINDS,
    CONF_PRICE_SOURCE,
    CONF_PRICE_EXTENSION,
    CONF_PRICE_FORECAST,
    CONF_PV_FORECAST,
    CONF_EXPORT_ENTITIES,
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
            hass, PRICE_SOURCE_SENSOR, CONF_PRICE_SOURCE, forecasts=False
        ),
        vol.Required(
            CONF_PRICE_EXTENSION,
            default=current.get(CONF_PRICE_EXTENSION, PRICE_EXTENSION_NONE),
        ): _price_source_selector(hass, PRICE_EXTENSION_NONE, CONF_PRICE_EXTENSION),
        vol.Optional(CONF_PRICE_FORECAST): EntitySelector(
            EntitySelectorConfig(domain="sensor")
        ),
        vol.Required(
            CONF_PLAN_MODE, default=current.get(CONF_PLAN_MODE, DEFAULT_PLAN_MODE)
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    *(SelectOptionDict(value=m, label=m) for m in PLAN_MODES),
                    *(
                        SelectOptionDict(value=key, label=p.name or key)
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
                        SelectOptionDict(value=k, label=f.name or k)
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
                        SelectOptionDict(value=k, label=t.name or k)
                        for k, t in (await async_load_user_tariffs(hass)).items()
                    ),
                ],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_TARIFF,
            )
        ),
        vol.Required(
            CONF_MANUAL_POWER,
            default=current.get(CONF_MANUAL_POWER, DEFAULT_MANUAL_POWER),
        ): _number(-20000, 20000, 50, "W"),
        vol.Required(
            CONF_RESERVE_SOC, default=current.get(CONF_RESERVE_SOC, 0)
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
        vol.Optional(CONF_MIN_DISCHARGE_PRICE): _number(-1, 5, 0.001, ""),
        vol.Optional(CONF_MAX_CHARGE_PRICE): _number(-1, 5, 0.001, ""),
        vol.Required(CONF_MIN_MARGIN, default=current.get(CONF_MIN_MARGIN, 0)): _number(
            0, 1, 0.005, ""
        ),
        vol.Required(
            CONF_CHARGE_HYSTERESIS, default=current.get(CONF_CHARGE_HYSTERESIS, 0)
        ): _number(0, 20, 1, "%"),
        vol.Required(
            CONF_VACATION, default=current.get(CONF_VACATION, False)
        ): BooleanSelector(),
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
            CONF_PV_MARGIN,
            default=current.get(CONF_PV_MARGIN, DEFAULT_PV_MARGIN),
        ): _number(0, 50, 1, "%"),
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
                min=0, max=0.5, step=0.001, mode=NumberSelectorMode.BOX
            )
        ),
    }
    pv_options = [
        SelectOptionDict(value=value, label=label)
        for value, label in await async_find_pv_forecasts(
            hass, await async_load_user_pv_sources(hass)
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
        CONF_EXPORT_FACTOR: float(
            user_input.get(CONF_EXPORT_FACTOR, DEFAULT_EXPORT_FACTOR)
        ),
        CONF_CYCLE_COST: float(user_input.get(CONF_CYCLE_COST, DEFAULT_CYCLE_COST)),
        CONF_MIN_BATTERY_POWER: int(
            user_input.get(CONF_MIN_BATTERY_POWER, DEFAULT_MIN_BATTERY_POWER)
        ),
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
    options[CONF_PRICE_SOURCE] = user_input.get(CONF_PRICE_SOURCE, PRICE_SOURCE_SENSOR)
    options[CONF_PRICE_EXTENSION] = user_input.get(
        CONF_PRICE_EXTENSION, PRICE_EXTENSION_NONE
    )
    options[CONF_EXPORT_MODE] = user_input.get(CONF_EXPORT_MODE, DEFAULT_EXPORT_MODE)
    options[CONF_MANUAL_POWER] = int(
        user_input.get(CONF_MANUAL_POWER, DEFAULT_MANUAL_POWER)
    )
    options[CONF_RESERVE_SOC] = int(user_input.get(CONF_RESERVE_SOC, 0))
    options[CONF_SYSTEM_MAX_CHARGE] = int(user_input.get(CONF_SYSTEM_MAX_CHARGE, 0))
    options[CONF_SYSTEM_MAX_DISCHARGE] = int(
        user_input.get(CONF_SYSTEM_MAX_DISCHARGE, 0)
    )
    options[CONF_NOM_TARGET] = int(user_input.get(CONF_NOM_TARGET, 0))
    options[CONF_MIN_MARGIN] = float(user_input.get(CONF_MIN_MARGIN, 0))
    options[CONF_CHARGE_HYSTERESIS] = int(user_input.get(CONF_CHARGE_HYSTERESIS, 0))
    options[CONF_VACATION] = bool(user_input.get(CONF_VACATION, False))
    options[CONF_FULL_CHARGE_DAY] = user_input.get(CONF_FULL_CHARGE_DAY, "none")
    options[CONF_FULL_CHARGE_SOLAR] = bool(user_input.get(CONF_FULL_CHARGE_SOLAR, True))
    options[CONF_NOTIFY_TARGETS] = list(user_input.get(CONF_NOTIFY_TARGETS) or [])
    options[CONF_NOTIFY_KINDS] = list(user_input.get(CONF_NOTIFY_KINDS) or [])
    options[CONF_TEMP_LIMIT] = int(user_input.get(CONF_TEMP_LIMIT, 40))
    options[CONF_TEMP_BAND] = int(user_input.get(CONF_TEMP_BAND, 10))
    options[CONF_TEMP_MIN_POWER] = int(user_input.get(CONF_TEMP_MIN_POWER, 40))
    options[CONF_TEMP_DISCHARGE] = bool(user_input.get(CONF_TEMP_DISCHARGE, False))
    options[CONF_PEAK_INCLUDE_EXCLUDED] = bool(
        user_input.get(CONF_PEAK_INCLUDE_EXCLUDED, True)
    )
    for key in (CONF_MIN_DISCHARGE_PRICE, CONF_MAX_CHARGE_PRICE):
        if user_input.get(key) is not None:
            options[key] = float(user_input[key])
    options[CONF_PEAK_LIMIT] = int(user_input.get(CONF_PEAK_LIMIT, DEFAULT_PEAK_LIMIT))
    options[CONF_PV_CORRECTION] = user_input.get(CONF_PV_CORRECTION, PV_CORRECTION_BOTH)
    options[CONF_PV_MARGIN] = int(user_input.get(CONF_PV_MARGIN, DEFAULT_PV_MARGIN))
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
    for address in sorted(speedwire):
        options[_direct_key(SOURCE_SPEEDWIRE, address)] = DirectCandidate(
            SOURCE_SPEEDWIRE, address, SOURCE_NAMES[SOURCE_SPEEDWIRE], None
        )
    return options


def _direct_label(candidate: DirectCandidate, dutch: bool) -> str:
    how = (
        "rechtstreeks, elke seconde, alleen lezen"
        if dutch
        else "read directly, every second, read-only"
    )
    return f"{candidate.name} {candidate.address} ({how})"


class _GridSteps:
    """Steps 0-3 (grid meter, phases, connection size, sensors).

    Shared by the setup (and reconfigure) flow and the options flow, so the
    meter and the phases can also be changed under "Configure".
    """

    _data: dict[str, Any]
    hass: Any

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
                                    SelectOptionDict(value=c.device_id, label=c.label)
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
        )

    async def async_step_direct(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """A meter read directly at an address you enter (e.g. not in Home Assistant)."""
        if user_input is not None:
            return await self.async_step_meter_choice(
                user_input[CONF_METER_SOURCE], user_input[CONF_METER_ADDRESS].strip()
            )
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
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
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
            if self._from_meter:
                return await self._async_grid_done()
            return await self.async_step_sensors()

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
            else:
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
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(), data=self._data
            )
        return await self.async_step_settings()

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4: history interval, planning horizon and forecast inputs."""
        if user_input is not None:
            return self.async_create_entry(
                title=NAME, data=self._data, options=settings_from_input(user_input)
            )

        schema = await settings_schema(self.hass)
        return self.async_show_form(
            step_id="settings",
            data_schema=self.add_suggested_values_to_schema(
                schema, await settings_form_values(self.hass, {})
            ),
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
        if user_input is not None:
            return self.async_create_entry(data=settings_from_input(user_input))

        current = self.config_entry.options
        schema = await settings_schema(self.hass, current)
        return self.async_show_form(
            step_id="settings",
            data_schema=self.add_suggested_values_to_schema(
                schema, await settings_form_values(self.hass, current)
            ),
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
        self.hass.config_entries.async_update_entry(self.config_entry, data=self._data)
        return self.async_create_entry(data=dict(self.config_entry.options))


class _MeasuredDeviceSubentryFlow(ConfigSubentryFlow):
    """Add or change a named device with a power/current sensor and phase."""

    allow_direct = False  # PV sources: also a directly read meter

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
        if direct:
            schema[vol.Required(CONF_PV_DRIVER, default=PV_DRIVER_SENSOR)] = (
                SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=PV_DRIVER_SENSOR, label=PV_DRIVER_SENSOR
                            ),
                            *(
                                SelectOptionDict(value=d.key, label=d.name)
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
    allow_direct = True  # a PV meter may also be read directly

    """Add or change a PV production measurement."""


class ExcludedLoadSubentryFlow(_MeasuredDeviceSubentryFlow):
    """Add or change a device excluded from house consumption."""


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


def battery_schema(three_phase: bool) -> vol.Schema:
    """Reading and properties of a battery."""
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
    }
    if three_phase:
        schema[vol.Required(CONF_PHASE, default=PHASE_NONE)] = phase_selector()
    return vol.Schema(schema)


class BatterySubentryFlow(ConfigSubentryFlow):
    """Link a home battery (read-only): pick a detected one or link manually."""

    def __init__(self) -> None:
        """Initialize."""
        self._candidates: dict[str, BatteryCandidate] = {}
        self._suggested_data: dict[str, Any] | None = None

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
            return await self.async_step_battery()

        found = find_battery_candidates(self.hass, used_sensors(self._get_entry()))
        if not found:
            return await self.async_step_battery()
        self._candidates = {c.device_id: c for c in found}
        options = [SelectOptionDict(value=c.device_id, label=c.label) for c in found]
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
                battery_schema(entry.data[CONF_PHASES] == 3), suggested
            ),
            errors=errors,
        )

    @staticmethod
    def _battery_data(user_input: dict[str, Any]) -> dict[str, Any]:
        return {
            **user_input,
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


def virtual_battery_schema(three_phase: bool) -> vol.Schema:
    """Properties of a virtual (simulated) battery."""
    schema: dict[Any, Any] = {
        vol.Required(CONF_NAME): TextSelector(),
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
            if user_input[CONF_MIN_SOC] >= user_input[CONF_MAX_SOC]:
                errors[CONF_MAX_SOC] = "soc_range"
            elif user_input[CONF_LOSS_MIN] > user_input[CONF_LOSS_MAX]:
                errors[CONF_LOSS_MAX] = "loss_range"
            else:
                data = {
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_CAPACITY: float(user_input[CONF_CAPACITY]),
                    CONF_PHASE: user_input.get(CONF_PHASE, PHASE_NONE),
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
                virtual_battery_schema(entry.data[CONF_PHASES] == 3), suggested
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
