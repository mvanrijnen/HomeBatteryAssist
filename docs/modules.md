---
description: "Make HomeBatteryAssist your own: planners, consumption forecasters, tariffs, PV corrections and spike filters as modules."
---

# Modules: make HomeBatteryAssist your own

The swappable parts of HomeBatteryAssist's layers are *modules* (devices are [drivers](drivers.md); see [Architecture](architecture.md)). You choose between the built-in ones, and advanced users can add their own without changing the integration. Eight kinds can be added as own modules today:

| Kind | What it does | Built-in | Own modules in | Choose in the settings |
|---|---|---|---|---|
| **Planner** | Decides per slot how much the batteries charge or discharge | Zero on the meter, Arbitrage own use, Arbitrage with export, Time slots, Manual | `/config/homebatteryassist/planners/` | Battery plan mode |
| **Consumption forecaster** | Predicts the house consumption per slot | Weekday and hour profile (default), Same time in the last weeks | `/config/homebatteryassist/forecasters/` | Consumption forecaster |
| **Tariff** | Turns the source's prices into what a kWh really costs and earns | As the price source gives them (default), Market price + surcharge + energy tax, plus VAT (not tested) | `/config/homebatteryassist/tariffs/` | Tariff |
| **PV forecast source** | Reads a solar forecast | Solar forecast integrations (Forecast.Solar, Solcast, …) | `/config/homebatteryassist/pv_forecasts/` | PV forecast |
| **PV correction** | Adjusts the PV forecast with what was learned from past forecasts and measured PV | Per lead time, hour and level (default), Per lead time (the original) | `/config/homebatteryassist/pv_corrections/` | PV correction (section *Solar forecast*) |
| **Spike filter** | Recognises short consumption peaks while they happen | Short peaks above a threshold | `/config/homebatteryassist/spike_filters/` | Spike filter (section *Short peaks*) |
| **Weather source** | Reads the outdoor temperature now and its forecast per hour | Weather entity, KNMI integration, Weerlive, Open-Meteo, Open-Meteo KNMI model | `/config/homebatteryassist/weather_sources/` | Weather source (section *Weather and outdoor temperature*) |
| **Interceptor** | Your last say per battery before a command goes out: approve, limit, hold back or release | None (everything as proposed) | `/config/homebatteryassist/interceptors/` | Interceptor (section *Planning*) |

The built-in modules live in the integration and are updated with it; your own modules live in their own folder under `/config`, so an update never touches them.

The **price sources** (`engine/sources/prices/`: [DynTarNL](https://github.com/mvanrijnen/ha-dyntarNL) (verified), Nord Pool, EnergyZero, easyEnergy, ENTSO-e, EPEX Spot, Frank Energie, Zonneplan, Amber Electric, PVPC, Essent, Pure Energie, a block tariff (`block_tariff.py`, fixed prices per time block from a setting), or any sensor with prices in its attributes) are modules too; new ones are added to the code for now (`template.py`). Sources still in development (e.g. Tibber) are kept apart in `in_development/` and not offered. Next to the price source you can choose an **extra price forecast** that predicts the market price days ahead (`price_forecasts.py`): EpexPredictor and stroomprijsprognose.nl (both verified), or the sensors of Energy Price Forecast EU, WattWanneer, Wattcast and EnerPrice (not tested). It is first brought to the level of the price source and is only used after that source's prices; the published prices keep coming from the price source.

## HomeBatteryAssist keeps the final say

Whatever a module returns, HomeBatteryAssist checks it before it is used:

- **Planner**: every requested power is cut back to what the batteries and the phases allow, to the minimum/maximum state of charge and to your price rules (no discharging below the minimum discharge price, no charging from the grid above the maximum charge price — except fixed actions you set yourself, such as manual or time slots). **Periodic full charges are inserted after that.** A planner cannot plan anything the batteries or the grid connection cannot do.
- **Consumption forecaster**: a missing, negative or absurd value is replaced by the built-in profile's prediction. The temperature step (optional), the learned (or manual) correction and your own adjustments are applied afterwards.
- **Tariff**: a missing or absurd price (more than 10 per kWh either way) is replaced by the price the source gave. The accuracy of the price *forecast* is still measured on the source's prices.
- **PV forecast source**: negative, non-finite or absurd values and hours without a time zone are dropped. The PV correction and the safety margin are applied afterwards.
- **Spike filter**: the part of the consumption not discharged for stays between 0 and the consumption, a peak's energy between 0 and 5 kWh; anything else counts as no peak. A failing filter is switched off until the next reload (*Why* says so). Regular peaks are always treated as normal consumption, whatever the filter says.
- **Interceptor**: it can only intercept — a limit is at most the proposal and in the same direction (more is cut back to the proposal, the other direction to 0 W); unknown batteries, unknown actions and nonsense count as approved; a failing interceptor lets the proposals through unchanged (*Why* says so once). After it comes HomeBatteryAssist's own final check, which always wins: phase limits, power limits and the state of charge.
- **Weather source**: hours without a time zone and temperatures that are not believable (outside −60…60 °C) are dropped; a failing source counts as no forecast (the consumption forecast is then not adjusted for the weather).
- **PV correction**: a missing, negative, non-finite or absurd value (more than 3 × the forecast + 100 Wh) is replaced by the correction per lead time. Accuracy is always learned on the *raw* forecast, so a correction never feeds back on itself. When the correction is set by hand or switched off (action `set_forecast_correction`), only the correction per lead time is used, as set.

If a chosen module fails, the explanation (*Why*) says so once, the log has the details, and the built-in fallback is used: zero on the meter for a planner, the profile for a forecaster, the source's prices for a tariff. The dashboard's overview shows which planner, forecaster and tariff are active, and marks a fallback.

Modules never talk to a device. With *Control on*, the planner module in use (*Zero on the meter* or *Arbitrage*) and the interceptor decide what the controlled batteries do, always through HomeBatteryAssist's final check and each battery's controller ([safety layers](architecture.md#safety-layers)); otherwise everything is advice.

## Comparing

- **Planners**: every planner, also your own, is calculated every cycle; the dashboard compares their expected saving with no battery.
- **Consumption forecasters**: every forecaster runs every cycle and its own accuracy (before corrections) is tracked per lead time. The *Accuracy* tab shows them side by side, the best in bold — so after a week you see which forecaster suits your house, and switch.
- **Spike filters**: the diagnostics show what the chosen filter saw (peaks, their energy) and the hours with regular peaks.
- **PV corrections**: every correction runs every cycle and the PV forecast after it is checked against the measured PV per lead time. The *Accuracy* tab shows them side by side, with the uncorrected forecast for reference.

## Making your own

1. Create the folder of the kind (e.g. `/config/homebatteryassist/forecasters/`), e.g. with the File editor.
2. Copy the kind's `template.py` from the integration into it under a name of your own — or copy a built-in module to start from it:

   | Kind | Template and built-in modules |
   |---|---|
   | Planner | `engine/planning/planners/template.py` (charge in the cheapest hours); `zero_on_meter.py`, `arbitrage.py` |
   | Consumption forecaster | `engine/forecast/forecasters/template.py` (average of the last day); `weekday_hour_profile.py`, `same_time_last_weeks.py` |
   | Tariff | `engine/sources/tariffs/template.py` (a dynamic contract from the market price — fill in your own numbers); `as_price_source.py`, `market_plus_costs.py` |
   | PV forecast source | `engine/sources/pv_forecasts/template.py` (a sensor with a `wh_hours` attribute); `solar_forecast_integrations.py` |
   | PV correction | `engine/evaluation/pv_corrections/template.py` (less in the morning, e.g. a tree); `hour_and_level.py`, `lead_time.py` |
   | Spike filter | `engine/measure/spike_filters/template.py` (never discharge above a level during the day); `short_peaks.py` |
   | Weather source | `engine/sources/weather/template.py` (a sensor plus day values); `ha_weather_entity.py`, `knmi_integration.py`, `weerlive_api.py`, `open_meteo.py` |
   | Interceptor | `engine/control/interceptors/template.py` (no discharging of a cold battery, no grid charging while a big device runs, at most 1500 W); `pass_through.py` |

3. Give the class its own `key` and `name`. In a copied built-in module, change the relative imports (`from .base import ...`) into absolute ones (`from custom_components.homebatteryassist.<package>.base import ...`), as in the templates.
4. Reload HomeBatteryAssist (Settings → Devices & services → HomeBatteryAssist → ⋮ → Reload). Your module appears in the settings as `custom_<key>`, marked **(not tested)** until you set `verified = True` in the class — do that only after testing it on your own setup.

A file whose name starts with `_` is ignored; a file that does not load is skipped and logged. After changing a file, reload again.

> [!CAUTION]
> Module files are Python code that runs inside Home Assistant. Only use files you wrote yourself or trust.

## The interfaces

Each kind has a `base.py` in its package with the full interface and documentation. In short:

### Planner — `engine/planning/planners/base.py`

```python
class Planner:
    key = "my_plan"
    name = "My plan"

    def plan(self, data: PlannerInput) -> PlannerResult | list[float]: ...
```

`data.slots` (per slot: `start`, `end`, `hours`, `house_w`, `pv_w`, `net_w`, `price`, `export_price`, `max_charge_w`, `max_discharge_w`), `data.battery` (all batteries as one: `capacity_wh`, `stored_wh`, `floor_wh`, `ceiling_wh`, `efficiency`; `members` = the batteries apart when there are several), `data.forced` (extra charge W per slot start that must happen: the periodic full charges), `data.rules` (your plan rules), `data.cycle_cost`, `data.peak_w`, `data.priced`. Return the requested power per slot in W (+ charging, − discharging). The final check splits it over the batteries (a full battery takes no more charge, an empty one gives nothing) and adds the full charges. Runs outside the event loop; no I/O.

### Consumption forecaster — `engine/forecast/forecasters/base.py`

```python
class Forecaster:
    key = "my_forecast"
    name = "My forecast"

    def forecast(
        self, data: ForecasterInput
    ) -> ForecasterResult | list[float | None]: ...
```

`data.history` (the consumption records: `start`, `minutes`, `avg_w`, `coverage`, optionally `pv_w`, `excluded_w`, `battery_w`, `vacation`, `heating_w` (heating/cooling devices, part of `avg_w`), `temp_c` (outdoor temperature) and `zones` (per heating/cooling device: `w`, and when measured `in` = room and `out` = own outdoor temperature)), `data.slots` (start, end), `data.now`, `data.interval`, and `data.temperatures` (the forecast outdoor temperature per slot in °C, None where unknown; None without a weather source). Return the expected consumption per slot in W, or None where you have no idea. Quick, no I/O.

The optional [temperature step](forecasting.md#outdoor-temperature-optional) is added to your result afterwards; set `uses_temperature = True` on your class if your forecaster already takes the temperature into account.

### Tariff — `engine/sources/tariffs/base.py`

```python
class Tariff:
    key = "my_contract"
    name = "My contract"
    needs_market = True

    def prices(self, data: TariffInput) -> TariffResult: ...
```

`data.slots` (per period: `price` from the source, `market` (EPEX, with `needs_market` and when the source offers it), `export` by the export settings, `estimated`). Return the import and export price per period (None = keep the source's). Quick, no I/O.

### PV forecast source — `engine/sources/pv_forecasts/base.py`

```python
class PvForecastSource:
    key = "my_pv"
    name = "My PV forecast"

    async def async_find(self, hass) -> list[PvForecastOption]: ...
    async def async_read(self, hass, option_id) -> dict[datetime, float]: ...
```

`async_find` lists the forecasts the source offers (shown in the settings); `async_read` returns one as Wh per clock hour (timezone-aware hour starts). Only read — never control a device; use Home Assistant's shared HTTP session for web services and cache, because the forecast is read every cycle.

### Interceptor — `engine/control/interceptors/base.py`

```python
class Interceptor:
    key = "my_rules"
    name = "My rules"

    def intercept(self, data: InterceptInput) -> InterceptResult: ...
```

Called every round of the batteries (default every 5 s, at once on a large jump or an overload) with HomeBatteryAssist's proposal. `data.batteries` holds per battery its name, phase, state of charge, power now, temperature, capacity and limits, whether a full charge runs, the proposed power (`proposed_w`, + charge / − discharge) and why (`reason`: `plan`, `zero_on_meter`, `full_charge`, `min_soc_guard`, `phase_relief`, `peak_shaving`); besides that the grid (net and per phase, the phase limit), house, solar, excluded devices, the random short peak now, the plan mode and the coming slots of the plan (prices, export prices, planned power, 8 hours).

Return `InterceptResult(decisions, redistribute=True)` with a `Decision(battery_id, action, power_w, reason)` for the batteries you do not approve: `REJECT` (0 W, HomeBatteryAssist keeps control), `LIMIT` (at most `power_w`, same direction) or `RELEASE` (back to the battery's own control). With `redistribute` the approved batteries may take over what the others no longer do (up to their limits; for discharging not below `floor_soc`: the minimum raised by the reserves in force). The `reason` shows in *Why* and on the overview. Quick, no I/O. The interceptor acts on the virtual batteries and, with *Control on*, on the controlled real batteries in the same round, so with control off you see what it would do first.

### Weather source — `engine/sources/weather/base.py`

```python
class WeatherSource:
    key = "my_weather"
    name = "My weather"
    settings: WeatherSettings  # entity_id, api_key, location (what the user set)

    def temperature_now(self, hass) -> float | None: ...
    async def async_forecast(self, hass) -> dict[datetime, float]: ...
    def describe(self) -> str: ...  # optional: what it reads (diagnostics)
```

`async_forecast` returns °C per hour (timezone-aware hour starts) as far ahead as it can, and is called every cycle: cache (the built-in ones ask a web service every 30 minutes). `daily_curve` and `combine` in `base.py` turn daily minimum / maximum temperatures into hours after an hourly forecast. Only read; use Home Assistant's shared HTTP session.

### Spike filter — `engine/measure/spike_filters/base.py`

```python
class SpikeFilter:
    key = "my_filter"
    name = "My spike filter"
    threshold_w: float  # from the settings
    max_duration_s: float  # from the settings

    def update(self, when, house_w) -> SpikeState: ...
    def details(self) -> dict: ...  # optional: what it saw (diagnostics)
```

`update` gets every new house consumption value (W, None = unknown; about every 1 to 10 s) and keeps its own state; a fresh instance is made at every start. Return `SpikeState(ignore_w, ended_wh)`: the part of the consumption now that is a peak (not discharged for), and once, when a peak ended, its energy (left out of the average). Quick, no I/O.

### PV correction — `engine/evaluation/pv_corrections/base.py`

```python
class PvCorrector:
    key = "my_correction"
    name = "My PV correction"

    def correct(self, data: PvCorrectionInput) -> list[float | None]: ...
    def details(self) -> dict: ...  # optional: what was learned (diagnostics)
```

`data.slots` (UTC hour start, raw forecast Wh), `data.results` (the last weeks per hour: `start`, `actual` measured Wh and `predictions` = raw forecast Wh per lead time bucket `0-1h` … `5d+`), `data.lead_factor(start)` (the built-in factor per lead time for a slot) and `data.bucket_factors`, `data.now`. Return the corrected Wh per slot, or None to use the correction per lead time. Quick, no I/O. The correction is used when *Correction of the PV forecast* is automatic (or automatic and fixed margin); the fixed margin comes after it.
