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
    BALANCE_INTERVAL_OPTIONS,
    BATTERY_SENSOR_KEYS,
    CONF_BALANCE_INTERVAL,
    CONF_CAPACITY,
    CONF_CYCLE_COST,
    CONF_EFFICIENCY,
    CONF_EXPORT_ENTITIES,
    CONF_EXPORT_FACTOR,
    CONF_EXPORT_MODE,
    CONF_FORECAST_INTERVAL,
    CONF_FULL_CHARGE_INTERVAL,
    CONF_FULL_CHARGE_WINDOW,
    CONF_HISTORY_INTERVAL,
    CONF_INITIAL_SOC,
    CONF_LOSS_MAX,
    CONF_LOSS_MIN,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_CURRENT,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_SOC,
    CONF_METER_ADDRESS,
    CONF_METER_SOURCE,
    CONF_MIN_BATTERY_POWER,
    CONF_MIN_SOC,
    CONF_PHASE,
    CONF_PHASE_MARGIN,
    CONF_PHASES,
    CONF_PLAN_MODE,
    CONF_PLANNING_HORIZON,
    CONF_POWER_SENSOR,
    CONF_POWER_SIGN,
    CONF_PRICE_FORECAST,
    CONF_PV_FORECAST,
    CONF_SENSOR,
    CONF_SOC_SENSOR,
    CONF_SOURCE,
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
    DEFAULT_MAX_CURRENT,
    DEFAULT_MAX_SOC,
    DEFAULT_MIN_BATTERY_POWER,
    DEFAULT_MIN_SOC,
    DEFAULT_PHASE_MARGIN,
    DEFAULT_PLANNING_HORIZON,
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
    SIGN_CHARGING_POSITIVE,
    SIGN_DISCHARGING_POSITIVE,
    SOURCE_MANUAL,
    SUBENTRY_BATTERY,
    SUBENTRY_EXCLUDED_LOAD,
    SUBENTRY_PV_SOURCE,
    SUBENTRY_VIRTUAL_BATTERY,
    phase_return_sensor_keys,
    phase_sensor_keys,
)
from .inputs.direct import (
    SOURCE_HOMEWIZARD,
    SOURCE_SHELLY,
    SOURCE_SPEEDWIRE,
    discover_speedwire,
    shelly_3em_hosts,
)
from .inputs.meters import MeterCandidate, find_meter_candidates
from .inputs.profiles import BatteryCandidate, find_battery_candidates
from .inputs.solar import async_solar_forecast_entries
from .planning.battery_plan import DEFAULT_PLAN_MODE, PLAN_MODES

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
        vol.Optional(CONF_PRICE_FORECAST): EntitySelector(
            EntitySelectorConfig(domain="sensor")
        ),
        vol.Required(
            CONF_PLAN_MODE, default=current.get(CONF_PLAN_MODE, DEFAULT_PLAN_MODE)
        ): SelectSelector(
            SelectSelectorConfig(
                options=list(PLAN_MODES),
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_PLAN_MODE,
            )
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
            NumberSelectorConfig(min=0, max=1.5, step=0.05, mode=NumberSelectorMode.BOX)
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
                min=0, max=0.5, step=0.005, mode=NumberSelectorMode.BOX
            )
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


# Settings shown as a (single) select: their values are strings in the form.
SELECT_OPTIONS = (CONF_HISTORY_INTERVAL, CONF_FORECAST_INTERVAL, CONF_BALANCE_INTERVAL)


def settings_from_input(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Convert the settings form input to stored options."""
    options: dict[str, Any] = {
        CONF_HISTORY_INTERVAL: int(user_input[CONF_HISTORY_INTERVAL]),
        CONF_PLANNING_HORIZON: int(user_input[CONF_PLANNING_HORIZON]),
        CONF_FORECAST_INTERVAL: int(
            user_input.get(CONF_FORECAST_INTERVAL, DEFAULT_FORECAST_INTERVAL)
        ),
        CONF_PLAN_MODE: user_input.get(CONF_PLAN_MODE, DEFAULT_PLAN_MODE),
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
    options[CONF_EXPORT_MODE] = user_input.get(CONF_EXPORT_MODE, DEFAULT_EXPORT_MODE)
    if user_input.get(CONF_EXPORT_ENTITIES):
        options[CONF_EXPORT_ENTITIES] = list(user_input[CONF_EXPORT_ENTITIES])
    if user_input.get(CONF_PV_FORECAST):
        options[CONF_PV_FORECAST] = list(user_input[CONF_PV_FORECAST])
    return options


def _direct_key(source: str | None, address: str | None) -> str:
    return f"direct:{source}:{address}"


def _direct_options(
    meters: list[MeterCandidate],
    speedwire: dict[str, int],
    shelly: dict[str, str],
) -> dict[str, tuple[str, str, int | None]]:
    """Meters that can be read directly: key -> (source, address, phases)."""
    options: dict[str, tuple[str, str, int | None]] = {}
    for meter in meters:
        if meter.profile.direct and meter.address:
            key = _direct_key(meter.profile.direct, meter.address)
            options[key] = (meter.profile.direct, meter.address, meter.phases)
    for address in sorted(shelly):
        options[_direct_key(SOURCE_SHELLY, address)] = (SOURCE_SHELLY, address, None)
    for address in sorted(speedwire):
        options[_direct_key(SOURCE_SPEEDWIRE, address)] = (
            SOURCE_SPEEDWIRE,
            address,
            None,
        )
    return options


def _direct_label(key: str, dutch: bool) -> str:
    _, source, address = key.split(":", 2)
    name = {
        SOURCE_HOMEWIZARD: "HomeWizard P1",
        SOURCE_SPEEDWIRE: "SMA Home Manager / Energy Meter",
        SOURCE_SHELLY: "Shelly 3EM",
    }.get(source, source)
    how = (
        "rechtstreeks, elke seconde, alleen lezen"
        if dutch
        else "read directly, every second, read-only"
    )
    return f"{name} {address} ({how})"


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
        self._direct: dict[str, tuple[str, str, int | None]] = {}
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
                found, await discover_speedwire(self.hass), shelly_3em_hosts(self.hass)
            )
            if self._meters or self._direct:
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
            if direct := self._direct.get(choice):
                source, address, phases = direct
                self._from_meter = True
                self._data = {
                    **{k: v for k, v in self._data.items() if k == CONF_MAX_CURRENT},
                    CONF_METER_SOURCE: source,
                    CONF_METER_ADDRESS: address,
                }
                if phases:
                    self._data[CONF_PHASES] = phases
                    return await self.async_step_max_current()
                return await self._async_ask_phases()
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

        default = next(iter(self._direct), None) or next(iter(self._meters))
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
                                        value=key, label=_direct_label(key, dutch)
                                    )
                                    for key in self._direct
                                ),
                                *(
                                    SelectOptionDict(value=c.device_id, label=c.label)
                                    for c in self._meters.values()
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
            SUBENTRY_VIRTUAL_BATTERY: VirtualBatterySubentryFlow,
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
        return self.async_show_menu(step_id="init", menu_options=["settings", "grid"])

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change interval, planning horizon, forecast inputs and battery settings."""
        if user_input is not None:
            return self.async_create_entry(data=settings_from_input(user_input))

        current = self.config_entry.options
        schema = await settings_schema(self.hass, current)
        # Select fields hold strings; stored options may be numbers.
        suggested = {
            key: str(value) if key in SELECT_OPTIONS and value is not None else value
            for key, value in current.items()
        }
        return self.async_show_form(
            step_id="settings",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
        )

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
