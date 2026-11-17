"""Constants for HomeBatteryAssist."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "homebatteryassist"
NAME: Final = "HomeBatteryAssist"

# Grid connection
CONF_PHASES: Final = "phases"
CONF_MAX_CURRENT: Final = "max_current_per_phase"
CONF_METER_SOURCE: Final = "meter_source"  # sensors (default) or a direct meter
CONF_METER_ADDRESS: Final = "meter_address"  # IP address of a direct meter

PHASE_OPTIONS: Final = (1, 3)

# Standard (Dutch) grid connections: main fuse rating in A per phase count.
MAX_CURRENT_OPTIONS: Final[dict[int, tuple[int, ...]]] = {
    1: (10, 25, 35),
    3: (25, 35, 50, 63, 80),
}
# Most common connection per phase count (1x35A, 3x25A).
DEFAULT_MAX_CURRENT: Final[dict[int, int]] = {1: 35, 3: 25}

# Nominal grid voltage, used to convert current (A) measurements to power (W).
NOMINAL_VOLTAGE: Final = 230.0

# Interval (minutes) at which house consumption is aggregated for forecasting.
CONF_HISTORY_INTERVAL: Final = "history_interval"
HISTORY_INTERVAL_OPTIONS: Final = (5, 15, 60)
DEFAULT_HISTORY_INTERVAL: Final = 15
HISTORY_RETENTION: Final = timedelta(days=28)

# Planning: the configured maximum horizon. The effective horizon is further
# limited by how far the price and PV forecasts reach.
CONF_PLANNING_HORIZON: Final = "planning_horizon_days"
MIN_PLANNING_HORIZON: Final = 1
MAX_PLANNING_HORIZON: Final = 7
DEFAULT_PLANNING_HORIZON: Final = 2

# Forecast inputs, provided by other integrations:
# - a sensor entity whose attributes contain the (day-ahead) price forecast
# - config entries of integrations offering a solar forecast to the Energy
#   dashboard (Forecast.Solar, Solcast, Open-Meteo Solar Forecast, ...)
CONF_PRICE_FORECAST: Final = "price_forecast_entity"
# Optional: outdoor temperature for the consumption forecast.
CONF_WEATHER_ENTITY: Final = "weather_entity"  # weather.* with a forecast
CONF_OUTDOOR_TEMPERATURE: Final = "outdoor_temperature_sensor"  # sensor, °C/°F
# Per heating/cooling device (a zone, e.g. a room): its room temperature, and
# optionally its own outdoor temperature (CONF_OUTDOOR_TEMPERATURE).
CONF_INDOOR_TEMPERATURE: Final = "indoor_temperature_sensor"
CONF_PV_FORECAST: Final = "pv_forecast_entries"
# Battery plan (advice): mode and cost assumptions.
CONF_PLAN_MODE: Final = "plan_mode"
CONF_CONSUMPTION_FORECASTER: Final = "consumption_forecaster"
CONF_TARIFF: Final = "tariff"
CONF_EXPORT_FACTOR: Final = "export_price_factor"
CONF_EXPORT_MODE: Final = "export_price_mode"
CONF_PRICE_SOURCE: Final = "price_source"  # "<driver>:<source>" or "sensor"
CONF_PRICE_EXTENSION: Final = "price_extension"  # extra forecast or "none"
PRICE_SOURCE_SENSOR: Final = "sensor"  # the price sensor field
PRICE_EXTENSION_NONE: Final = "none"
CONF_MAX_CYCLES: Final = "max_cycles_per_day"
CONF_PV_MARGIN: Final = "pv_forecast_margin"
CONF_PV_CORRECTION: Final = "pv_correction"
CONF_PV_CORRECTOR: Final = "pv_corrector"  # PV correction module (learned)
PV_CORRECTION_AUTO: Final = "auto"  # learned from past forecasts
PV_CORRECTION_FIXED: Final = "fixed"  # only the fixed margin (%)
PV_CORRECTION_BOTH: Final = "both"
PV_CORRECTION_OFF: Final = "off"
PV_CORRECTION_MODES: Final = (
    PV_CORRECTION_BOTH,
    PV_CORRECTION_AUTO,
    PV_CORRECTION_FIXED,
    PV_CORRECTION_OFF,
)
CONF_PEAK_LIMIT: Final = "peak_limit_w"
CONF_PEAK_INCLUDE_EXCLUDED: Final = "peak_include_excluded"
# Short peaks (kettle, microwave): a spike filter module recognises them;
# random ones are left out of the average and/or not covered by the battery.
CONF_SPIKE_FILTER: Final = "spike_filter"
CONF_SPIKE_HISTORY: Final = "spike_exclude_average"
CONF_SPIKE_BATTERY: Final = "spike_no_discharge"
CONF_SPIKE_THRESHOLD: Final = "spike_threshold_w"
CONF_SPIKE_DURATION: Final = "spike_max_minutes"
DEFAULT_SPIKE_THRESHOLD: Final = 2000  # W above the usual consumption
DEFAULT_SPIKE_DURATION: Final = 5  # minutes at most
CONF_RESERVE_SOC: Final = "reserve_soc"  # % never planned below (backup reserve)
CONF_SYSTEM_MAX_CHARGE: Final = "system_max_charge_w"  # all batteries, 0 = off
CONF_SYSTEM_MAX_DISCHARGE: Final = "system_max_discharge_w"
CONF_NOM_TARGET: Final = "nom_target_w"  # grid power NOM aims at
CONF_MIN_DISCHARGE_PRICE: Final = "min_discharge_price"  # optional
CONF_MAX_CHARGE_PRICE: Final = "max_charge_price"  # optional
CONF_MIN_MARGIN: Final = "min_arbitrage_margin"  # per kWh
CONF_CHARGE_HYSTERESIS: Final = "charge_hysteresis"  # % below max before recharging
CONF_VACATION: Final = "vacation"  # do not learn the house consumption
CONF_NOTIFY_TARGETS: Final = "notify_targets"  # notify services / persistent
CONF_NOTIFY_KINDS: Final = "notify_kinds"  # which decisions
CONF_FULL_CHARGE_DAY: Final = "full_charge_day"  # "none" or mon..sun
CONF_FULL_CHARGE_SOLAR: Final = "full_charge_solar"  # prefer solar surplus
CONF_TEMPERATURE_SENSOR: Final = "temperature_sensor"
CONF_TEMP_LIMIT: Final = "temperature_limit"  # °C, full power up to here
CONF_TEMP_BAND: Final = "temperature_band"  # °C over which power is reduced
CONF_TEMP_MIN_POWER: Final = "temperature_min_power"  # % of max power at the end
CONF_TEMP_DISCHARGE: Final = "temperature_discharge"  # also reduce discharging
CONF_MANUAL_POWER: Final = "manual_power_w"  # + charge / - discharge
DEFAULT_MANUAL_POWER: Final = 0
SUBENTRY_TIME_SLOT: Final = "time_slot"
DEFAULT_PEAK_LIMIT: Final = 0  # W grid import (all phases); 0 = no peak shaving
DEFAULT_PV_MARGIN: Final = 0  # % of the PV forecast the plan does not count on
DEFAULT_MAX_CYCLES: Final = 1.0  # full cycles per day for arbitrage (0 = no limit)
CONF_EXPORT_ENTITIES: Final = "export_price_entities"
EXPORT_FACTOR: Final = "factor"  # import price x factor
EXPORT_SENSOR: Final = "sensor"  # export price forecast from sensor(s)
EXPORT_MARKET: Final = "market"  # bare market price (EPEX) from sensor(s)
EXPORT_MODES: Final = (EXPORT_FACTOR, EXPORT_MARKET, EXPORT_SENSOR)
DEFAULT_EXPORT_MODE: Final = EXPORT_MARKET
CONF_CYCLE_COST: Final = "cycle_cost"
# No net metering (NL: ends 1 January 2027): export earns far less than the
# import price. 1.0 would mean net metering.
DEFAULT_EXPORT_FACTOR: Final = 0.25
# Realised battery value without net metering, with the energy behind it for
# its wear (basis 3); counters of an older basis are reset once.
VALUE_BASIS: Final = 3
DEFAULT_CYCLE_COST: Final = 0.02  # per kWh through the battery
# Below this power per battery conversion losses are high: use fewer batteries.
CONF_MIN_BATTERY_POWER: Final = "min_battery_power"
DEFAULT_MIN_BATTERY_POWER: Final = 300  # W
CONF_PHASE_MARGIN: Final = "phase_margin"
DEFAULT_PHASE_MARGIN: Final = 10  # % of the fuse rating kept free per phase
# A due full charge is forced at the cheapest moment within this many days.
CONF_FULL_CHARGE_WINDOW: Final = "full_charge_window_days"
DEFAULT_FULL_CHARGE_WINDOW: Final = 3
# How often to check whether another battery should take over (balance).
CONF_BALANCE_INTERVAL: Final = "balance_interval"
BALANCE_INTERVAL_OPTIONS: Final = (15, 30, 60, 120)
DEFAULT_BALANCE_INTERVAL: Final = 60  # minutes

# How often the forecasts are recalculated (minutes).
CONF_FORECAST_INTERVAL: Final = "forecast_interval"
FORECAST_INTERVAL_OPTIONS: Final = (5, 15, 30, 60)
DEFAULT_FORECAST_INTERVAL: Final = 15
FORECAST_UPDATE_INTERVAL: Final = timedelta(minutes=DEFAULT_FORECAST_INTERVAL)

# Per-phase grid measurement sensors (power in W or current in A).
# Either one signed sensor per phase (+ import / - export), or an import sensor
# plus an optional separate export (return) sensor.
CONF_PHASE_SENSORS: Final = ("sensor_l1", "sensor_l2", "sensor_l3")
CONF_PHASE_RETURN_SENSORS: Final = ("return_l1", "return_l2", "return_l3")

# Subentries (any number of each), each with a name, sensor and optional phase:
# - a PV production measurement (added to the grid measurement)
# - a device excluded from house consumption, e.g. an EV charger (subtracted)
SUBENTRY_PV_SOURCE: Final = "pv_source"
SUBENTRY_EXCLUDED_LOAD: Final = "excluded_load"
# Heating/cooling (heat pump, airco): part of the house, measured apart.
SUBENTRY_HEATING_COOLING: Final = "heating_cooling"
CONF_SENSOR: Final = "sensor"
CONF_PHASE: Final = "phase"
CONF_PV_DRIVER: Final = "pv_driver"  # "sensor" or a meter driver key
# An external meter on a battery's line (+ = into the battery, charging)
CONF_BATTERY_METER: Final = "battery_meter"  # "none" or a meter driver key
CONF_BATTERY_METER_ADDRESS: Final = "battery_meter_address"
BATTERY_METER_NONE: Final = "none"
CONF_PV_ADDRESS: Final = "pv_address"  # address of a directly read PV meter
PV_DRIVER_SENSOR: Final = "sensor"
# Optional per-phase sensors of a 3-phase device (PV inverter, EV charger)
CONF_DEVICE_PHASE_SENSORS: Final = (
    "phase_sensor_l1",
    "phase_sensor_l2",
    "phase_sensor_l3",
)
PHASE_NONE: Final = "none"
PHASE_IDS: Final = ("l1", "l2", "l3")

# Subentry: a home battery, linked (read-only) through entities of its own
# integration. HomeBatteryAssist never controls batteries.
SUBENTRY_BATTERY: Final = "battery"
# Subentry: a virtual battery, simulated live (what-if; the only kind of battery
# HomeBatteryAssist "controls", because it is not a device).
SUBENTRY_VIRTUAL_BATTERY: Final = "virtual_battery"
CONF_INITIAL_SOC: Final = "initial_soc"
DEFAULT_INITIAL_SOC: Final = 50
# Round-trip loss of a virtual battery: random per simulation step between
# min and max (%); the planner uses the average.
CONF_LOSS_MIN: Final = "loss_min"
CONF_LOSS_MAX: Final = "loss_max"
DEFAULT_LOSS_MIN: Final = 10
DEFAULT_LOSS_MAX: Final = 20
# Reading
CONF_SOC_SENSOR: Final = "soc_sensor"  # state of charge, %
CONF_POWER_SENSOR: Final = "power_sensor"  # W or A
CONF_POWER_SIGN: Final = "power_sign"
SIGN_CHARGING_POSITIVE: Final = "charging_positive"
SIGN_DISCHARGING_POSITIVE: Final = "discharging_positive"
# Properties for forecasting / planning
CONF_CAPACITY: Final = "capacity_kwh"
CONF_MAX_CHARGE_POWER: Final = "max_charge_power"  # W
CONF_MAX_DISCHARGE_POWER: Final = "max_discharge_power"  # W
CONF_MIN_SOC: Final = "min_soc"  # %
CONF_MAX_SOC: Final = "max_soc"  # %
CONF_EFFICIENCY: Final = "round_trip_efficiency"  # %
CONF_FULL_CHARGE_INTERVAL: Final = "full_charge_interval_days"  # 0 = off
DEFAULT_MIN_SOC: Final = 10
DEFAULT_MAX_SOC: Final = 100
DEFAULT_EFFICIENCY: Final = 90
DEFAULT_FULL_CHARGE_INTERVAL: Final = 28
# Monitoring
IDLE_THRESHOLD_W: Final = 20.0  # |power| below this counts as idle
FULL_CHARGE_SOC: Final = 99.5  # % at or above which a full charge is registered
BATTERY_SENSOR_KEYS: Final = (CONF_SOC_SENSOR, CONF_POWER_SENSOR)
CONF_SOURCE: Final = "source"  # battery flow: detected device or manual
SOURCE_MANUAL: Final = "manual"


def phase_index(phase: str, phases: int) -> int | None:
    """Index of the phase a device is on; None = spread over all phases.

    On a 1-phase connection everything is on that phase.
    """
    if phases == 1:
        return 0
    return PHASE_IDS.index(phase) if phase in PHASE_IDS[:phases] else None


def phase_sensor_keys(phases: int) -> tuple[str, ...]:
    """Return the config keys for the measurement sensors of each phase."""
    return CONF_PHASE_SENSORS[:phases]


def phase_return_sensor_keys(phases: int) -> tuple[str, ...]:
    """Return the config keys for the optional export sensors of each phase."""
    return CONF_PHASE_RETURN_SENSORS[:phases]
