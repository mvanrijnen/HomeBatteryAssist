# Settings reference

Every screen of HomeBatteryAssist with each field and the explanation you see in Home Assistant, generated from the integration's own texts. For the background see [Measuring](measuring.md), [Forecasting](forecasting.md) and [Planning](planning.md); for pictures of the screens see [Screenshots](screenshots.md).

## Setup and grid connection {#setup}

The first setup and **Configure → Grid connection and meter** go through the same steps.

### Grid meter {#setup-meter}

These grid meters were found. A meter read directly gives a value about every second (read-only, nothing on the meter changes); a meter of another integration uses its sensors. Or choose the phases and sensors yourself. HomeBatteryAssist only reads the meter.

**Meter**

### Meter read directly {#setup-direct}

Choose the type of meter and enter its IP address. HomeBatteryAssist reads it about every second, read-only; nothing on the meter changes. For an SMA Home Manager / Energy Meter enter the address it sends from.

**Type of meter**, **IP address**

### Grid connection {#setup-user}

Is your home connected to the grid with 1 phase or 3 phases?

**Number of phases**

### Connection size {#setup-max-current}

Select the size of your grid connection (main fuse rating per phase). You can find it on your energy contract or on the main fuse in your meter cupboard.

**Connection**

### Phase measurements {#setup-sensors}

Select for each phase the sensor that measures the power (W) on that phase, typically from your smart meter (P1). If this sensor is positive for import and negative for export, leave the return sensor empty. If your meter has separate sensors for import and export (return), select both. A current sensor (A) cannot tell import from export, so it goes in the optional current fields below.

| Field | Explanation |
|---|---|
| **Phase L1** |  |
| **Phase L1 return (optional)** |  |
| **Phase L2** |  |
| **Phase L2 return (optional)** |  |
| **Phase L3** |  |
| **Phase L3 return (optional)** |  |
| **Phase L1 current (optional)** | Optional: the current (A) per phase, from the same meter. The main fuse sees current; without it the phase protection takes power / voltage (or / 230 V). The voltage (V) per phase makes that more precise. |
| **Phase L2 current (optional)** |  |
| **Phase L3 current (optional)** |  |
| **Phase L1 voltage (optional)** |  |
| **Phase L2 voltage (optional)** |  |
| **Phase L3 voltage (optional)** |  |

## Settings {#settings}

**Configure → Settings**: the main fields, then the collapsible sections. **Back to the default settings** resets them (where prices and the PV forecast come from is kept).

### Main fields {#settings-main}

| Field | Explanation |
|---|---|
| **Consumption history interval** | A shorter interval is more precise but stores more data. |
| **Maximum planning horizon** | How many days ahead the system may plan at most. |
| **Price forecast sensor** | Used with the price source 'Price sensor': a sensor of another integration with the price forecast in its attributes. |
| **PV forecast** | Integrations providing a solar forecast (e.g. Forecast.Solar, Solcast). Selected forecasts are added up to the total for your home. |
| **Recalculate every** | How often the forecasts are recalculated automatically. |
| **Battery plan mode** | How HomeBatteryAssist would control the batteries (advice only for now). All modes are always calculated for comparison. Own planner modules from /config/homebatteryassist/planners appear here too (after a reload). |
| **Price source** | Where the power prices come from. Sources found in Home Assistant are listed (* = not yet tested on a real installation); 'Price sensor' uses the sensor chosen below. |
| **Extra price forecast** | Optional: a second source that reaches further ahead (e.g. a multi-day forecast), used after the prices of the price source; always counted as estimated. |
| **Consumption forecaster** | How the house consumption is forecast. The accuracy of every forecaster is shown side by side on the dashboard. Own forecasters from /config/homebatteryassist/forecasters appear here too (after a reload). |
| **Tariff** | How the prices of the price source become what a kWh really costs and earns. Own tariffs from /config/homebatteryassist/tariffs appear here too (after a reload). |

### Tariff costs {#settings-tariff-costs}

Only for the tariff 'Market price + surcharge + energy tax, plus VAT' (for a price source with bare market prices such as Nord Pool, EnergyZero or easyEnergy).

| Field | Explanation |
|---|---|
| **Supplier surcharge** | What the supplier adds per kWh on top of the market price, excl. VAT, in Home Assistant's currency (e.g. 0.02 for 2 ct). |
| **Energy tax** | Energy tax per kWh excl. VAT, in Home Assistant's currency (e.g. 0.0916; see your contract or the tax authority). |
| **VAT** | VAT over market price, surcharge and energy tax. |

### Export price {#settings-export}

What returning power earns.

| Field | Explanation |
|---|---|
| **Export price** | What energy returned to the grid earns. Import price x factor (below), the bare market price (EPEX, from the selected sensors, or from market attributes of the price sensor), or the export price: from the price source when it has one (DynTarNL: the market price minus the supplier's purchase fee), otherwise from the selected sensors. Where these do not reach, import price x factor is used. |
| **Export price sensors** | One or more sensors with prices (state and/or price list attributes), e.g. a market price sensor for today/tomorrow plus a forecast sensor for the days after. For overlapping periods the first sensor wins. |
| **Export compensation** | Used with 'Import price x factor', and wherever the export price sensors give no price. All calculations assume no net metering (ends in the Netherlands on 1 January 2027): export earns only this compensation. Default 0.25 (a quarter of the import price); 1.0 equals net metering. |

### Solar forecast {#settings-solar}

Correction of the PV forecast, and what to do when the sun differs from it.

| Field | Explanation |
|---|---|
| **Correction of the PV forecast** | How the PV forecast is corrected before planning: automatically (learned from how accurate past forecasts were), with a fixed margin (below), both, or not at all. |
| **PV correction** | With 'automatic': which correction module learns from past forecasts. 'Per lead time, hour and level' (default) also learns per hour of the day (shade, roof direction) and per level (dull or sunny hour); 'Per lead time' is the original. Own corrections from /config/homebatteryassist/pv_corrections appear here too (after a reload). The Accuracy tab compares them. |
| **Margin on the PV forecast** | Used with 'fixed margin' and 'both': the plans count on this much less solar power, as a buffer against optimistic forecasts. |
| **More or less sun than forecast: from this difference** | When at least this much more solar power is left over than forecast for this hour (and less than half of it was forecast), the batteries store it on top of the plan. When at least this much was forecast and less than half of it is there, they only charge what is really left over: the grid does not fill in for the missing sun. Default 300 W. |
| **More or less sun than forecast: tell after** | Why tells it (and notifies, with 'Unexpected solar surplus or shortage') once it lasts this long, so a passing cloud or gap in the clouds is no message. The batteries react at once. Default 5 min. |

### Planning {#settings-planning}

How the plans weigh costs and prices, and the fixed modes.

| Field | Explanation |
|---|---|
| **Battery wear cost** | Cost per kWh through the battery (wear), in the price unit; avoids charging/discharging for tiny gains. |
| **Max. cycles per day (arbitrage)** | Arbitrage charges and discharges at most this many full cycles per day (energy discharged / capacity), to spare the batteries. 0 = no limit. |
| **Min. arbitrage margin** | Arbitrage only charges to discharge later when that brings at least this much per kWh, on top of the wear cost. |
| **Discharge only from price** | Optional: the batteries only discharge when power costs at least this much (also in zero on the meter). |
| **Charge from the grid up to price** | Optional: arbitrage only charges from the grid when power costs at most this much (charging with surplus solar power is always allowed). |
| **Target grid power (zero on the meter)** | Zero on the meter aims at this grid power instead of exactly 0 W, e.g. +50 W so a little is always imported. |
| **Manual power** | Used in the plan mode “Manual”: the batteries always charge (positive) or discharge (negative) at this power, within their limits. |
| **Charge hysteresis** | Once full, the batteries only charge again after their state of charge dropped this much below the maximum (fewer small top-ups). 0 = off. |
| **Vacation mode** | While on, the measured house consumption is not used to learn the usual consumption (the forecast keeps using the normal days). |
| **Interceptor** | Your last say per battery before a command goes out: approve, limit (less, same direction), hold back or release. HomeBatteryAssist's own check comes after it and always wins. None by default; own interceptors from /config/homebatteryassist/interceptors appear here too (after a reload). For now it acts on the virtual batteries. |

### Limits and reserve {#settings-limits}

Reserve, power limits, peak limit and phase margin.

| Field | Explanation |
|---|---|
| **Reserve state of charge** | The plans never go below this state of charge (e.g. as backup reserve), on top of each battery's own minimum. Peak shaving and phase protection may still use it. 0 = off. |
| **Night reserve state of charge** | From the evening (the sun gone) until the sun is up again (per the PV forecast) the plans do not go below this state of charge. Arbitrage charges from the grid for it at the cheapest moment before sunrise when needed; zero on the meter only keeps it. Peak shaving and phase protection may still use it. 0 = off. |
| **Max. charge power, all batteries** | All batteries together never charge at more than this power. 0 = no limit. |
| **Max. discharge power, all batteries** | All batteries together never discharge at more than this power. 0 = no limit. |
| **Minimum power per battery** | Below this power the conversion losses of a battery are high: a request is spread over as few batteries as possible, each running at least at this power, and over more batteries when more power is needed. |
| **Balance check every** | How often to check whether another battery should take over, so the batteries stay equally full. In between, the batteries in use are kept. |
| **Peak limit grid import** | Peak shaving on the total grid import (all phases together): the arbitrage plans keep energy in reserve to stay below this power, and virtual batteries take load off when it is exceeded. Next to the per-phase protection of the main fuse. 0 = off. |
| **Peak limit includes excluded devices** | When on, the consumption of excluded devices (e.g. an EV charger) counts for the peak limit. |
| **Peak reserve state of charge** | Below this state of charge the batteries only discharge for grid import above the peak limit, so energy stays for peaks. Only with a peak limit. 0 = off. |
| **Safety margin per phase** | Part of the main fuse rating that the batteries always leave free on every phase (the same for all phases). With 3x25A and 10% the batteries keep each phase below 22.5 A, in the plan and in the simulation. |

### Short peaks {#settings-spikes}

Short, high consumption peaks at random moments (a kettle, a microwave, an induction hob) are recognised by a spike filter module. A peak that comes back regularly (on most days of that day of the week, at the same hour) counts as normal consumption. Devices with their own power sensor can also be added as an excluded device: the battery never discharges for those.

| Field | Explanation |
|---|---|
| **Do not discharge for random peaks** | Zero on the meter does not discharge (extra) for a recognised peak: the grid supplies it. |
| **Leave random peaks out of the average consumption** | The energy of random peaks is not learned from: the consumption forecast (and the battery plan) does not count on them. |
| **Peak: at least this much above the usual consumption** | A rise of at least this much above the usual consumption can be a peak. Default 2000 W. |
| **Peak: lasting at most** | A rise that lasts longer is normal consumption (e.g. an oven) and is followed from then on. Default 5 minutes. |
| **Spike filter** | The module that recognises peaks. Own filters from /config/homebatteryassist/spike_filters appear here too (after a reload). |

### Reaction on the meter {#settings-reaction}

How often the batteries follow the grid meter (zero on the meter, phase protection). Phase overload and the peak limit are always acted on at once. For now this drives the virtual batteries; later the control.

| Field | Explanation |
|---|---|
| **A round every** | How often the batteries are adjusted to the meter. Every second hardly brings anything (the batteries take 1 to 2 seconds themselves); less often means fewer commands. Default 5 seconds. |
| **Use the average over the round** | Adjust to the average of the meter over the last round instead of its last value, so a single outlier steers nothing. |
| **React at once on a large jump** | When the grid changes by more than the jump below, an extra round at once (e.g. an oven or an EV charger switching on), not only at the next round. |
| **Large jump: at least** | Default 1000 W. |

### Full charge {#settings-full-charge}

The periodic full charge of the batteries.

| Field | Explanation |
|---|---|
| **Force full charge within** | When a battery has not been fully charged within its interval, a full charge is forced at the cheapest moment within this many days before the deadline. |
| **Preferred day for full charges** | Plan the periodic full charge on this weekday when it fits in the period; otherwise on the cheapest moment. |
| **Full charge preferably with solar power** | Count solar surplus as cheap (what exporting it would earn), so a full charge on a sunny moment is preferred over the grid. |

### Temperature {#settings-temperature}

Less power for warm batteries (with a temperature sensor).

| Field | Explanation |
|---|---|
| **Temperature limit** | Batteries with a temperature sensor charge at full power up to this temperature. |
| **Temperature reduction band** | Above the limit the power goes down over this many degrees, to the minimum power. |
| **Minimum power when warm** | Power at the end of the reduction band, as % of the battery's maximum. |
| **Also reduce discharging when warm** | Reduce the discharge power too, not only the charge power. |

### Notifications {#settings-notifications}

Get important decisions as notifications.

| Field | Explanation |
|---|---|
| **Send to** | Notify services (e.g. the companion app) and/or a notification in Home Assistant itself. |
| **About** | Which decisions to send. |

### Weather and outdoor temperature (optional) {#settings-weather}

For houses that heat or cool with electricity: the consumption forecast follows the weather forecast. Add a heating/cooling device for a cleaner signal.

| Field | Explanation |
|---|---|
| **Weather source** | Where the temperature forecast comes from (a module): a weather entity of your choice, the KNMI integration (found by itself), Weerlive (KNMI, needs a free API key from weerlive.nl) or Open-Meteo (no key needed; best model or the KNMI model). Turns the temperature step in the consumption forecast on. |
| **Weather entity** | For 'Weather entity': a weather entity with a forecast (e.g. Buienradar, Met.no, KNMI). Hourly forecast first, then the daily minimum/maximum for the days after. |
| **API key** | For Weerlive (required) and Open-Meteo (only with a commercial plan). Stored in Home Assistant; only sent to that service. |
| **Place** | For Weerlive and Open-Meteo: 'latitude,longitude' (Weerlive also takes a place name). Empty: the home location of Home Assistant, rounded to about 1 km. |
| **Outdoor temperature sensor** | Optional, more accurate than the weather entity's current temperature; its history is used to learn right away. |

### Battery follows its command {#settings-command-check}

Whether each battery does what it is told (in this phase by its own integration, e.g. Omnibattery), so a battery that stops charging or discharging is noticed.

| Field | Explanation |
|---|---|
| **Check commands from** | A command to charge or discharge at least this power is checked: the battery should move at least half of it (or of its maximum power) in that direction. Default 100 W. |
| **Tell after** | Why tells it (and notifies, with 'A battery does not follow its command') once it lasts this long, so starting up and ramping are no message. Full, almost full (from 5 % below the maximum), cold (below 5 °C, with a temperature sensor), empty, charging/discharging switched off and the battery's hysteresis are explained, not reported as a problem. Default 2 min. |

### Export limit (PV inverters) {#settings-export-limit}

The most that may be exported now, as the sensor Max export on the grid connection (0 W = no export): only export when it earns money after costs (export price of the tariff, minus the export costs of your contract), or a fixed maximum. In this phase only shown and explained in Why; nothing is sent to an inverter.

| Field | Explanation |
|---|---|
| **Never export** | Optional: export is always stopped (Max export 0 W), whatever the price; the batteries still store what they can, the inverters would produce no more than the house and batteries use. |
| **No export when it earns too little** | Below the limit price (the export price minus the export costs), the limit is 0 W: the batteries still store what they can, the inverters would produce no more than the house and batteries use. Off: only a fixed maximum limits. |
| **Export costs (fee or penalty)** | Per kWh exported, on top of the export price: e.g. the export fee of a fixed contract. Export only when the export price minus these costs is above the limit price. Default 0. |
| **Limit price (net)** | Export only when the export price (after the tariff, minus the export costs) is above this, per kWh. Default 0: only when exporting earns money; at a negative price never. |
| **Fixed maximum export** | E.g. a limit of the grid operator. 0 = none. |

## Devices and time slots {#devices}

Added under the integration (**+ Add …**) and changed with the gear icon next to each one.

### PV source {#device-pv-source}

A measurement of solar (PV) production, e.g. an inverter. Its production is added to the grid measurement to determine the actual house consumption.

| Field | Explanation |
|---|---|
| **Name** |  |
| **Sensor** | Sensor measuring the power (W) or current (A) of this device. |
| **Phase** | The phase this device is connected to, if it uses a single phase. |
| **Power L1 (optional, 3-phase)** | For a 3-phase device: a sensor per phase gives the exact split over the phases. Leave empty to spread the total evenly (phase 'all phases') or to use the phase chosen above. |
| **Power L2 (optional, 3-phase)** |  |
| **Power L3 (optional, 3-phase)** |  |
| **Measured by** | A sensor of another integration, or a meter read directly (about every second, read-only), e.g. a HomeWizard kWh meter on the inverter's line. |
| **Meter IP address** | Only for a meter read directly. |
| **Inverter driver (export limit)** | How this inverter could be limited for the export limit. With a Sunny Home Manager 2.0 choose the Home Manager for every SMA inverter behind it (the limit then goes through the Home Manager). In this phase nothing is sent: only shown what it would send. |
| **Address for the driver** | Where the chosen driver would send to: the IP address of the device it talks to, optionally with port and unit id (host:port/unit). With the Sunny Home Manager driver: the Home Manager's IP address (the same for every PV source behind it), not the inverter's. With SMA Modbus or SunSpec: the inverter's IP address (SunSpec on an SMA: e.g. 192.168.1.20:502/126). Without a driver: leave empty. |
| **Possible power (optional)** | What this PV source could produce now (W), e.g. an SMA inverter's register read with Home Assistant's Modbus integration. Where it is higher than the measured power, the PV was held back (curtailed): HomeBatteryAssist then learns from what the sun gave, and shows what is held back. |
| **Breaker of the inverter (A per phase)** | The breaker of the inverter's group (e.g. 20 A): the most this inverter can deliver (A x 230 V, x 3 when it is on all phases). When it is set for every PV source, Max export is no more than can pass the inverters' breakers, instead of the grid connection's maximum. |

### Excluded device {#device-excluded-load}

A device whose consumption is kept out of the house consumption, e.g. an EV charger, so it does not distort the consumption forecast.

| Field | Explanation |
|---|---|
| **Name** |  |
| **Sensor** | Sensor measuring the power (W) or current (A) of this device. |
| **Phase** | The phase this device is connected to, if it uses a single phase. |
| **Power L1 (optional, 3-phase)** | For a 3-phase device: a sensor per phase gives the exact split over the phases. Leave empty to spread the total evenly (phase 'all phases') or to use the phase chosen above. |
| **Power L2 (optional, 3-phase)** |  |
| **Power L3 (optional, 3-phase)** |  |

### Battery {#device-battery}

Link a home battery through the entities of its own integration (for now read-only). Its charging and discharging is kept out of the house consumption.

| Field | Explanation |
|---|---|
| **Name** |  |
| **State of charge sensor** | Sensor with the state of charge in %. |
| **Power sensor** | Sensor with the charge/discharge power (W) or current (A) of the battery. |
| **Power sensor direction** | Is the power sensor positive while charging or while discharging? |
| **Usable capacity** | Capacity of the battery in kWh (from the specifications). |
| **Maximum charge power** |  |
| **Maximum discharge power** |  |
| **Minimum state of charge** | The battery is not discharged below this level. |
| **Maximum state of charge** | The battery is not charged above this level (except for a full charge). |
| **Round-trip efficiency** | Share of charged energy that comes back out when discharging. |
| **Full charge every** | Charge to 100% at least every this many days (cell balancing). 0 = never. |
| **Phase** | The phase the battery is connected to, if it uses a single phase. |
| **Temperature sensor (optional)** | Battery temperature; when warm the plans use less power (see the temperature settings). |
| **Battery meter (optional)** | A meter on the battery's line that can be read directly, e.g. a kWh meter. Its power (+ into the battery = charging) is then used instead of the power sensor; for batteries whose integration does not give their own power, or as a check. |
| **Address of the battery meter** | IP address or host name of that meter. |

### Virtual battery {#device-virtual-battery}

A simulated battery that runs live alongside your real batteries in the selected plan mode, to see how a (second) battery would behave and what it would save. It is included in the battery plan, never in the house consumption.

| Field | Explanation |
|---|---|
| **Name** |  |
| **Twin of** | A real battery to copy: the virtual battery takes its properties (the fields below are then not used, the loss is its round-trip efficiency), starts at its state of charge and is planned in its place, on the grid as it would be without it. The real battery is then left out of the plan and keeps its own control (e.g. Omnibattery), so both can be compared. |
| **Capacity** |  |
| **Maximum charge power** |  |
| **Maximum discharge power** |  |
| **Minimum state of charge** |  |
| **Maximum state of charge** |  |
| **Starting state of charge** |  |
| **Phase** |  |
| **Minimum loss** | Round-trip loss (charge + discharge); per simulation step a random value between minimum and maximum is used. |
| **Maximum loss** | The planner uses the average of minimum and maximum. |
| **Full charge every** | Charge to 100% at least every this many days (cell balancing). 0 = never. |

### Time slot {#device-time-slot}

What the batteries do between two times on the chosen days, in the plan mode “Time slots”. A slot that ends before it starts runs past midnight. Outside the time slots the batteries work as zero on the meter.

| Field | Explanation |
|---|---|
| **Name** |  |
| **Start** |  |
| **End** |  |
| **Days** |  |
| **Action** |  |
| **Power** |  |
| **Until state of charge (optional)** | Charge up to, or discharge down to, this state of charge. Empty: the batteries' own limits. |

### Heating/cooling {#device-heating-cooling}

A heat pump, electric heating or airco. Its consumption stays part of the house consumption, but is measured apart so the forecast can follow the outdoor temperature (set a weather source in the settings). Add the room temperature (and its own outdoor sensor) to learn this device as a zone of its own.

| Field | Explanation |
|---|---|
| **Name** |  |
| **Sensor** | Sensor measuring the power (W) or current (A) of this device. |
| **Phase** | The phase this device is connected to, if it uses a single phase. |
| **Power L1 (optional, 3-phase)** | For a 3-phase device: a sensor per phase gives the exact split over the phases. Leave empty to spread the total evenly (phase 'all phases') or to use the phase chosen above. |
| **Power L2 (optional, 3-phase)** |  |
| **Power L3 (optional, 3-phase)** |  |
| **Room temperature (optional)** | A temperature sensor in the room this device heats or cools. Learns the desired room temperature (e.g. lower at night) and when heating starts, for a more accurate forecast. A device per room gives a zone per room. |
| **Own outdoor temperature (optional)** | E.g. the outdoor unit's sensor of an airco; otherwise the outdoor temperature from the settings is used. |

## Entities {#entities}

What HomeBatteryAssist creates (names as shown in Home Assistant).

| Name | Kind |
|---|---|
| House consumption | Sensor |
| Planning horizon | Sensor |
| Last decision | Sensor |
| State of charge | Sensor |
| Power | Sensor |
| Status | Sensor |
| Stored energy | Sensor |
| Usable energy | Sensor |
| Room to charge | Sensor |
| Full or empty at | Sensor |
| Charged energy | Sensor |
| Discharged energy | Sensor |
| Last full charge | Sensor |
| Capacity | Sensor |
| Round-trip efficiency (measured) | Sensor |
| Batteries state of charge | Sensor |
| Batteries power | Sensor |
| Batteries stored energy | Sensor |
| Batteries usable energy | Sensor |
| Batteries capacity | Sensor |
| Grid power | Sensor |
| Grid import | Sensor |
| Grid export | Sensor |
| PV power | Sensor |
| Excluded devices power | Sensor |
| Phase L1 load | Sensor |
| Phase L2 load | Sensor |
| Phase L3 load | Sensor |
| Expected consumption | Sensor |
| Consumption forecast accuracy | Sensor |
| PV forecast accuracy | Sensor |
| Price forecast accuracy | Sensor |
| Battery plan | Sensor |
| Realised value | Sensor |
| Phase discharging | Sensor |
| Phase charging (grid) | Sensor |
| Phase charging (solar) | Sensor |
| Phase grid only | Sensor |
| Test control | Sensor |
| Value today | Sensor |
| Difference with the real battery today | Sensor |
| Max export | Sensor |
| Recalculate | Button |
| Test: charge | Button |
| Test: discharge | Button |
| Test: stop | Button |
| Test inputs | Button |
| Sync with the real battery | Button |
| Does not follow its command | binary_sensor |
| Test power | number |
| Test duration | number |

## Actions {#actions}

Callable from automations and scripts (see [Working with other integrations](integration.md)).

### Recalculate {#action-recalculate}

`homebatteryassist.recalculate` — Recalculates the forecasts of HomeBatteryAssist now, e.g. when new prices or PV forecasts arrive. Only HomeBatteryAssist's own forecasts are recalculated; no device is controlled.

### Import consumption history {#action-import-history}

`homebatteryassist.import_history` — Fills the consumption history from Home Assistant's statistics, e.g. as starting data for forecasts. By default the house consumption is reconstructed from the configured sensors (grid, PV, excluded devices, batteries). Own measurements are never overwritten unless Replace is on.

| Field | Explanation |
|---|---|
| **Days** | How many days back to import (at most the retention of 28 days). |
| **Consumption sensor (optional)** | Take over the house consumption of this sensor instead of reconstructing it, e.g. from Omnibattery. |
| **Older battery power sensors (optional)** | Earlier power sensors of the battery (same direction), used for the period before its current sensor existed. |
| **Replace own measurements** | Let imported values replace own measurements in the same periods. |

### Adjust consumption forecast {#action-adjust-forecast}

`homebatteryassist.adjust_forecast` — Changes the expected house consumption for a period, e.g. from a script for a holiday, guests or a planned large load. Give a start (default: now), an end or duration, and exactly one change: a factor, an offset in W, a fixed power in W or an amount of energy in kWh (extra, or part of the expected consumption). Adjustments are kept until their end; the dashboard has a dialog for energy per day (button Expected consumption in the top bar).

| Field | Explanation |
|---|---|
| **Name** | Shown in the forecast and the decision log, and usable to remove it again. |
| **Start** | Default: now. |
| **End** | End of the period (or give a duration). |
| **Duration** | Length of the period (instead of an end). |
| **Factor** | Multiply the expected consumption, e.g. 0.3 while on holiday or 1.5 with guests. |
| **Extra power** | Add (or with a minus subtract) this power in W, e.g. 2000 for the oven. |
| **Fixed power** | Replace the expected consumption by this power in W. |
| **Energy** | An amount of energy in kWh spread evenly over the period, e.g. 1.5 for the washing machine (with a minus: less). |
| **Part of the expected consumption** | With Energy: the learned consumption of that day already holds this energy, it only happens in this period; the same energy is then taken from the rest of that day. Off: extra, on top of it. |

### Remove forecast adjustments {#action-clear-forecast-adjustments}

`homebatteryassist.clear_forecast_adjustments` — Removes adjustments of the consumption forecast by id or name; without id or name all adjustments are removed.

| Field | Explanation |
|---|---|
| **Id** | Id(s) of the adjustments to remove. |
| **Name** | Name(s) of the adjustments to remove. |

### Set forecast correction {#action-set-forecast-correction}

`homebatteryassist.set_forecast_correction` — Controls how a forecast is corrected from its running accuracy: learned (default), off (only measure) or manual with an own value. Optionally for one lead time and for a limited time.

| Field | Explanation |
|---|---|
| **Forecast** | Which forecast: consumption, PV, price or all. |
| **Mode** | learned: use the running accuracy; off: do not correct; manual: use the given value. |
| **Value** | Manual correction: a factor for PV (e.g. 0.85), an offset in W for consumption, an offset in the price unit for prices. |
| **Lead time** | Only for predictions made this long before the period (default: all). |
| **Duration** | Return to learned after this time (default: until changed). |

### Reset forecast accuracy {#action-reset-forecast-accuracy}

`homebatteryassist.reset_forecast_accuracy` — Forgets what was learned about a forecast (e.g. after switching PV forecast provider) and starts measuring again.

| Field | Explanation |
|---|---|
| **Forecast** | Which forecast: consumption, PV, price or all. |

### Set battery plan mode {#action-set-plan-mode}

`homebatteryassist.set_plan_mode` — Chooses the mode of the battery plan (advice): zero on the meter or arbitrage.

| Field | Explanation |
|---|---|
| **Mode** | nom or arbitrage. |

---

*Generated by `scripts/docs_reference.py` from the integration's texts.*
