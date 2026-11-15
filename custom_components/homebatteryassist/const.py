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
FORECAST_UPDATE_INTERVAL: Final = timedelta(minutes=15)

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


def phase_sensor_keys(phases: int) -> tuple[str, ...]:
    """Return the config keys for the measurement sensors of each phase."""
    return CONF_PHASE_SENSORS[:phases]


def phase_return_sensor_keys(phases: int) -> tuple[str, ...]:
    """Return the config keys for the optional export sensors of each phase."""
    return CONF_PHASE_RETURN_SENSORS[:phases]
