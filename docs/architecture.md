# Architecture: layers, drivers and modules

HomeBatteryAssist is built in layers. Data flows one way, from the devices to the explanation; a layer only uses the layers below it.

| # | Layer | What it does | Folder |
|---|---|---|---|
| 1 | **Devices** | Talks to the physical devices — read-only | `engine/devices/` |
| 2 | **External sources** | Prices, PV forecasts, tariffs | `engine/sources/` |
| 3 | **Measuring** | The house *now*: consumption, grid per phase, battery states and counters | `engine/measure/` |
| 4 | **History** | The past: consumption per interval, import of older data | `engine/history/` |
| 5 | **Forecasting** | The future: the planning window and the consumption forecast | `engine/forecast/` |
| 6 | **Planning** | Deciding: planners, the final check, full charges, phase limits, several batteries | `engine/planning/` |
| 7 | **Evaluation** | Afterwards: forecast accuracy, plan versus what happened | `engine/evaluation/` |
| 8 | **Explanation** | The *Why* texts and notifications | `engine/explain/` |
| – | **Home Assistant** | Entities, dashboard, settings, actions | package root (`output/`, `frontend/`, `config_flow.py`, …) |

`engine/coordinator.py` runs one cycle through the layers (by default every 15 minutes, and when new prices arrive).

## Drivers and modules

- **Drivers** connect HomeBatteryAssist to *devices* (layer 1). They are part of the code; a new one is added through a pull request. → [Drivers](drivers.md)
- **Modules** are the swappable parts of the *other* layers. The built-in ones live in their layer; advanced users can add their own in `/config/homebatteryassist/<kind>/` and choose them in the settings, while HomeBatteryAssist keeps the final say. → [Modules](modules.md)

Every extension point has the same shape: `base.py` (the interface), `template.py` (an example, never offered) and one file per built-in variant.

## Folder map

```
custom_components/homebatteryassist/
├── __init__.py, config_flow.py, services.py, diagnostics.py, sensor.py, button.py
├── output/            entities and the dashboard's data
├── frontend/          the dashboard (panel.js)
├── strings.json, translations/
└── engine/
    ├── coordinator.py     one cycle through the layers
    ├── units.py           unit conversion
    ├── own_modules.py     loading own modules from /config
    ├── devices/           1  drivers
    │   ├── batteries/     base.py, template.py, virtual.py (simulation), recognition.py,
    │   │                  marstek/ (__init__.py brand → venus.py → venus_e_v3.py),
    │   │                  integrations/ (entity_reader.py, omnibattery.py, marstek_modbus.py)
    │   └── meters/        base.py, template.py, homewizard.py, sma.py, shelly.py,
    │                      iammeter.py, direct_reading.py, discovery.py,
    │                      via_ha_integration.py
    ├── sources/           2  modules
    │   ├── prices/        base.py, template.py, price_points.py, dyntarnl.py,
    │   │                  ha_price_actions.py, sensor_attributes.py, regional.py,
    │   │                  price_forecasts.py, in_development/ (tibber.py)
    │   ├── pv_forecasts/  base.py, template.py, solar_forecast_integrations.py,
    │   │                  energy_dashboard_platform.py
    │   └── tariffs/       base.py, template.py, as_price_source.py
    ├── measure/           3  house_measurement.py, battery_monitor.py
    ├── history/           4  consumption_history.py, history_import.py, chart_series.py
    ├── forecast/          5  planning_window.py, consumption_forecast.py,
    │                         user_adjustments.py, phase_shares.py,
    │                         forecasters/ (base.py, template.py, weekday_hour_profile.py,
    │                                       same_time_last_weeks.py)
    ├── planning/          6  battery_plan.py (final check), full_charge.py, phase_limit.py,
    │                         battery_distribution.py, time_slots.py,
    │                         planners/ (base.py, template.py, zero_on_meter.py, arbitrage.py)
    ├── evaluation/        7  forecast_accuracy.py, plan_check.py
    └── explain/           8  messages.py, plan_story.py, decision_log.py, notifications.py
```

## Batteries: model and reader

A battery driver has two parts:

- a **model** — what the battery *is* — organised by inheritance as **brand → type range → type**: `marstek/__init__.py` (Marstek) → `marstek/venus.py` (Venus) → `marstek/venus_e_v3.py` (Venus E v3). A type inherits from its range and brand and only sets its own specifications (capacity, power, usable part, rated cycles, warranty);
- a **reader** — how the battery is *read* — one per integration that exposes batteries (`integrations/omnibattery.py`, `integrations/marstek_modbus.py`).

So one battery type can be read through several integrations. The **virtual battery** (`virtual.py`) is a simulated device that follows the plan.

## Meters

One file per brand (`homewizard.py`, `sma.py`, `shelly.py`, `iammeter.py`), sharing `direct_reading.py` (reading about once a second, a value going stale). Meters can also be read through their own Home Assistant integration (`via_ha_integration.py`).
