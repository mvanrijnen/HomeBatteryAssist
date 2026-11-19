---
description: "HomeBatteryAssist next to Omnibattery, Marstek, Victron and price or solar forecast integrations in Home Assistant."
---

# Working with other integrations

In this phase of development HomeBatteryAssist controls nothing, so it can run next to any battery or energy integration (e.g. Omnibattery) without interfering.

## Sensors

The sensors have a fixed meaning and can be used by other integrations and add-ons: *Grid power* (+ import / − export), *Grid import*, *Grid export*, *PV power*, *House consumption*, the battery sensors and the *Battery plan*.

**Plan phases.** Four sensors tell what the plan does now and next: *Phase discharging*, *Phase charging (grid)*, *Phase charging (solar)* and *Phase grid only* (batteries idle, the house on the grid). Their state is *Running now*, *Planned* or *Not planned*; the attributes give the current and the next phase: start, end, minutes, kWh (for the running phase: what is left from now), average price (import price; export price for charging with solar), why in plain language, and the kWh per battery. Each battery device has the three battery phases with its own share (the plan is for all batteries together and is spread over them by capacity). Handy for automations, e.g. "notify me when charging from the grid starts" or "start the dishwasher in a solar charging phase".

**Does not follow its command.** Each real battery has a problem sensor that is on while the battery does not follow the command of the integration that controls it, without an explanation (see [Measuring](measuring.md#does-the-battery-follow-its-command)); attributes: the command, the battery's power, the reason when explained, and since when.

**Test control.** Each real battery's device also has the [test control](architecture.md#control-layer-built-not-active) (buttons *Test: charge / discharge / stop*, *Test power*, *Test duration*, status *Test control*; see [Measuring](measuring.md#test-control-switched-off-for-now)). In this phase it is switched off: the buttons send nothing.

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
      custom_components.homebatteryassist.engine.forecast: debug    # forecast details
      custom_components.homebatteryassist.engine.devices.meters.discovery: debug # directly read meters
      custom_components.homebatteryassist.engine.own_modules: debug  # own modules
  ```

## Notifications

Choose in the settings which decisions you want to be told about — the plan changes, new prices or a changed forecast reach, phase protection / limits / peak shaving, full charges, a lost or restored measurement, an unexpected solar surplus or shortage, a battery that [does not follow its command](measuring.md#does-the-battery-follow-its-command) — and send them to notify services (e.g. the companion app) and/or as a notification in Home Assistant.

**Virtual batteries** always say so in their name (e.g. *Marstek Venus 1 (virtueel)*): HomeBatteryAssist adds it when the name does not.
