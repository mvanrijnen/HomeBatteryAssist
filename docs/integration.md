---
description: "HomeBatteryAssist next to Omnibattery, Marstek and price or solar forecast integrations in Home Assistant."
---

# Working with other integrations

HomeBatteryAssist is built to control batteries itself. In this phase of development it controls nothing yet, for safety and so it can run next to any battery or energy integration (e.g. Omnibattery) without interfering.

## Sensors

The sensors have a fixed meaning and can be used by other integrations and add-ons: *Grid power* (+ import / − export), *Grid import*, *Grid export*, *PV power*, *House consumption*, the battery sensors and the *Battery plan*.

**Plan phases.** Four sensors tell what the plan does now and next: *Phase discharging*, *Phase charging (grid)*, *Phase charging (solar)* and *Phase grid only* (batteries idle, the house on the grid). Their state is *Running now*, *Planned* or *Not planned*; the attributes give the current and the next phase: start, end, minutes, kWh (for the running phase: what is left from now), average price (import price; export price for charging with solar), why in plain language, and the kWh per battery. Each battery device has the three battery phases with its own share (the plan is for all batteries together and is spread over them by capacity). Handy for automations, e.g. "notify me when charging from the grid starts" or "start the dishwasher in a solar charging phase".

**Plan explanation.** The sensor *Plan explanation* says in its state what the batteries do now, until when, the price now and the price thresholds (short: a state holds at most 255 characters); its attributes hold the full *Now* line with the reason, *Power* (batteries the plans give less power because they are warm), the next change, the plan in one line, the sun, the cheapest published price and the thresholds as numbers (*Using pays above*, *Charging pays below*; arbitrage only) — handy for a Markdown card. See [Planning](planning.md#explanation).

**Does not follow its command.** Each real battery has a problem sensor that is on while the battery does not follow the command of the integration that controls it, without an explanation (see [Measuring](measuring.md#does-the-battery-follow-its-command)); attributes: the command, the battery's power, the reason when explained, and since when.

**Test control.** Each real battery's device also has the [test control](architecture.md#control-layer-built-not-active) (buttons *Test: charge / discharge / stop*, *Test power*, *Test duration*, status *Test control*; see [Measuring](measuring.md#test-control-switched-off-for-now)). It is off unless the setting *Test control on* is on: until then the buttons send nothing. A battery with a [direct connection](drivers.md#direct-battery-drivers) also has the diagnostic sensor *Direct connection* (connecting / connected / error, with what it reads).

## Actions

| Action | What it does |
|---|---|
| `homebatteryassist.recalculate` | Recalculate the forecasts and plans now (also the *Recalculate* button). |
| `homebatteryassist.import_history` | Import past consumption once from Home Assistant's statistics. |
| `homebatteryassist.adjust_forecast` / `clear_forecast_adjustments` | Adjust the consumption forecast for a period (e.g. a party or a holiday). |
| `homebatteryassist.set_forecast_correction` / `reset_forecast_accuracy` | Control the learned forecast corrections. |
| `homebatteryassist.set_plan_mode` | Choose the plan mode: a built-in one or an own planner (`custom_<key>`). |
| `homebatteryassist.exclude_consumption_days` | Leave unusual days out of what the forecasts learn, or take them back. |

`import_history`, `set_forecast_correction`, `reset_forecast_accuracy`, `set_plan_mode` and `exclude_consumption_days` change settings or the history: only an administrator can call them. Adjusting the forecast and recalculating are open to every user (also from the dashboard).

## Repairs

Under **Settings → Repairs** HomeBatteryAssist reports: sensors it uses that Home Assistant's recorder leaves out (`recorder: exclude:`), because their history cannot be imported or used to fill in the past; and an old storage database that could not be reached for half an hour when moving away from it (see [Storage](#storage)). The message goes away once it is solved.

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

## Storage

HomeBatteryAssist keeps its data in Home Assistant's `.storage` folder. The two big parts, the consumption history (28 days) and the forecast accuracy, are written whole each time as JSON files of roughly 0.7 MB. Under **Settings → Storage** you can keep them in a database instead; then only what changed is written, which wears an SD card far less:

| Storage | |
|---|---|
| **JSON files** (default) | As before. |
| **SQLite** | An own file, `/config/homebatteryassist/homebatteryassist.db`. Nothing to set up. |
| **MySQL / MariaDB** (not tested) | A server, by URL, e.g. `mysql://user:password@core-mariadb/homebatteryassist?charset=utf8mb4` (the MariaDB add-on). Create the database first. |
| **PostgreSQL** (not tested) | A server, by URL, e.g. `postgresql://user:password@host/homebatteryassist`. Create the database first. |

The data moves along when you change the choice, at the next start: from the JSON files to the database and back, or from one database to another. A server is checked when you save the setting. If the database cannot be reached at a start, HomeBatteryAssist waits and tries again (Home Assistant retries the setup) rather than carry on with an old copy; if writing fails while it runs, everything is kept in the JSON file and moved into the database at the next start. A server is only checked again when you change the storage setting, so a server that is down never blocks other settings. Is the old database gone for good, choose another storage: once it has been unreachable for half an hour HomeBatteryAssist goes on from the JSON copy (from when the data moved to that database) and a repair issue says so. The URL is left out of the diagnostics download.
