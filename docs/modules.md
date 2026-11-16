# Modules: make HomeBatteryAssist your own

Four parts of HomeBatteryAssist are *modules*: you can choose between the built-in ones, and add your own without changing the integration.

| Kind | What it does | Built-in | Own modules in | Choose in the settings |
|---|---|---|---|---|
| **Planner** | Decides per slot how much the batteries charge or discharge | Zero on the meter, Arbitrage, Full arbitrage, Time slots, Manual | `/config/homebatteryassist/planners/` | Battery plan mode |
| **Consumption forecaster** | Predicts the house consumption per slot | Weekday and hour profile (default), Same time in the last weeks | `/config/homebatteryassist/forecasters/` | Consumption forecaster |
| **Tariff** | Turns the source's prices into what a kWh really costs and earns | As the price source gives them (default) | `/config/homebatteryassist/tariffs/` | Tariff |
| **PV forecast source** | Reads a solar forecast | Solar forecast integrations (Forecast.Solar, Solcast, …) | `/config/homebatteryassist/pv_forecasts/` | PV forecast |

The built-in modules live in the integration and are updated with it; your own modules live in their own folder under `/config`, so an update never touches them.

## HomeBatteryAssist keeps the final say

Whatever a module returns, HomeBatteryAssist checks it before it is used:

- **Planner**: every requested power is cut back to what the batteries and the phases allow, to the minimum/maximum state of charge and to your price rules (no discharging below the minimum discharge price, no charging from the grid above the maximum charge price — except fixed actions you set yourself, such as manual or time slots). **Periodic full charges are inserted after that.** A planner cannot plan anything the batteries or the grid connection cannot do.
- **Consumption forecaster**: a missing, negative or absurd value is replaced by the built-in profile's prediction. The learned (or manual) correction and your own adjustments are applied afterwards.
- **Tariff**: a missing or absurd price (more than 10 per kWh either way) is replaced by the price the source gave. The accuracy of the price *forecast* is still measured on the source's prices.
- **PV forecast source**: negative, non-finite or absurd values and hours without a time zone are dropped. The learned PV correction and the safety margin are applied afterwards.

If a chosen module fails, the explanation (*Why*) says so once, the log has the details, and the built-in fallback is used: zero on the meter for a planner, the profile for a forecaster, the source's prices for a tariff. The dashboard's overview shows which planner, forecaster and tariff are active, and marks a fallback.

Everything stays **advice**: no module controls a battery or any other device.

## Comparing

- **Planners**: every planner, also your own, is calculated every cycle; the dashboard compares their expected saving with no battery.
- **Consumption forecasters**: every forecaster runs every cycle and its own accuracy (before corrections) is tracked per lead time. The *Accuracy* tab shows them side by side, the best in bold — so after a week you see which forecaster suits your house, and switch.

## Making your own

1. Create the folder of the kind (e.g. `/config/homebatteryassist/forecasters/`), e.g. with the File editor.
2. Copy the kind's `template.py` from the integration into it under a name of your own — or copy a built-in module to start from it:

   | Kind | Template and built-in modules |
   |---|---|
   | Planner | `engine/planning/planners/template.py` (charge in the cheapest hours); `nom.py`, `arbitrage.py` |
   | Consumption forecaster | `engine/forecast/forecasters/template.py` (average of the last day); `profile.py`, `recent.py` |
   | Tariff | `engine/sources/tariffs/template.py` (a dynamic contract from the market price — fill in your own numbers); `source.py` |
   | PV forecast source | `engine/sources/pv_forecasts/template.py` (a sensor with a `wh_hours` attribute); `energy.py` |

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

`data.history` (the consumption records: `start`, `minutes`, `avg_w`, `coverage`, optionally `pv_w`, `excluded_w`, `battery_w`, `vacation`), `data.slots` (start, end), `data.now`, `data.interval`. Return the expected consumption per slot in W, or None where you have no idea. Quick, no I/O.

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
