# Forecasting

HomeBatteryAssist forecasts consumption itself, but takes prices and PV forecasts from the integrations you already have — and checks every forecast afterwards against what really happened.

## Planning window

Every forecast first determines how far ahead it can calculate: limited by your setting (1–7 days) and by how far the price and PV forecasts reach. Nothing is calculated beyond that window.

## Consumption

The house consumption per slot is predicted by a **consumption forecaster** [module](modules.md):

- **Weekday and hour profile** (default): the average per weekday and hour from your own history, recent days counting more; with little history it falls back to weekdays/weekend, hour of the day, or the overall average.
- **Same time in the last weeks**: the same weekday and time in the last two weeks.
- **Your own forecaster**, see [Modules](modules.md).

All forecasters run every cycle; the *Accuracy* tab compares them, so you can choose the one that fits your house. Consumption during a **vacation** (setting) is not learned from. You can **adjust** the forecast for a period (e.g. a party) with the action `adjust_forecast`.

## Prices

From a price source of your choice (*price [drivers](drivers.md)*): DynTarNL (tested), Nord Pool, Tibber, EnergyZero, easyEnergy, ENTSO-e, EPEX Spot, Frank Energie, Zonneplan, or any sensor with prices in its attributes; optionally an extra, longer forecast after it. Estimated (forecast) prices are marked as such.

### Export price and no net metering

Every calculation (plans, comparisons and the realised value of the batteries) assumes there is **no net metering** (in the Netherlands it ends on 1 January 2027). Imported energy costs the import price; exported energy earns only the export price, so charging from solar power costs what that power would have earned, and discharging saves the import price only for energy the house would otherwise have bought.

The export price is the bare market price (EPEX, default), an export price forecast from one or more sensors, or import price × factor (default 0.25; 1.0 equals net metering).

### Tariff

A **tariff** [module](modules.md) turns these prices into what a kWh really costs and earns — for example for a contract with export costs or own surcharges. The built-in tariff uses them as they are; the template shows a dynamic contract built from the market price.

## PV

From a **PV forecast source** [module](modules.md): by default any integration that supports the Energy dashboard's solar forecast (e.g. Forecast.Solar, Solcast); several forecasts (e.g. one per roof) are summed. Corrected automatically (learned), with a fixed safety margin, both, or not at all.

## Accuracy

Every forecast is verified afterwards per lead time (0–1 h … 5 days+): consumption against the measured consumption, PV against the measured PV, estimated prices against the prices published later. Learned corrections are applied automatically, or set by hand (action `set_forecast_correction`).
