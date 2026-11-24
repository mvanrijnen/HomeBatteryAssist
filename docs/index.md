---
description: "HomeBatteryAssist: a Home Assistant integration (HACS) for home batteries. Measures, forecasts consumption, solar and prices, plans zero on the meter and arbitrage with dynamic prices."
---

# HomeBatteryAssist

**Insight, forecasts and plans for your home batteries — in Home Assistant, explained in plain language.**

HomeBatteryAssist measures the energy flows of your home, forecasts consumption, prices and solar power, and works out what your batteries could best do: when to charge, from the sun or the grid, and when to supply the house. Every forecast is checked afterwards against what really happened, and every plan is explained in plain words.

!!! warning "Alpha — under active development"
    Settings, entities and behaviour can still change, and releases are alpha releases. **By default HomeBatteryAssist reads, forecasts and advises**; *virtual batteries* follow its plans as a simulation. Controlling a battery itself is possible but **off by default** and not yet tested widely: the setting *Control on* together with *Controlled by HomeBatteryAssist* in a battery's form (zero on the meter or the plan, as the active planner module says), and a [test control](measuring.md#test-control-switched-off-for-now) per battery — over a [direct connection](drivers.md#direct-battery-drivers) to the battery, or else through its integration. Switch off any other integration that controls the battery first.

[Get started :material-arrow-right:](getting-started.md){ .md-button .md-button--primary } [Screenshots](screenshots.md){ .md-button } [GitHub](https://github.com/mvanrijnen/HomeBatteryAssist){ .md-button }

[![The HomeBatteryAssist dashboard](screenshots/overview.jpg)](screenshots.md)

## What it does

<div class="grid cards" markdown>

-   :material-flash: **Measures**

    ---

    The grid connection per phase (read directly from e.g. a HomeWizard P1 or SMA Home Manager, or from your own sensors), your batteries, solar power, an EV charger and heating/cooling — and from that the real house consumption.

    [:material-arrow-right: Measuring](measuring.md)

-   :material-chart-line: **Forecasts**

    ---

    House consumption from your own history (optionally following the weather for heating or cooling), with the prices and solar forecast from your integrations. Every forecast is checked afterwards and corrected where it is consistently off.

    [:material-arrow-right: Forecasting](forecasting.md)

-   :material-battery-charging: **Plans**

    ---

    What the batteries could best do — zero on the meter or arbitrage — within the limits of the batteries and the main fuse, with reserves, peak shaving and periodic full charges. Every plan is compared with no battery.

    [:material-arrow-right: Planning](planning.md)

-   :material-message-text: **Explains**

    ---

    Every plan and every change in plain language: what happens until when, and why — also what your real battery does by itself.

    [:material-arrow-right: Planning: explanation](planning.md#explanation)

-   :material-view-dashboard: **Shows**

    ---

    A dashboard in the sidebar with the energy flows, forecasts, the return of each plan mode, your batteries and the accuracy of every forecast.

    [:material-arrow-right: Dashboard](dashboard.md)

-   :material-puzzle: **Can be made your own**

    ---

    Planner, consumption forecaster, tariff, PV correction, spike filter, weather source and interceptor are *modules*: pick a built-in one or add your own — HomeBatteryAssist keeps the final say.

    [:material-arrow-right: Modules](modules.md)

</div>

## Works with

- **Grid meters**: HomeWizard P1 (read directly), SMA Home Manager / Energy Meter (Speedwire), Shelly Pro 3EM / EM, Iammeter, or any sensors per phase.
- **Batteries**: through the integration that controls them, e.g. **Omnibattery** or **Marstek Modbus** (recognised automatically), or a [direct connection](drivers.md#direct-battery-drivers) (Marstek Venus E v3 tested; others not tested); any other battery can be linked by its sensors.
- **Prices**: DynTarNL (tested, incl. the export price), Nord Pool, EnergyZero, easyEnergy and price sensors with a forecast.
- **Solar forecast**: the forecasts of the Energy dashboard (e.g. Solcast, Forecast.Solar).
- **Weather** (optional): a weather entity, the KNMI integration, Weerlive or Open-Meteo.

## Where to next

- New here? Follow **[Getting started](getting-started.md)** step by step.
- Looking for one setting? See the **[Settings reference](reference.md)**.
- Something unexpected? Check the **[FAQ](faq.md)**.
- Building automations or your own modules? See **[Working with other integrations](integration.md)** and **[Modules](modules.md)**.
