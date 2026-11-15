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
- battery:       a home battery, linked through entities of its own integration.
  Steps: battery (reading + properties) -> control -> modes (if a mode select
  is used).

A sensor can only be used once: as grid sensor or by one subentry.
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
    BATTERY_SENSOR_KEYS,
    CONF_CAPACITY,
    CONF_CHARGE_ENTITY,
    CONF_CONTROL_TYPE,
    CONF_DISCHARGE_ENTITY,
    CONF_EFFICIENCY,
    CONF_FULL_CHARGE_INTERVAL,
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_CURRENT,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_MODE_CHARGE,
    CONF_MODE_DISCHARGE,
    CONF_MODE_ENTITY,
    CONF_MODE_IDLE,
    CONF_PHASE,
    CONF_PHASES,
    CONF_PLANNING_HORIZON,
    CONF_POWER_SENSOR,
    CONF_POWER_SIGN,
    CONF_PRICE_FORECAST,
    CONF_PV_FORECAST,
    CONF_SENSOR,
    CONF_SETPOINT_ENTITY,
    CONF_SETPOINT_SIGN,
    CONF_SOC_SENSOR,
    CONTROL_NONE,
    CONTROL_SEPARATE,
    CONTROL_SETPOINT,
    CONTROL_TYPES,
    DEFAULT_EFFICIENCY,
    DEFAULT_FULL_CHARGE_INTERVAL,
    DEFAULT_HISTORY_INTERVAL,
    DEFAULT_MAX_CURRENT,
    DEFAULT_MAX_SOC,
    DEFAULT_MIN_SOC,
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
    SIGN_CHARGING_POSITIVE,
    SIGN_DISCHARGING_POSITIVE,
    SUBENTRY_BATTERY,
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


def grid_sensors(data: Mapping[str, Any]) -> set[str]:
    """Return all grid sensors (import and return) configured in ``data``."""
    keys = (*phase_sensor_keys(3), *phase_return_sensor_keys(3))
    return {data[key] for key in keys if data.get(key)}


SUBENTRY_SENSOR_KEYS = (CONF_SENSOR, *BATTERY_SENSOR_KEYS)


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
        """Return the subentry types: PV sources, excluded loads, batteries."""
        return {
            SUBENTRY_PV_SOURCE: PvSourceSubentryFlow,
            SUBENTRY_EXCLUDED_LOAD: ExcludedLoadSubentryFlow,
            SUBENTRY_BATTERY: BatterySubentryFlow,
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
            schema[vol.Required(CONF_PHASE, default=PHASE_NONE)] = phase_selector()
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
CONTROL_NUMBER_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain=["number", "input_number"])
)


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
    }
    if three_phase:
        schema[vol.Required(CONF_PHASE, default=PHASE_NONE)] = phase_selector()
    return vol.Schema(schema)


CONTROL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CONTROL_TYPE, default=CONTROL_NONE): SelectSelector(
            SelectSelectorConfig(
                options=list(CONTROL_TYPES),
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_CONTROL_TYPE,
            )
        ),
        vol.Optional(CONF_SETPOINT_ENTITY): CONTROL_NUMBER_SELECTOR,
        vol.Required(CONF_SETPOINT_SIGN, default=SIGN_CHARGING_POSITIVE): _select(
            SIGN_OPTIONS, CONF_POWER_SIGN
        ),
        vol.Optional(CONF_CHARGE_ENTITY): CONTROL_NUMBER_SELECTOR,
        vol.Optional(CONF_DISCHARGE_ENTITY): CONTROL_NUMBER_SELECTOR,
        vol.Optional(CONF_MODE_ENTITY): EntitySelector(
            EntitySelectorConfig(domain=["select", "input_select"])
        ),
    }
)

MODE_KEYS = (CONF_MODE_CHARGE, CONF_MODE_DISCHARGE, CONF_MODE_IDLE)


class BatterySubentryFlow(ConfigSubentryFlow):
    """Add or change a home battery: reading, properties and control."""

    def __init__(self) -> None:
        """Initialize."""
        self._data: dict[str, Any] = {}

    def _current(self) -> ConfigSubentry | None:
        return (
            self._get_reconfigure_subentry() if self.source == "reconfigure" else None
        )

    def _suggested(self, user_input: dict[str, Any] | None) -> dict[str, Any] | None:
        if user_input is not None:
            return user_input
        current = self._current()
        return dict(current.data) if current else None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a battery."""
        return await self._async_step_battery("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change a battery."""
        return await self._async_step_battery("reconfigure", user_input)

    async def _async_step_battery(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        """Step 1: name, sensors and properties."""
        entry = self._get_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            for key in BATTERY_SENSOR_KEYS:
                if error := sensor_conflict(entry, user_input[key], self._current()):
                    errors[key] = error
            if user_input[CONF_SOC_SENSOR] == user_input[CONF_POWER_SENSOR]:
                errors[CONF_POWER_SENSOR] = "sensor_in_use"
            if user_input[CONF_MIN_SOC] >= user_input[CONF_MAX_SOC]:
                errors[CONF_MAX_SOC] = "soc_range"
            if not errors:
                self._data = {
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
                return await self.async_step_control()

        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                battery_schema(entry.data[CONF_PHASES] == 3),
                self._suggested(user_input),
            ),
            errors=errors,
        )

    async def async_step_control(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Step 2: how the battery can be controlled (optional)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            control_type = user_input[CONF_CONTROL_TYPE]
            if control_type == CONTROL_SETPOINT and not user_input.get(
                CONF_SETPOINT_ENTITY
            ):
                errors[CONF_SETPOINT_ENTITY] = "control_entity_required"
            if control_type == CONTROL_SEPARATE:
                for key in (CONF_CHARGE_ENTITY, CONF_DISCHARGE_ENTITY):
                    if not user_input.get(key):
                        errors[key] = "control_entity_required"
            if not errors:
                self._data.update(self._control_data(user_input))
                if self._data.get(CONF_MODE_ENTITY):
                    return await self.async_step_modes()
                return self._async_finish()

        return self.async_show_form(
            step_id="control",
            data_schema=self.add_suggested_values_to_schema(
                CONTROL_SCHEMA, self._suggested(user_input)
            ),
            errors=errors,
            description_placeholders={"name": self._data[CONF_NAME]},
        )

    async def async_step_modes(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Step 3: which option of the mode select means charge/discharge/idle."""
        if user_input is not None:
            self._data.update({k: v for k, v in user_input.items() if v})
            return self._async_finish()

        mode_entity = self._data[CONF_MODE_ENTITY]
        state = self.hass.states.get(mode_entity)
        options = list(state.attributes.get("options", [])) if state else []
        selector: Any = (
            SelectSelector(
                SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
            )
            if options
            else TextSelector()
        )
        return self.async_show_form(
            step_id="modes",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Optional(key): selector for key in MODE_KEYS}),
                self._suggested(None),
            ),
            description_placeholders={"entity": mode_entity},
        )

    @staticmethod
    def _control_data(user_input: dict[str, Any]) -> dict[str, Any]:
        """Keep only the control entities that belong to the chosen type."""
        control_type = user_input[CONF_CONTROL_TYPE]
        data: dict[str, Any] = {CONF_CONTROL_TYPE: control_type}
        if control_type == CONTROL_SETPOINT:
            data[CONF_SETPOINT_ENTITY] = user_input[CONF_SETPOINT_ENTITY]
            data[CONF_SETPOINT_SIGN] = user_input[CONF_SETPOINT_SIGN]
        elif control_type == CONTROL_SEPARATE:
            data[CONF_CHARGE_ENTITY] = user_input[CONF_CHARGE_ENTITY]
            data[CONF_DISCHARGE_ENTITY] = user_input[CONF_DISCHARGE_ENTITY]
        if control_type != CONTROL_NONE and user_input.get(CONF_MODE_ENTITY):
            data[CONF_MODE_ENTITY] = user_input[CONF_MODE_ENTITY]
        return data

    @callback
    def _async_finish(self) -> SubentryFlowResult:
        title = self._data[CONF_NAME]
        unique_id = self._data[CONF_POWER_SENSOR]
        if (current := self._current()) is None:
            return self.async_create_entry(
                title=title, data=self._data, unique_id=unique_id
            )
        return self.async_update_and_abort(
            self._get_entry(),
            current,
            title=title,
            data=self._data,
            unique_id=unique_id,
        )
