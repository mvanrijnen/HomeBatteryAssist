---
description: "What HomeBatteryAssist needs as input: grid meter, batteries, prices (DynTarNL import, market and export prices, tariff), PV forecast, weather and history."
---

# Inputs: what HomeBatteryAssist needs

HomeBatteryAssist makes **no forecasts of its own**: it reads measurements and forecasts from other integrations and combines them. This page lists every input in one place: what it is for, whether it is needed, where it comes from, and what happens without it.

## At a glance {#at-a-glance}

| Input | Needed for | Required? | Typical source |
|---|---|---|---|
| [Grid meter](#grid-meter) | everything (house consumption, phase protection) | **yes** | HomeWizard P1, SMA Home Manager, your own sensors |
| [Batteries](#batteries) | battery plans, counters, plan check | for plans | Omnibattery, Marstek Modbus, own sensors, or a virtual battery |
| [Import price](#prices) | arbitrage, costs and savings | for arbitrage | [DynTarNL](#dyntarnl), Nord Pool, EnergyZero, … |
| [Export price](#export-price) | value of exported energy | recommended | the price source, sensors, or import price × factor |
| [Market price](#prices) | only for the *market + costs* tariff or the *market* export price | sometimes | the price source |
| [Price extension](#price-extension) | planning further ahead | optional | EpexPredictor, stroomprijsprognose.nl |
| [PV forecast](#pv-forecast) | solar in the plans, night reserve | with solar panels | Forecast.Solar, Solcast |
| [PV measurement](#pv-measurement) | house consumption, learning the PV correction | with solar panels | inverter sensor or kWh meter |
| [Excluded devices / heating](#excluded-devices-and-heating) | a clean consumption profile | optional | EV charger, heat pump sensors |
| [Weather](#weather) | the temperature effect on consumption | optional | weather entity, KNMI, Weerlive, Open-Meteo |
| [History](#history) | good forecasts from day one | optional (once) | Home Assistant's statistics |

## Grid meter {#grid-meter}

**Required.** The power per phase (W, + import / − export): from a meter read directly (HomeWizard P1, SMA Home Manager, Shelly, IAMMETER), through the sensors of its integration, or your own sensors (one signed sensor, or import and return apart). Optional per phase: **current** (A) and **voltage** (V), and a power factor if the meter sends it; with them the phase protection works on the real current (see [Current per phase](measuring.md#current-per-phase)). Without a grid value the house consumption is unknown and the virtual batteries do nothing.

## Batteries {#batteries}

Per battery from **its own integration** (read-only): **state of charge** (%) and **power** (W, with its sign: + charging or + discharging, set in the battery form). Capacity, maximum charge/discharge power, min/max state of charge and efficiency are prefilled from a recognised battery and can be changed. Without batteries HomeBatteryAssist measures and forecasts, but makes no battery plan; a [virtual battery](measuring.md#virtual-batteries) needs no integration at all.

## Prices {#prices}

A price source gives up to three kinds of prices (roles), all **per kWh**:

- **import**: what a kWh from the grid costs, **all-in** (market price + supplier surcharge + energy tax + VAT). This is what the plans use.
- **market**: the bare market price (EPEX). Only needed for the tariff *Market price + surcharge + energy tax, plus VAT* and for the export price *bare market price*.
- **export**: what an exported kWh earns on your contract.

Published prices and forecast (estimated) prices are both used; estimates are marked as such. The window of the plans ends where the prices end, and at the **first gap** in them. Without prices arbitrage plans zero on the meter, and costs and savings are not shown.

Units are converted to the main currency per kWh (ct/kWh, EUR/MWh, öre/kWh, …); a source without a unit is taken as per kWh.

### DynTarNL (recommended for the Netherlands) {#dyntarnl}

[DynTarNL](https://github.com/mvanrijnen/ha-dyntarNL) gives all three roles plus a forecast of about 7 days. HomeBatteryAssist finds its sensors by itself (per DynTarNL entry):

| DynTarNL sensor (unique id ends with) | Attribute | Used as |
|---|---|---|
| `_electricity_forecast_total_avg_24h` | `prices` (`[time, all-in price, "p"/"f"]`: published, then forecast) | **import** |
| | `forecast_market` | market (forecast part) |
| | `forecast_export` (DynTarNL ≥ 1.2.0, forecasts on) | export (forecast part) |
| `_electricity_market_market_current` | `prices` (published market prices) | **market** |
| | `purchase_fee` | export on DynTarNL < 1.2.0 (market − fee) |
| `_electricity_feedin_compensation_now` (DynTarNL ≥ 1.2.0) | `prices` (published export prices, can be negative) | **export** |

Settings with DynTarNL:

1. **Price source**: *DynTarNL: ⟨your entry⟩*.
2. **Tariff**: *As the price source and export settings give them*. DynTarNL's import prices are already all-in, so another tariff would count the costs twice.
3. **Export price**: *Export price from the price source or sensor(s)*, without export price sensors. That is the market price minus your supplier's purchase fee, the same as your contract pays. Use DynTarNL ≥ 1.2.0 with its forecasts on, so the export price reaches as far as the import price.
4. **Extra price forecast**: not needed; DynTarNL already reaches about 7 days ahead.
5. **Planning horizon** (1–7 days): the plans never reach further than the prices.

### Other price sources {#other-price-sources}

- **Nord Pool, EnergyZero, easyEnergy** (not tested) give the **bare market price**. Choose the tariff *Market price + surcharge + energy tax, plus VAT* and fill in your supplier's surcharge, the energy tax (both per kWh, excl. VAT) and the VAT. Otherwise arbitrage sees a round trip as too cheap.
- **Price sensor**: any sensor with a price list in its attributes (`prices`, `prices_today`/`prices_tomorrow`, `raw_today`/`raw_tomorrow`, `today`/`tomorrow`, …; for market prices `forecast_market`, `prices_market`, …). Each item needs a start (`start`, `from`, `time`, …) and a price; an item without an end lasts until the next one.

### Price extension {#price-extension}

Optional: a second source that reaches further ahead, used **after** the last price of the price source and always counted as estimated (EpexPredictor, stroomprijsprognose.nl, or another driver). A source with market prices only is first brought to the level of your import prices (calibrated against the overlap).

### Export price {#export-price}

What exported energy earns. **No net metering** is assumed (it ends in the Netherlands on 1 January 2027): an exported kWh earns only the export price. The setting *Export price* has three choices:

- **Export price from the price source or sensor(s)**: without *Export price sensors* from the price source when it has an export price (DynTarNL: market − purchase fee; recommended on a dynamic contract); with them from those sensors (for overlapping periods the first sensor wins).
- **Bare market price (EPEX)** (default): from the price source, or from the selected sensors.
- **Import price x factor** (factor *Export compensation*, default 0.25; 1.0 = net metering). The factor is also used wherever the chosen source gives no price.

## PV forecast {#pv-forecast}

From every integration that supports the **Energy dashboard's solar forecast** (Forecast.Solar, Solcast, …). Several (e.g. one per roof) are added up. Per hour in Wh. It is used in the plans, for the night reserve (night = outside the first to the last sun hour of a day), and it limits the planning window. It is corrected by what your panels really did (learned), by a fixed margin, both, or not at all ([PV correction](forecasting.md#pv-correction)). Without a PV forecast there is no night reserve (when the sun comes up is not known), and the plans count on no sun.

## PV measurement {#pv-measurement}

Per PV source (a sub-item): a power sensor of the inverter or a kWh meter on its line. It is needed for the house consumption (`house = grid + PV − excluded − batteries`) and to learn the PV correction. Without it, with solar panels, the house consumption is too low in the sun.

## Excluded devices and heating {#excluded-devices-and-heating}

Optional sub-items. **Excluded devices** (an EV charger, a large load you plan yourself) are left out of the house consumption and the forecast, and the batteries never discharge for them. **Heating/cooling** zones (heat pump, airco) stay part of the house, but are recorded apart for the temperature effect.

## Weather {#weather}

Optional. An **outdoor temperature forecast** (weather entity, KNMI, Weerlive with a free API key, or Open-Meteo), optionally with an outdoor temperature sensor. With it the consumption forecast learns how many W per degree the house uses for heating or cooling. Without it the temperature has no effect.

## History {#history}

Optional, once: the action **Import consumption history** fills the history (up to 28 days) from Home Assistant's statistics of the sensors above. Then the forecasts are good from day one. A period without statistics of the grid, a battery or an excluded device is skipped. Without importing, HomeBatteryAssist learns from the moment it is installed.
