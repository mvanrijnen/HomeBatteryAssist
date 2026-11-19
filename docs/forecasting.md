# Forecasting

HomeBatteryAssist forecasts consumption itself, but takes prices and PV forecasts from the integrations you already have — and checks every forecast afterwards against what really happened.

## Planning window

Every forecast first determines how far ahead it can calculate: limited by your setting (1–7 days) and by how far the price and PV forecasts reach. Nothing is calculated beyond that window.

## Consumption

The house consumption per slot is predicted by a **consumption forecaster** [module](modules.md):

- **Weekday and hour profile** (default): the average per weekday and hour from your own history, recent days counting more; every day of the week (Monday … Sunday) has its own profile — no working days / weekend split, since with working from home a Wednesday can differ from a Tuesday; with little history it falls back to the hour of all days, or the overall average.
- **Same time in the last weeks**: the same weekday and time in the last two weeks.
- **Your own forecaster**, see [Modules](modules.md).

All forecasters run every cycle; the *Accuracy* tab compares them, so you can choose the one that fits your house. Consumption during a **vacation** (setting) is not learned from. You can **adjust** the forecast for a period (e.g. a party) with the action `adjust_forecast`.

### Outdoor temperature (optional)

A profile follows a sudden cold spell only after days. Houses that heat or cool with electricity (heat pump, electric heating, airco) can let the forecast follow the **weather forecast**:

1. Choose a **weather source** in the settings section *Weather and outdoor temperature*. This turns the temperature step on. The weather source is a [module](modules.md):
   - **Weather entity** — any weather entity with a forecast (Buienradar, Met.no, OpenWeatherMap, KNMI, …), chosen below it.
   - **KNMI integration** ([golles/ha-knmi](https://github.com/golles/ha-knmi)) — its weather entity is found by itself.
   - **Weerlive** — the KNMI data of [weerlive.nl](https://weerlive.nl/delen.php) directly, without an integration. Needs a free API key from weerlive.nl (field *API key*); at most 300 requests a day for private use. HomeBatteryAssist asks every 30 minutes (48 a day); an integration with the same key (e.g. KNMI) counts against the same limit.
   - **Open-Meteo** / **Open-Meteo, KNMI model** — [open-meteo.com](https://open-meteo.com) directly, no key needed for non-commercial use (data CC BY 4.0, *Weather data by Open-Meteo.com*); per hour for 7 days. The KNMI model is HARMONIE for the first days, then ECMWF.
   - Your own module (see [Modules](modules.md)).

   Weerlive and Open-Meteo use the **home location of Home Assistant** (rounded to about 1 km); the field *Place* is only for another place (`latitude,longitude`; Weerlive also takes a place name). The hourly forecast of a weather entity or Weerlive often reaches only 24–48 hours; after it, the daily minimum and maximum are turned into an hourly course (coldest around 05:00, warmest around 15:00), so the forecast reaches as far as the planning.
2. Optional: an **outdoor temperature sensor** — more accurate than the weather source's current temperature, and its history in Home Assistant is used to learn right away instead of after a week. The sensors of a zone (below) are filled in from the history too, so a new zone is learned right away.
3. Optional: add the heat pump or airco as a **heating/cooling** device (with its power sensor). It stays part of the house consumption, but is measured apart, which gives a cleaner signal.
4. Optional, per heating/cooling device: the **room temperature** sensor of the room it heats or cools, and its **own outdoor temperature** sensor (e.g. the outdoor unit of an airco; without it the outdoor temperature of step 1–2 is used). A device with these is a **zone**; several devices (an airco per room) are several zones.

Everything is optional: without a weather source nothing changes.

**What is learned.** Every history interval stores the outdoor temperature (and per zone its power, room and outdoor temperature). From whole days — days instead of hours keep the daily rhythm (cooking, sleeping) out of it — HomeBatteryAssist learns how many W the consumption rises per degree below the **heating point** (heating) and per degree above 22 °C (cooling, a fixed limit); at least 7 days with temperature are needed, and days that hardly differ teach nothing.

- The heating point is the room temperature minus what the house warms itself (people, appliances, sun). Without a room sensor the room is taken as 20 °C; the warming is learned (0–8 °C, 4 °C — so 16 °C outside — unless another value fits the days clearly better).
- With a room sensor, the **desired room temperature** per hour is learned too (e.g. 21 °C during the day, 17 °C at night), recent days counting more (a week ago counts half, so a lower thermostat shows within days). Either per hour for working days together and the weekend, or per day of the week (e.g. 22 °C on the Thursdays and Fridays you work from home): HomeBatteryAssist checks which of the two would have predicted the last week best and uses that one. The forecast assumes it: a cold night costs less than a cold afternoon when the thermostat is lower at night.
- What is fitted: per zone its own power against its own temperatures, the zones added up — once every zone has 7 days. Until then, and without zones, the heating/cooling devices together, or without them the whole house.

**How it is applied.** Per slot the step adds *W per degree × (forecast degrees − the usual degrees at that day of the week and hour, recent days counting more)*: only the difference with the weather the profile already contains. The step comes after the forecaster and before the correction, so the accuracy check covers it. A forecaster [module](modules.md) that handles temperature itself sets `uses_temperature = True` and gets the forecast per slot in `temperatures`. The decision log (*Why*) tells what was learned — W per degree, the heating point and, with a room sensor, the room temperature by day and night (per day of the week when the days differ); the diagnostics have the details per zone.

## Prices

From a price source of your choice (*price [drivers](drivers.md)*): [DynTarNL](https://github.com/mvanrijnen/ha-dyntarNL) (tested; Dutch dynamic tariffs with a price forecast for the coming days), Nord Pool, Tibber, EnergyZero, easyEnergy, ENTSO-e, EPEX Spot, Frank Energie, Zonneplan, or any sensor with prices in its attributes; optionally an extra, longer forecast after it. Estimated (forecast) prices are marked as such. Prices are converted to a price per kWh in the main currency from the source's unit (ct/kWh, EUR/MWh, öre/kWh, ...); a source without a known unit is taken as per kWh.

### Export price and no net metering

Every calculation (plans, comparisons and the realised value of the batteries) assumes there is **no net metering** (in the Netherlands it ends on 1 January 2027). Imported energy costs the import price; exported energy earns only the export price, so charging from solar power costs what that power would have earned, and discharging saves the import price only for energy the house would otherwise have bought.

The export price is the bare market price (EPEX, default), the export price — from the price source when it has one, otherwise from one or more sensors — or import price × factor (default 0.25; 1.0 equals net metering). On a dynamic contract the supplier usually deducts a purchase fee from the market price for exported energy (e.g. Essent about € 0.025/kWh); with DynTarNL as price source, *Export price from the price source* gives exactly that. From DynTarNL 1.2.0 the export prices are read directly — the published ones from *export price now* (attribute `prices`), then the forecast ones (`forecast_export`, when DynTarNL's forecasts are on) after the last published hour; negative export prices are kept (exporting costs money then). Older DynTarNL versions work too: the market price minus the purchase fee DynTarNL reports.

### Tariff

A **tariff** [module](modules.md) turns these prices into what a kWh really costs and earns — for example for a contract with export costs or own surcharges. The built-in tariff *As the price source gives them* uses them as they are. For a source with bare market prices (Nord Pool, EnergyZero, easyEnergy: no energy tax or supplier surcharge) choose the built-in tariff *Market price + surcharge + energy tax, plus VAT* (not tested) and fill in the amounts under *Tariff costs*; otherwise arbitrage sees the losses of a round trip too cheaply. The template shows a dynamic contract built from the market price.

## PV

From a **PV forecast source** [module](modules.md): by default any integration that supports the Energy dashboard's solar forecast (e.g. Forecast.Solar, Solcast); several forecasts (e.g. one per roof) are summed. Forecast.Solar labels each amount with the end of its period (19:00 = 18:00-19:00); HomeBatteryAssist puts it in the right hour. Corrected automatically (learned), with a fixed safety margin, both, or not at all.

### PV correction

Every hour the PV forecast is checked against the PV measured afterwards. The automatic correction is a **PV correction** [module](modules.md), chosen in the settings section *Solar forecast*:

- **Per lead time, hour and level** (default): the factor per lead time below, and on top of it what is typical for your installation:
  - **per hour of the day** — e.g. shade in the morning or a roof facing west: the forecast is too high in the morning and too low in the afternoon;
  - **per level** — how much the forecast promises at that hour compared with the most it promised at that hour lately (about a clear sky). Forecasts are often relatively further off on dull days than on sunny ones; *dull*, *mixed* and *sunny* hours each get a factor.

  Both are learned from the last weeks (recent days counting more) and count for less while there are few days; the combined factor stays between 0.3 and 2. Without history it is the same as the original.
- **Per lead time** (the original, always available): one factor per lead time (0–1 h … 5 days+), measured / forecast energy, between 0.5 and 1.5.
- **Your own correction**, see [Modules](modules.md) — e.g. a copy of a built-in one, adapted.

All corrections are calculated every cycle; the *Accuracy* tab compares them with each other and with the uncorrected forecast. The diagnostics show what the chosen one learned (factors per hour and level). A correction set by hand or switched off (action `set_forecast_correction`) is followed as set.

### Unexpected solar surplus or shortage

The correction works afterwards; *Why* also says it while it happens. When clearly more solar power is left over than forecast — the measured surplus (PV − house − excluded devices) is at least 300 W and less than half of it was forecast for this hour (PV forecast, corrected, minus the consumption forecast), for 5 minutes on end — *Why* reports an **unexpected solar surplus**; when at least 300 W was forecast and less than half of it is there, *Why* reports **less solar than forecast**. Each message says how much, what was forecast, and what it means for the batteries. When it has been over for 10 minutes a second message gives the energy left over and how much of it was forecast. Both values are settings (section *Solar forecast*). Needs a measured PV source and a PV forecast. Can also be sent as a notification (kind *Unexpected solar surplus or shortage*). What the batteries do: [Planning: when the sun differs from the forecast](planning.md#when-the-sun-differs-from-the-forecast).

## Accuracy

Every forecast is verified afterwards per lead time (0–1 h … 5 days+): consumption against the measured consumption, PV against the measured PV, estimated prices against the prices published later. Learned corrections are applied automatically, or set by hand (action `set_forecast_correction`).

With heating/cooling devices measured apart and the temperature effect learned, the **heating/cooling part** is also checked on its own: the power the [temperature step](#outdoor-temperature-optional) expected per slot against what the devices really used (row *of which heating/cooling* on the *Accuracy* tab). It is only measured, not used to correct anything.
