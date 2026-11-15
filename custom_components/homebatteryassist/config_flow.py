"""Config flow for HomeBatteryAssist.

Steps:
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
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
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
from homeassistant.helpers.selector import (
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
)

from .const import (
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_PHASE,
    CONF_PHASES,
    CONF_PLANNING_HORIZON,
    CONF_PRICE_FORECAST,
    CONF_PV_FORECAST,
    CONF_SENSOR,
    DEFAULT_HISTORY_INTERVAL,
    DEFAULT_MAX_CURRENT,
    DEFAULT_PLANNING_HORIZON,
    DOMAIN,
    HISTORY_INTERVAL_OPTIONS,
    MAX_CURRENT_OPTIONS,
    MAX_PLANNING_HORIZON,
    MIN_PLANNING_HORIZON,
    NAME,
    PHASE_IDS,
    PHASE_NONE,
    PHASE_OPTIONS,
    SUBENTRY_EXCLUDED_LOAD,
    SUBENTRY_PV_SOURCE,
    phase_return_sensor_keys,
    phase_sensor_keys,
)
from .inputs.solar import async_solar_forecast_entries

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


def grid_sensors(data: dict[str, Any]) -> set[str]:
    """Return all grid sensors (import and return) configured in ``data``."""
    keys = (*phase_sensor_keys(3), *phase_return_sensor_keys(3))
    return {data[key] for key in keys if data.get(key)}


async def settings_schema(
    hass: HomeAssistant, current: Mapping[str, Any] | None = None
) -> vol.Schema:
    """Build the schema for the changeable settings (setup step 4 and options)."""
    current = current or {}
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
        vol.Optional(CONF_PRICE_FORECAST): EntitySelector(
            EntitySelectorConfig(domain="sensor")
        ),
    }
    pv_options = [
        SelectOptionDict(value=e.entry_id, label=e.title)
        for e in await async_solar_forecast_entries(hass)
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


def settings_from_input(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Convert the settings form input to stored options."""
    options: dict[str, Any] = {
        CONF_HISTORY_INTERVAL: int(user_input[CONF_HISTORY_INTERVAL]),
        CONF_PLANNING_HORIZON: int(user_input[CONF_PLANNING_HORIZON]),
    }
    if user_input.get(CONF_PRICE_FORECAST):
        options[CONF_PRICE_FORECAST] = user_input[CONF_PRICE_FORECAST]
    if user_input.get(CONF_PV_FORECAST):
        options[CONF_PV_FORECAST] = list(user_input[CONF_PV_FORECAST])
    return options


class HomeBatteryAssistConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup of HomeBatteryAssist."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: choose a 1-phase or 3-phase connection."""
        if user_input is not None:
            self._data[CONF_PHASES] = int(user_input[CONF_PHASES])
            return await self.async_step_max_current()

        return self.async_show_form(step_id="user", data_schema=PHASES_SCHEMA)

    async def async_step_max_current(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: maximum current per phase (main fuse rating)."""
        if user_input is not None:
            self._data[CONF_MAX_CURRENT] = int(user_input[CONF_MAX_CURRENT])
            return await self.async_step_sensors()

        return self.async_show_form(
            step_id="max_current",
            data_schema=max_current_schema(self._data[CONF_PHASES]),
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
                self._data.update(user_input)
                return await self.async_step_settings()

        return self.async_show_form(
            step_id="sensors",
            data_schema=self.add_suggested_values_to_schema(
                sensors_schema(phases), user_input
            ),
            errors=errors,
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4: history interval, planning horizon and forecast inputs."""
        if user_input is not None:
            return self.async_create_entry(
                title=NAME, data=self._data, options=settings_from_input(user_input)
            )

        return self.async_show_form(
            step_id="settings", data_schema=await settings_schema(self.hass)
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentry types: PV sources and excluded loads."""
        return {
            SUBENTRY_PV_SOURCE: PvSourceSubentryFlow,
            SUBENTRY_EXCLUDED_LOAD: ExcludedLoadSubentryFlow,
        }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return HomeBatteryAssistOptionsFlow()


class HomeBatteryAssistOptionsFlow(OptionsFlow):
    """Change settings of an existing HomeBatteryAssist entry."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change interval, planning horizon and forecast inputs."""
        if user_input is not None:
            return self.async_create_entry(data=settings_from_input(user_input))

        current = self.config_entry.options
        schema = await settings_schema(self.hass, current)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, current),
        )


class _MeasuredDeviceSubentryFlow(ConfigSubentryFlow):
    """Add or change a named device with a power/current sensor and phase."""

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

        if user_input is not None:
            data = {
                CONF_NAME: user_input[CONF_NAME],
                CONF_SENSOR: user_input[CONF_SENSOR],
                CONF_PHASE: user_input.get(CONF_PHASE, PHASE_NONE),
            }
            errors = self._validate_sensor(entry, data[CONF_SENSOR], current)
            if not errors:
                if current is None:
                    return self.async_create_entry(
                        title=data[CONF_NAME], data=data, unique_id=data[CONF_SENSOR]
                    )
                return self.async_update_and_abort(
                    entry,
                    current,
                    title=data[CONF_NAME],
                    data=data,
                    unique_id=data[CONF_SENSOR],
                )

        schema: dict[Any, Any] = {
            vol.Required(CONF_NAME): TextSelector(),
            vol.Required(CONF_SENSOR): PHASE_SENSOR_SELECTOR,
        }
        if three_phase:
            schema[vol.Required(CONF_PHASE, default=PHASE_NONE)] = SelectSelector(
                SelectSelectorConfig(
                    options=[PHASE_NONE, *PHASE_IDS],
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key=CONF_PHASE,
                )
            )
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
        if sensor in grid_sensors(dict(entry.data)):
            return {CONF_SENSOR: "sensor_is_phase_sensor"}
        for subentry in entry.subentries.values():
            if current is not None and subentry.subentry_id == current.subentry_id:
                continue
            if subentry.data.get(CONF_SENSOR) == sensor:
                return {CONF_SENSOR: "sensor_in_use"}
        return {}


class PvSourceSubentryFlow(_MeasuredDeviceSubentryFlow):
    """Add or change a PV production measurement."""


class ExcludedLoadSubentryFlow(_MeasuredDeviceSubentryFlow):
    """Add or change a device excluded from house consumption."""
