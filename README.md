<img src="images/icon.png" alt="HomeBatteryAssist" width="128" align="right">

# HomeBatteryAssist

A Home Assistant custom integration that gives insight into your home batteries and energy flows, forecasts what is coming, and plans what your batteries could best do — explained in plain language.

> [!WARNING]
> **Alpha — under active development, not even beta.** Settings, entities and behaviour can still change at any moment, and there are no releases yet. Use it to explore and give feedback, not to rely on.
>
> HomeBatteryAssist **does not control any physical battery** (or any other device): it only reads, forecasts and advises. Only *virtual* batteries follow its plans, as a simulation.

HomeBatteryAssist **only reads, forecasts and advises — it never controls your battery or any other device.** It runs next to the integration that controls your battery (e.g. Omnibattery) without interfering. It does not make price or PV forecasts itself: it uses the forecast integrations you already have, and checks every forecast afterwards against what really happened.

## Features

### Measuring

- **Grid connection** with 1 or 3 phases and its size (1x10A up to 3x80A).
- **Grid meter**, chosen during setup:
  - **read directly**, about once a second, read-only (nothing on the meter is changed, and the meter's own integration keeps working):
    - HomeWizard P1 meter and kWh meters (1- and 3-phase), local API;
    - SMA Sunny Home Manager 2.0 / Energy Meter, Speedwire (only received: the meter sends its data on the network anyway);
    - Shelly Pro 3EM / 3EM and Shelly EM / Pro EM, local API *(not yet verified on a device)*;
    - Iammeter WEM3080 / WEM3080T, local API *(not yet verified on a device)*;

    Meters already in Home Assistant are offered automatically; any of these can also be entered by IP address;
  - **via the sensors of its integration** (e.g. a HomeWizard P1 is recognised and filled in);
  - **your own sensors** per phase: one signed sensor, or separate import and return sensors; power (W) or current (A).
- **Batteries**, linked read-only through the entities of their own integration. Batteries of **Omnibattery** and **Marstek Modbus** are recognised and filled in, and their *battery driver* adds temperature, voltages, cell voltages, cycles, energy of today and measured efficiency; any other battery can be linked manually. Per battery: state of charge, power, status, stored/usable energy, time to full/empty, charged/discharged energy, last full charge and realised return, plus totals.
- **Virtual batteries**: simulated what-if batteries (capacity, power, state-of-charge limits, losses, phase) that follow the plan live, so you can see what a (bigger) battery would bring before buying one.
- **PV sources** and **excluded devices** (e.g. an EV charger): on one phase, on all phases (3-phase, spread evenly) or measured per phase with a sensor per phase. A PV source can also be a meter read directly (e.g. a HomeWizard kWh meter on the inverter's line).
- **House consumption** = grid + PV − excluded devices − battery charging, plus grid import/export, PV power and the load per phase as % of the main fuse.

### Forecasting

- **Consumption forecast** from your own history (per weekday and hour, recent days weigh more). Past consumption can be imported once from Home Assistant's statistics.
- **Prices** from a price source of your choice (*price drivers*): DynTarNL (tested), Nord Pool, Tibber, EnergyZero, easyEnergy, ENTSO-e, EPEX Spot, Frank Energie, Zonneplan, or any sensor with prices in its attributes; optionally an extra, longer forecast after it. Estimated (forecast) prices are marked as such. New sources can be added from a template driver (`inputs/price_drivers/template.py`).
- **Export price**: import price × factor, the bare market price (EPEX), or an export price forecast from one or more sensors.
- **PV forecast** from any integration that supports the Energy dashboard's solar forecast (e.g. Forecast.Solar, Solcast), corrected automatically (learned), with a fixed margin, both, or not at all.
- **Planning window**: every forecast first determines how far ahead it can calculate, limited by your setting and by how far the price and PV forecasts reach.
- **Accuracy**: every forecast is verified afterwards per lead time (0–1 h … 5 days+). Learned corrections are applied automatically, or set by hand.

### Planning (advice)

- A **battery plan** for every mode, with the expected saving:
  - **Zero on the meter (NOM)**: charge with surplus solar power, supply the house on shortage;
  - **Arbitrage** (own use): charge when power is cheap, supply the house when it is expensive;
  - **Full arbitrage**: like arbitrage, but may also discharge to the grid when the export price makes that worthwhile;
  - **Time slots**: your own slots (days, times, charge/discharge/idle, power, until a state of charge), zero on the meter outside them;
  - **Manual**: a fixed charge or discharge power.
- **Max. cycles per day** for arbitrage, to spare the batteries.
- **Your own rules**: a reserve state of charge (backup), max. charge/discharge power of all batteries together, a target grid power for zero on the meter, discharge only from a price, charge from the grid only up to a price, a minimum arbitrage margin, and a charge hysteresis.
- **Warm batteries**: with an optional temperature sensor per battery the plans use less power above a temperature limit.
- **Vacation mode**: consumption measured during a vacation is not learned from.
- **Negative prices**: charging when import is negative, making room before a negative export price.
- **Peak shaving** on the total grid import: the plan keeps energy in reserve for peaks, virtual batteries shave them live.
- **Phase limits**: the plan never lets a phase exceed the main fuse (with an adjustable safety margin). The share of each phase is learned from your history.
- **Phase protection** (virtual batteries): when a phase is overloaded, batteries on that phase take load off it within seconds.
- **Periodic full charge** per battery (for the battery management's calibration), at the cheapest moment, optionally on a preferred weekday and preferably with solar power; batteries charge fully at the same time when the grid connection allows it.
- **Distribution over several batteries**: as few batteries as possible at a sensible minimum power, kept in balance.
- **Plain-language explanation**, e.g. *"The batteries do not discharge now, because power is not expensive enough now (€ 0.31 per kWh): they keep their energy for Mon 07:00-12:00, when power costs € 0.40 per kWh, and charge tonight at € 0.27 per kWh."*

### Dashboard

A dashboard in the sidebar with the energy flows (and which grid meter is used), the current and next power price and the export price, the expected and realised return of each mode compared with no battery and with each other, the forecast chart with the plan, the batteries' state of charge, the last 7 days, the load per phase (including virtual batteries), the planning window, the forecast accuracy and the latest decisions. The plan mode can be chosen right on the dashboard. What phase protection and peak shaving do right now is shown with the phases, and the chart shows the advantage over no battery (and of arbitrage over zero on the meter) up to each moment. A card compares the plan with what really happened, per day.

## Installation

### HACS (custom repository)

1. In HACS, open the menu → **Custom repositories**.
2. Add `https://github.com/mvanrijnen/HomeBatteryAssist` with type **Integration**.
3. Install **HomeBatteryAssist** and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and search for **HomeBatteryAssist**.

### Manual

Copy `custom_components/homebatteryassist` into your Home Assistant `config/custom_components/` directory and restart Home Assistant.

Home Assistant 2025.6 or newer is required.

## Configuration

- **Configure** on the integration opens a menu:
  - **Settings**: the main fields on top (history interval, planning horizon, forecast interval, price source, extra price forecast, plan mode, PV forecast), the rest in collapsible sections: export price, solar forecast correction, planning, limits and reserve, full charge, notifications and temperature. Empty fields show their default value;
  - **Back to default settings**: every setting back to its default; where the prices and PV forecast come from is kept;
  - **Grid connection and meter**: the meter, phases, connection size and sensors. Your previous choices are kept: switching back to your own sensors starts from them.
- **Add** batteries, virtual batteries, PV sources, excluded devices and time slots under the integration; each can be changed later (including its phase).

## Working with other integrations

HomeBatteryAssist never controls anything, so it can run next to any battery or energy integration:

- **Use its data elsewhere.** The sensors have a fixed meaning and can be used by other integrations and add-ons: *Grid power* (+ import / − export), *Grid import*, *Grid export*, *PV power*, *House consumption*, the battery sensors and the *Battery plan*.
- **Actions** (for automations and scripts):

  | Action | What it does |
  |---|---|
  | `homebatteryassist.recalculate` | Recalculate the forecasts and plans now (also the *Recalculate* button). |
  | `homebatteryassist.import_history` | Import past consumption once from Home Assistant's statistics. |
  | `homebatteryassist.adjust_forecast` / `clear_forecast_adjustments` | Adjust the consumption forecast for a period (e.g. a party or a holiday). |
  | `homebatteryassist.set_forecast_correction` / `reset_forecast_accuracy` | Control the learned forecast corrections. |
  | `homebatteryassist.set_plan_mode` | Choose the plan mode (NOM, arbitrage, full arbitrage, time slots, manual). |

- **Events**: `homebatteryassist_forecast_updated` (after every forecast cycle) and `homebatteryassist_decision` (every explained decision).

## Why did it do that? Logging

- **Last decision** sensor: a short explanation in your language of the latest decision or notable change; the `recent` attribute holds the last 10. The dashboard shows them too.
- **Diagnostics**: Settings → Devices & services → HomeBatteryAssist → ⋮ → *Download diagnostics* gives the configuration and the state of each module, useful when reporting an issue.
- **Technical logging** per module, e.g. in `configuration.yaml`:

  ```yaml
  logger:
    logs:
      custom_components.homebatteryassist: info               # decisions
      custom_components.homebatteryassist.forecasts: debug    # forecast details
      custom_components.homebatteryassist.inputs.direct: debug # directly read meters
  ```

## Notifications

Choose in the settings which decisions you want to be told about — the plan changes, new prices or a changed forecast reach, phase protection / limits / peak shaving, full charges, a lost or restored measurement — and send them to notify services (e.g. the companion app) and/or as a notification in Home Assistant.

## Drivers: adding a device or price source

Prices, batteries, grid meters and PV meters are read through *drivers*, one per kind of source. Every kind has an empty template that is only a code example (never offered in the settings):

| Kind | Package | Template |
|---|---|---|
| Price sources (incl. forecast-only sources) | `inputs/price_drivers/` | `template.py` |
| Batteries (reading; write methods are defined but never used) | `inputs/battery_drivers/` | `template.py` |
| Grid and PV meters read directly | `inputs/meter_drivers/` | `template.py` |

A driver only reads: Home Assistant states and registries, a read-only local API or data a device broadcasts anyway. Copy the template, fill it in, add it to `DRIVERS` in the package's `__init__.py`, and mark it verified only after testing on a real installation.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt   # Windows: .venv\Scripts\pip
pytest
ruff check . && ruff format --check .
```

Home Assistant's test harness does not run on native Windows; use WSL there.

## License

[MIT](LICENSE)
