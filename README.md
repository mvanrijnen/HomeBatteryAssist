<img src="images/icon.png" alt="HomeBatteryAssist" width="128" align="right">

# HomeBatteryAssist

A Home Assistant custom integration that gives insight into your home batteries and energy flows, forecasts what is coming, and plans what your batteries could best do — explained in plain language.

> [!WARNING]
> **Alpha — under active development, not even beta.** Settings, entities and behaviour can still change at any moment, and there are no releases yet. Use it to explore and give feedback, not to rely on.
>
> HomeBatteryAssist **does not control any physical battery** (or any other device): it only reads, forecasts and advises. Only *virtual* batteries follow its plans, as a simulation.

HomeBatteryAssist **only reads, forecasts and advises — it never controls your battery or any other device.** It runs next to the integration that controls your battery (e.g. Omnibattery) without interfering. It uses the price and PV forecasts you already have, and checks every forecast afterwards against what really happened.

## What it does

- **Measures** the grid connection per phase (meters read directly, e.g. HomeWizard P1 or SMA Home Manager, or your own sensors), your batteries (read-only, through their own integration), PV, excluded devices such as an EV charger and (optionally) heating/cooling, and from that the house consumption. *Virtual batteries* show what a (bigger) battery would bring. → [Measuring](docs/measuring.md)
- **Forecasts** the house consumption from your own history, optionally following the weather forecast for electric heating or cooling, and takes prices and the PV forecast from your integrations — assuming **no net metering** (as in the Netherlands from 2027). Every forecast is checked afterwards and corrected where it is consistently off. → [Forecasting](docs/forecasting.md)
- **Plans** what the batteries could best do — zero on the meter, arbitrage, time slots, manual or your own planner — within the batteries' and the grid connection's limits, with a periodic full charge, and compares every plan with no battery. Advice only. → [Planning](docs/planning.md)
- **Explains** every plan and every change in plain language, as periods: what happens until when, and why — also what your real battery does by its own control. → [Planning: explanation](docs/planning.md#explanation)
- **Shows** it all on a dashboard in the sidebar. → [Dashboard](docs/dashboard.md)
- **Can be made your own**: the planner, the consumption forecaster, the tariff and the PV forecast source are *modules* — choose a built-in one or add your own, while HomeBatteryAssist keeps the final say. → [Modules](docs/modules.md)

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
  - **Settings**: the main fields on top (history interval, planning horizon, forecast interval, price source, extra price forecast, plan mode, consumption forecaster, tariff, PV forecast), the rest in collapsible sections: export price, solar forecast correction, planning, limits and reserve, full charge, notifications, temperature and weather. Empty fields show their default value;
  - **Back to default settings**: every setting back to its default; where the prices and PV forecast come from is kept;
  - **Grid connection and meter**: the meter, phases, connection size and sensors.
- **Add** batteries, virtual batteries, PV sources, excluded devices, heating/cooling and time slots under the integration; each can be changed later (including its phase).

## Documentation

| Page | About |
|---|---|
| [Architecture](docs/architecture.md) | Layers, drivers and modules, and where everything is in the code |
| [Measuring](docs/measuring.md) | Grid meters, batteries, virtual batteries, PV sources, excluded devices, house consumption |
| [Forecasting](docs/forecasting.md) | Planning window, consumption, prices, export price and tariff, PV, accuracy |
| [Planning](docs/planning.md) | Plan modes, rules and limits, full charge, explanations, plan check |
| [Dashboard](docs/dashboard.md) | What each tab shows |
| [Modules](docs/modules.md) | Planners, consumption forecasters, price sources, tariffs and PV forecast sources — built-in and your own |
| [Drivers](docs/drivers.md) | Devices: battery models and readers, meters per brand |
| [Working with other integrations](docs/integration.md) | Sensors, actions, events, logging, notifications |
| [Development](docs/development.md) | Tests, code structure, contributing |

## License

[MIT](LICENSE)
