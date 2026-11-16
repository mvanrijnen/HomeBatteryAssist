# Working with other integrations

HomeBatteryAssist never controls anything, so it can run next to any battery or energy integration (e.g. Omnibattery) without interfering.

## Sensors

The sensors have a fixed meaning and can be used by other integrations and add-ons: *Grid power* (+ import / − export), *Grid import*, *Grid export*, *PV power*, *House consumption*, the battery sensors and the *Battery plan*.

## Actions

| Action | What it does |
|---|---|
| `homebatteryassist.recalculate` | Recalculate the forecasts and plans now (also the *Recalculate* button). |
| `homebatteryassist.import_history` | Import past consumption once from Home Assistant's statistics. |
| `homebatteryassist.adjust_forecast` / `clear_forecast_adjustments` | Adjust the consumption forecast for a period (e.g. a party or a holiday). |
| `homebatteryassist.set_forecast_correction` / `reset_forecast_accuracy` | Control the learned forecast corrections. |
| `homebatteryassist.set_plan_mode` | Choose the plan mode: a built-in one or an own planner (`custom_<key>`). |

## Events

`homebatteryassist_forecast_updated` (after every forecast cycle) and `homebatteryassist_decision` (every explained decision).

## Why did it do that? Logging

- **Last decision** sensor: a short explanation in your language of the latest decision or notable change; the `recent` attribute holds the last 10. The dashboard shows them too.
- **Diagnostics**: Settings → Devices & services → HomeBatteryAssist → ⋮ → *Download diagnostics* gives the configuration and the state of each module, useful when reporting an issue.
- **Technical logging** per module, e.g. in `configuration.yaml`:

  ```yaml
  logger:
    logs:
      custom_components.homebatteryassist: info               # decisions
      custom_components.homebatteryassist.engine.forecasts: debug    # forecast details
      custom_components.homebatteryassist.engine.inputs.direct: debug # directly read meters
      custom_components.homebatteryassist.engine.user_modules: debug  # own modules
  ```

## Notifications

Choose in the settings which decisions you want to be told about — the plan changes, new prices or a changed forecast reach, phase protection / limits / peak shaving, full charges, a lost or restored measurement — and send them to notify services (e.g. the companion app) and/or as a notification in Home Assistant.
