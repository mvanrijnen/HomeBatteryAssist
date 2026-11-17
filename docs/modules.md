# Modules: make HomeBatteryAssist your own

The swappable parts of HomeBatteryAssist's layers are *modules* (devices are [drivers](drivers.md); see [Architecture](architecture.md)). You choose between the built-in ones, and advanced users can add their own without changing the integration. Five kinds can be added as own modules today:

| Kind | What it does | Built-in | Own modules in | Choose in the settings |
|---|---|---|---|---|
| **Planner** | Decides per slot how much the batteries charge or discharge | Zero on the meter, Arbitrage, Full arbitrage, Time slots, Manual | `/config/homebatteryassist/planners/` | Battery plan mode |
| **Consumption forecaster** | Predicts the house consumption per slot | Weekday and hour profile (default), Same time in the last weeks | `/config/homebatteryassist/forecasters/` | Consumption forecaster |
| **Tariff** | Turns the source's prices into what a kWh really costs and earns | As the price source gives them (default) | `/config/homebatteryassist/tariffs/` | Tariff |
| **PV forecast source** | Reads a solar forecast | Solar forecast integrations (Forecast.Solar, Solcast, …) | `/config/homebatteryassist/pv_forecasts/` | PV forecast |
| **PV correction** | Adjusts the PV forecast with what was learned from past forecasts and measured PV | Per lead time, hour and level (default), Per lead time (the original) | `/config/homebatteryassist/pv_corrections/` | PV correction (section *Solar forecast*) |

The built-in modules live in the integration and are updated with it; your own modules live in their own folder under `/config`, so an update never touches them.

The **price sources** (`engine/sources/prices/`: [DynTarNL](https://github.com/mvanrijnen/ha-dyntarNL) (verified), Nord Pool, EnergyZero, easyEnergy, ENTSO-e, EPEX Spot, Frank Energie, Zonneplan, Amber Electric, PVPC, Essent, Pure Energie, or any sensor with prices in its attributes) are modules too; new ones are added to the code for now (`template.py`). The same goes for **weather sources** (`engine/sources/weather/`: a Home Assistant weather entity; `template.py`). Sources still in development (e.g. Tibber) are kept apart in `in_development/` and not offered.

## HomeBatteryAssist keeps the final say

Whatever a module returns, HomeBatteryAssist checks it before it is used:

- **Planner**: every requested power is cut back to what the batteries and the phases allow, to the minimum/maximum state of charge and to your price rules (no discharging below the minimum discharge price, no charging from the grid above the maximum charge price — except fixed actions you set yourself, such as manual or time slots). **Periodic full charges are inserted after that.** A planner cannot plan anything the batteries or the grid connection cannot do.
- **Consumption forecaster**: a missing, negative or absurd value is replaced by the built-in profile's prediction. The temperature step (optional), the learned (or manual) correction and your own adjustments are applied afterwards.
- **Tariff**: a missing or absurd price (more than 10 per kWh either way) is replaced by the price the source gave. The accuracy of the price *forecast* is still measured on the source's prices.
- **PV forecast source**: negative, non-finite or absurd values and hours without a time zone are dropped. The PV correction and the safety margin are applied afterwards.
- **PV correction**: a missing, negative, non-finite or absurd value (more than 3 × the forecast + 100 Wh) is replaced by the correction per lead time. Accuracy is always learned on the *raw* forecast, so a correction never feeds back on itself. When the correction is set by hand or switched off (action `set_forecast_correction`), only the correction per lead time is used, as set.

If a chosen module fails, the explanation (*Why*) says so once, the log has the details, and the built-in fallback is used: zero on the meter for a planner, the profile for a forecaster, the source's prices for a tariff. The dashboard's overview shows which planner, forecaster and tariff are active, and marks a fallback.

Everything stays **advice**: no module controls a battery or any other device.

## Comparing

- **Planners**: every planner, also your own, is calculated every cycle; the dashboard compares their expected saving with no battery.
- **Consumption forecasters**: every forecaster runs every cycle and its own accuracy (before corrections) is tracked per lead time. The *Accuracy* tab shows them side by side, the best in bold — so after a week you see which forecaster suits your house, and switch.
- **PV corrections**: every correction runs every cycle and the PV forecast after it is checked against the measured PV per lead time. The *Accuracy* tab shows them side by side, with the uncorrected forecast for reference.

## Making your own

1. Create the folder of the kind (e.g. `/config/homebatteryassist/forecasters/`), e.g. with the File editor.
2. Copy the kind's `template.py` from the integration into it under a name of your own — or copy a built-in module to start from it:

   | Kind | Template and built-in modules |
   |---|---|
   | Planner | `engine/planning/planners/template.py` (charge in the cheapest hours); `zero_on_meter.py`, `arbitrage.py` |
   | Consumption forecaster | `engine/forecast/forecasters/template.py` (average of the last day); `weekday_hour_profile.py`, `same_time_last_weeks.py` |
   | Tariff | `engine/sources/tariffs/template.py` (a dynamic contract from the market price — fill in your own numbers); `as_price_source.py` |
   | PV forecast source | `engine/sources/pv_forecasts/template.py` (a sensor with a `wh_hours` attribute); `solar_forecast_integrations.py` |
   | PV correction | `engine/evaluation/pv_corrections/template.py` (less in the morning, e.g. a tree); `hour_and_level.py`, `lead_time.py` |

3. Give the class its own `key` and `name`. In a copied built-in module, change the relative imports (`from .base import ...`) into absolute ones (`from custom_components.homebatteryassist.<package>.base import ...`), as in the templates.
4. Reload HomeBatteryAssist (Settings → Devices & services → HomeBatteryAssist → ⋮ → Reload). Your module appears in the settings as `custom_<key>`.

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

`data.slots` (per slot: `start`, `end`, `hours`, `house_w`, `pv_w`, `net_w`, `price`, `export_price`, `max_charge_w`, `max_discharge_w`), `data.battery` (all batteries as one: `capacity_wh`, `stored_wh`, `floor_wh`, `ceiling_wh`, `efficiency`), `data.rules` (your plan rules), `data.cycle_cost`, `data.peak_w`, `data.priced`. Return the requested power per slot in W (+ charging, − discharging). Runs outside the event loop; no I/O.

### Consumption forecaster — `engine/forecast/forecasters/base.py`

```python
class Forecaster:
    key = "my_forecast"
    name = "My forecast"

    def forecast(
        self, data: ForecasterInput
    ) -> ForecasterResult | list[float | None]: ...
```

`data.history` (the consumption records: `start`, `minutes`, `avg_w`, `coverage`, optionally `pv_w`, `excluded_w`, `battery_w`, `vacation`, `heating_w` (heating/cooling devices, part of `avg_w`), `temp_c` (outdoor temperature) and `zones` (per heating/cooling device: `w`, and when measured `in` = room and `out` = own outdoor temperature)), `data.slots` (start, end), `data.now`, `data.interval`, and `data.temperatures` (the forecast outdoor temperature per slot in °C, None where unknown; None without a weather entity). Return the expected consumption per slot in W, or None where you have no idea. Quick, no I/O.

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

### PV correction — `engine/evaluation/pv_corrections/base.py`

```python
class PvCorrector:
    key = "my_correction"
    name = "My PV correction"

    def correct(self, data: PvCorrectionInput) -> list[float | None]: ...
    def details(self) -> dict: ...  # optional: what was learned (diagnostics)
```

`data.slots` (UTC hour start, raw forecast Wh), `data.results` (the last weeks per hour: `start`, `actual` measured Wh and `predictions` = raw forecast Wh per lead time bucket `0-1h` … `5d+`), `data.lead_factor(start)` (the built-in factor per lead time for a slot) and `data.bucket_factors`, `data.now`. Return the corrected Wh per slot, or None to use the correction per lead time. Quick, no I/O. The correction is used when *Correction of the PV forecast* is automatic (or automatic and fixed margin); the fixed margin comes after it.
