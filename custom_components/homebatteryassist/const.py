"""Constants for HomeBatteryAssist."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "homebatteryassist"
NAME: Final = "HomeBatteryAssist"

# Grid connection
CONF_PHASES: Final = "phases"
CONF_MAX_CURRENT: Final = "max_current_per_phase"

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
CONF_PV_FORECAST: Final = "pv_forecast_entries"
# Battery plan (advice): mode and cost assumptions.
CONF_PLAN_MODE: Final = "plan_mode"
CONF_EXPORT_FACTOR: Final = "export_price_factor"
CONF_CYCLE_COST: Final = "cycle_cost"
DEFAULT_EXPORT_FACTOR: Final = 1.0  # export earns the import price (net metering)
DEFAULT_CYCLE_COST: Final = 0.02  # per kWh through the battery
# Below this power per battery conversion losses are high: use fewer batteries.
CONF_MIN_BATTERY_POWER: Final = "min_battery_power"
DEFAULT_MIN_BATTERY_POWER: Final = 300  # W
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
CONF_SENSOR: Final = "sensor"
CONF_PHASE: Final = "phase"
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
DEFAULT_FULL_CHARGE_INTERVAL: Final = 0
# Monitoring
IDLE_THRESHOLD_W: Final = 20.0  # |power| below this counts as idle
FULL_CHARGE_SOC: Final = 99.5  # % at or above which a full charge is registered
BATTERY_SENSOR_KEYS: Final = (CONF_SOC_SENSOR, CONF_POWER_SENSOR)
CONF_SOURCE: Final = "source"  # battery flow: detected device or manual
SOURCE_MANUAL: Final = "manual"


def phase_sensor_keys(phases: int) -> tuple[str, ...]:
    """Return the config keys for the measurement sensors of each phase."""
    return CONF_PHASE_SENSORS[:phases]


def phase_return_sensor_keys(phases: int) -> tuple[str, ...]:
    """Return the config keys for the optional export sensors of each phase."""
    return CONF_PHASE_RETURN_SENSORS[:phases]
