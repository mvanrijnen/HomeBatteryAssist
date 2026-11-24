---
description: "Battery plans in Home Assistant: zero on the meter (NOM), arbitrage with dynamic prices, phase protection, peak shaving, reserves and periodic full charges."
---

# Planning (advice and control) {#planning-advice}

HomeBatteryAssist plans what the batteries could best do over the [planning window](forecasting.md#planning-window). **By default it is advice**: virtual batteries follow the plan as a simulation, and the integration that controls your battery keeps doing so. With the setting *Control on* (section *Control*, off by default, alpha) HomeBatteryAssist controls the batteries marked *Controlled by HomeBatteryAssist* itself, following this plan (or zero on the meter), with the same rules and limits.

## Plan modes

Every plan mode is a [planner module](modules.md); all are calculated every cycle, with the expected saving compared with no battery:

- **Less consumption than forecast**: a planned discharge goes no further than the house needs now, so battery energy never goes into the grid unless the plan chose that export.
- **More or less sun than forecast**: in every mode the batteries follow the solar surplus that is really there — an unexpected surplus is stored on top of the plan (unless the plan exports the surplus because storing does not pay), missing sun is never taken from the grid. See [When the sun differs from the forecast](#when-the-sun-differs-from-the-forecast).
- **Zero on the meter (NOM)**: charge with surplus solar power, supply the house on shortage — not excluded devices (e.g. an EV charger) and, when switched on, not random [short peaks](measuring.md#short-peaks).
- **Arbitrage** (own use): charge when power is cheap, supply the house when it is expensive. Energy still in the battery at the end of the window is valued at what it saves later (the average price, minus the wear of using it then; the plan's cost and saving count it the same way); but when the PV forecast reaches further than the prices and the next sun has a surplus that fills the battery anyway, the part it fills is only worth that surplus's export price. So in summer the battery also covers the evening and night instead of the grid, as long as the price minus wear (*cost per cycle*) and the *minimum arbitrage margin* make it worthwhile. Diagnostics: `outlook`.
- **Full arbitrage**: like arbitrage, but may also discharge to the grid when the export price makes that worthwhile.
- **Time slots**: your own slots (days, times, charge/discharge/idle, power, until a state of charge), zero on the meter outside them.
- **Manual**: a fixed charge or discharge power.
- **Your own planner**: see [Modules](modules.md).

Choose the mode in the settings, on the dashboard or with the action `set_plan_mode`. HomeBatteryAssist checks every plan afterwards (power, phases, state of charge, price rules) — see [the final say](modules.md#homebatteryassist-keeps-the-final-say).

## When the sun differs from the forecast

A plan is made with the forecast PV and consumption per slot. When the sun does something else — a cloud, or a sunny spell nobody forecast — the batteries follow what is **really measured**, not the forecast.

HomeBatteryAssist compares the **surplus** now (PV − house − excluded devices: what the batteries could store) with the surplus **expected** for this hour (the PV forecast, corrected, minus the consumption forecast):

| | More sun than forecast | Less sun than forecast |
|---|---|---|
| **When** | at least **300 W** left over, and less than half of it was forecast | at least **300 W** was forecast, and less than half of it is left over |
| **Zero on the meter** | stored, like any surplus | less to store; on a shortage the batteries supply the house from what they hold |
| **Arbitrage and other plans per slot** | stored **on top of** the planned power — never more than the surplus, so never from the grid; only when the plan stores the forecast surplus itself: when it exports it (storing does not pay at that export price), the extra goes to the grid too | the part of a planned charge that was to come **from the sun** is only charged as far as the surplus is really there — also below the threshold: the grid never fills in for the missing sun; a planned charge **from the grid** goes on |
| **A planned discharge** | followed as planned | followed as planned |
| **Why** | after **5 minutes**: *Unexpected solar surplus* | after **5 minutes**: *Less solar than forecast* |

The threshold decides when an extra surplus is stored on top and when *Why* tells it; a shortage is never filled in from the grid, however small.

!!! example "Example"
    Arbitrage planned to charge 1,000 W with solar power between 12:00 and 13:00.

    - **A cloud**: only 200 W is left over. The battery charges 200 W — not 1,000 W of which 800 W from the grid.
    - **More sun**: 2,500 W is left over while 1,000 W was forecast. The battery charges 2,500 W (as far as it can and is not full).
    - Had the plan charged 2,000 W at a cheap price, 800 W of it from the sun, the cloud leaves 1,200 W from the grid + 200 W from the sun.

What happens next:

1. **At once**: the batteries react at their next round (every 5 s by default). Only the message in *Why* waits, so a passing cloud or a gap in the clouds gives no message.
2. **After 5 minutes**: *Why* says it — how much is left over, what was forecast, and what it means for the batteries. It can also be sent as a [notification](integration.md#notifications) (kind *Unexpected solar surplus or shortage*).
3. **Every quarter of an hour**: the plan is calculated again with the real state of charge, so a battery that is fuller or emptier than planned gets a fitting plan (e.g. less charging from the grid tonight).
4. **When it is over** (10 minutes without it): a second message gives the energy left over and how much was forecast.
5. **Afterwards**: the [PV correction](forecasting.md#pv-correction) compares the forecast with what was measured and corrects forecasts that are consistently off.

Both values can be set under **Settings → Solar forecast**: *More or less sun than forecast: from this difference* (default 300 W) and *More or less sun than forecast: tell after* (default 5 min). This needs a measured [PV source](measuring.md) and a PV forecast; without them a plan is followed as it is.

The [virtual batteries](measuring.md#virtual-batteries) do this, and so do the real batteries HomeBatteryAssist controls (*Control on*); a real battery under its own integration's control follows that integration.

## Rules and limits

- **Max. cycles per day** for arbitrage, to spare the batteries.
- **Your own rules**: a reserve state of charge (backup), max. charge/discharge power of all batteries together, a target grid power for zero on the meter, discharge only from a price, charge from the grid only up to a price, a minimum arbitrage margin, a margin for estimated prices (charging, discharging or keeping energy for a slot whose price is not published yet must bring at least that much more per kWh than doing it at a published price: the estimate may be off; default 0.02, 0 = off; the charge-the-car advice weighs it the same way), and a charge hysteresis (once a battery was full it charges again only after dropping below the band; every plan starts from the state the batteries have now, the virtual ones from the simulator and the real ones from their state of charge; with several batteries the plan holds back only when every battery is held).
- **Warm batteries**: with an optional temperature sensor per battery the plans use less power above a temperature limit (without a sensor: the temperature its integration reports). *Why* tells when that starts (with the temperature and the powers the plans use) and when the battery has cooled down again (1 °C below the limit); *The plan at a glance* shows it on the *Power* line while it lasts. **Learning (being recorded)**: per real battery HomeBatteryAssist records what it could do at its temperature — per 2 °C, how often it gave clearly less than it was asked (not near full or empty, not switched off) and how much — and per hour its temperature next to the outdoor temperature and its use. The temperature comes from the battery's temperature sensor, else from what its integration reports. Shown in the diagnostics for now; later the plans will use it per slot with the battery's expected temperature (e.g. less charge power in a cold garage).
- **Negative prices**: charging when import is negative, making room before a negative export price.
- **Night reserve**: from the evening (the sun gone) until the sun is up again (per the PV forecast) the batteries are not discharged below this state of charge. Arbitrage charges from the grid for it at the cheapest moment before sunrise when needed; zero on the meter only keeps it. With several batteries every battery keeps its own reserve (also the peak reserve), so one battery is not emptied while another holds the reserve for all. Without a PV forecast it does nothing.
- **Peak shaving** on the total grid import: the plan keeps energy in reserve for peaks; virtual batteries, and real batteries under HomeBatteryAssist's control, shave them live. With a **peak reserve** the batteries only discharge for the import above the peak limit once they are below that state of charge. Peak shaving keeps the reserve and the night reserve (only the peak reserve is for peaks).
- **Phase limits**: the plan never lets a phase exceed the main fuse (with an adjustable safety margin). The share of each phase is learned from your history, per hour of the day for the consumption and for the PV (east/west roofs on other phases).
- **Phase protection** (virtual batteries and batteries HomeBatteryAssist controls): when a phase is overloaded, batteries on that phase take load off it within seconds. The load per phase is the **current** (what the main fuse sees): measured when the meter sends it (an SMA Home Manager does, with voltage and power factor), else power / (measured voltage × power factor), else power / 230 V. A battery only changes the active power, so with a reactive part the current falls less than the power: the batteries take off enough active power to bring the current itself under the limit. The final check that holds every battery within the phase limit works from the worst case of what is measured (a current in whole amps up to half an amp more, 207 V without a measured voltage; see [Current per phase](measuring.md#current-per-phase)). Phase protection and peak shaving cannot be undone by an [interceptor](#interceptor-your-last-say). Without a grid measurement (meter gone for 10 s; HomeWizard API v2: 25 s; a grid sensor not reported anew for 90 s, frozen while its integration hangs; a battery power sensor frozen like that at 50 W or more) the batteries do nothing until it is back; *Why* says so.
- **Distribution over several batteries**: as few batteries as possible at a sensible minimum power, kept in balance. Setting *Charging several batteries* (section *Limits and reserve*): **one after the other** (default) charges the emptiest battery first at its full power and the next only for what it cannot take, because a battery charges less efficiently at low power; **parallel** charges them at the same time. **Never one battery charging while another discharges**: that only moves energy between them, with the losses of both. Phase protection or peak shaving, then a full charge, sets the direction and the batteries against it stop; otherwise the net stands (the grid sees the same). One exception: when two phases are overloaded the opposite way (one importing, one exporting too much), the main fuse comes first and both are relieved. The system's max charge and discharge power (*Limits and reserve*) is a hard limit, also for phase protection and peak shaving.

## Export limit (PV inverters)

When the solar surplus can no longer go into the batteries, it goes to the grid. At a negative export price that costs money; and a grid operator may cap the export. The sensor **Max export** on the *Grid connection* device says how much may be exported now:

- **0 W** — do not export, because it does not earn money: the export price of the tariff (for a dynamic contract the market price minus the supplier's fee) minus the **export costs** of your contract (setting *Export costs*, e.g. the export fee or penalty of a fixed contract) is below the *limit price* (default 0). So: a very low or negative price, or a fixed contract whose export costs are higher than what it pays, means no export. The batteries still store what they can; the inverters would produce no more than the house and batteries use. *No export when it earns too little* switches this off.
- **0 W always** with the setting **Never export** (optional): export is stopped altogether, whatever the price;
- **a fixed maximum** (setting *Fixed maximum export*, e.g. the grid operator's limit; 0 = none);
- else the **most that can be exported**: the grid connection's maximum (phases × fuse × 230 V), or less when the *breaker of the inverter* is set for every PV source (A per phase × 230 V, × 3 on all phases; set per PV source) — then no more than can pass the inverters' breakers, e.g. a 3-phase inverter on 3 × 20 A = 13.8 kW on a 3 × 25 A connection (17.25 kW). Not limited.

Attributes: *limited*, the reason, the limit as current per phase, the export price, the export now, what would be curtailed now and today, and per PV source what its inverter driver would send. With a [twin](measuring.md#twin-of-a-real-battery) the export is counted as with the twin instead of the real battery.

**Ahead:** when the plan clearly expects export while exporting costs money (or earns less than the limit price), so export would be stopped (at least an hour, at least 0.5 kWh the batteries cannot store, e.g. a sunny afternoon at negative prices), *Why* tells it beforehand once: from when to when, the lowest net export price and the kWh; the sensor's attribute *expected* lists these periods.

**No guarantee of zero export:** a limit is followed after the fact (a measurement, the reaction of the inverter, clouds passing), so a short moment of export will always happen now and then.

**What an inverter would get.** A Sunny Home Manager limits the *export* itself, so it gets the export limit (e.g. 0 W). An inverter on its own (SunSpec, SMA Modbus) limits its *production*: it may give what the house and the batteries use now plus the export allowed (PV + grid + limit), so at 0 W export the house is still fed by the sun. Plus what the real batteries could still charge on top of their charge now (else a battery on its own zero-on-meter control never gets more). With several such inverters that is split by what each gives now (a shaded one cannot use a larger share), each at most its breaker, the rest going to the others. The sensor's attribute *Production limit (inverters)* shows the total.

**In this phase nothing is sent to an inverter.** *Why* tells when the export would be limited (to what, why, how much less the inverters would produce) and when it ends (minutes, kWh not exported, what that was worth at the export price). Settings section *Export limit (PV inverters)*. Which inverter could be limited is chosen per PV source (*Inverter driver*, *Address for the driver*: the IP address of the device the driver talks to — with a Sunny Home Manager the Home Manager's address, the same for every SMA inverter behind it; otherwise the inverter's) — see [Drivers](drivers.md#pv-inverters--enginedevicesinverters).

**Possible power.** A PV source can get a sensor with what it could produce now (*Possible power*, e.g. an SMA inverter's register read with Home Assistant's [Modbus integration](https://www.home-assistant.io/integrations/modbus/); the register differs per model). Where it is higher than the measured power, PV is being held back: the history, the PV correction and the forecast accuracy then learn from what the sun gave (not from the curtailed power), and *Max export* shows the PV held back now. The house consumption stays measured.

## Periodic full charge

Per battery (for the battery management's calibration), every so many days, at the cheapest moment, optionally on a preferred weekday and preferably with solar power; never two batteries at the same time: the next one gets the cheapest block after (or before) the other; with *Charging several batteries* on one after the other (default) the emptiest goes first, on parallel the one whose full charge is due first. Each battery's full charge goes to that battery itself (not spread over all of them). The full charge is scheduled before planning and always added by HomeBatteryAssist's final check of the plan, whatever planner is chosen (no price rule stops it): the state of charge, grid and costs of the plan count with it, and what no longer fits after it is not charged. The block is sized for the worst case (the battery at its minimum by then, since it can be days later), at the battery's power within the system max and a warm battery's derating, and made as long as it takes to reach 100 % within the phase and peak limits; blocks are compared by what the energy charged costs. It stops as soon as the battery is full. With several batteries, one above its maximum (after a full charge) or below its minimum does not hide another battery's room.

**When.** Each battery has its own *Full charge every* (battery form, default 14 days; 0 = off). The clock runs from its last full charge: 99.5 % or more counts, also when it happened by itself (a sunny day, arbitrage), and starts the interval again. In the last days before the deadline — setting *Force full charge within* (section *Full charge*, 1–14 days, default 3) — the cheapest block that ends before the deadline is chosen, never further ahead than the prices are known. Only when that did not work (Home Assistant off, no prices, the battery released) and the deadline has passed, the full charge is caught up within that many days after it. Example, interval 14 days and 3 days: full on the 1st → the deadline is the 15th, the full charge falls between the 12th and the 15th, and only when it was missed between the 15th and the 18th.

## Reaction on the meter

Settings section *Reaction on the meter*: the batteries are adjusted to the grid meter **every 5 seconds** (adjustable, 1–60 s), by default on the **average over that round**, so a single outlier steers nothing. With **react at once on a large jump** (on by default, 1000 W) an oven or EV charger switching on gets an extra round right away. Phase overload and the peak limit are always acted on at once. Every second would hardly bring anything: the batteries take 1–2 seconds themselves, and a few seconds of delay on a 2 kW jump is about 2 Wh. These rounds drive the virtual batteries and, with *Control on*, the real batteries marked *Controlled by HomeBatteryAssist*: a new power goes to a real battery at most every 5 seconds (longer when the battery's driver needs it); going idle is never held back; a change between charging and discharging is held to the same 5 seconds and deadband (no flapping around 0 W).

**Control quality** (diagnostic sensor, with virtual batteries): how well zero on the meter holds the grid at its target over the last 10 minutes — *stable*; *oscillating* (the grid keeps swinging past the target by 100 W or more while the battery power keeps reversing: the control overshoots); *sluggish* (on average 150 W or more off while the batteries had room: it lags behind); *idle* (too few rounds of zero on the meter: another mode, a protection, batteries full or empty). Attributes: rounds, mean error, crossings, reversals. It measures the virtual batteries; what the real batteries did, and why, shows in the dashboard tab *Log*.

**Control (zero on the meter)** (*Reaction on the meter*): *Direct* sets the batteries every round to what the grid asks. A real battery reacts with a delay and ramps its power, and then direct overshoots: while the battery is still ramping, the meter shows the old shortage and it is added again. *PD control* (proportional-derivative) steers towards it in steps: *Kp* is the part of the difference closed per round (1 = all, as direct), *Kd* reacts to how fast the batteries' power changes and damps an overshoot (on the measurement: a jump in what the house asks gives no kick, and a battery held at a limit builds up nothing), *max. power change per round* and *direction hysteresis* (no switch between charging and discharging for a small power) keep it calm. Like a real controller it builds on its previous command and sees on the meter what the batteries really do. To see the effect, the virtual batteries can simulate a real battery's reaction: *simulated battery delay* (seconds before it follows a new power, from the moment it was given, also within a round) and *simulated battery ramp* (W per second; both 0 = at once). The control quality then shows whether a setting overshoots (*oscillating*) or lags (*sluggish*). With a battery that reacts at once, direct gives exactly what the grid asks, as before. On a real battery the control steers on the meter alone, from its previous command: half of what the meter shows per round, the direction only turning for at least 100 W, no Kd (a real battery's own power reading comes seconds late and must not steer); with *PD control* chosen it takes your Kp, max. power change and hysteresis, still without Kd. If charge and discharge still alternate 4 times within a minute, the control pauses for 10 minutes.

## Interceptor (your last say)

Before a command would go to a battery, the chosen **interceptor** [module](modules.md#interceptor--enginecontrolinterceptorsbasepy) gets the proposal per battery — with the batteries, phases, grid, prices and plan — and may approve it, **limit** it (less power, same direction), **hold it back** (0 W) or **release** the battery (back to its own control); what is held back may be taken over by the other batteries. It can only intercept, never ask more. After it comes HomeBatteryAssist's own final check (phase limits, power and state of charge), which always wins. None by default (settings section *Planning*); *Why* and the overview say what it holds back or limits. It acts on the virtual batteries and on the real batteries HomeBatteryAssist controls.

## Explanation

The plan is explained in plain language, as periods — what happens until when, and why — and compared with no battery, e.g.:

> *Until 17:00 the batteries do not discharge and the house runs on the grid, because power is not expensive enough now (€ 0.31 per kWh): they keep their energy for Mon 17:00-20:00, when power costs € 0.46 per kWh.*

What each battery does is explained as periods too — since when it charges or supplies, with what (solar power or the grid), until when it is expected to go on, and what happens when it stops — and whether that matches the plan, with the plan's reason (e.g. *That matches the plan: power is expensive then (€ 0.42 per kWh).*). A real battery follows its own control, or HomeBatteryAssist's when it is controlled (*Control on*); a virtual battery (and a twin) shows what HomeBatteryAssist would do, until the end of the plan's phase. The plan story itself is told again when what the plan does now changes, and otherwise at most every 3 hours.

**The plan at a glance** (dashboard *Overview*, sensor *Plan explanation*): a few lines that are always there —

- **Now**: what the batteries do, until when and why, with the price now and the **price thresholds** of the plan, e.g. *Waiting until Mon 08:00: the batteries keep their energy for Mon 16:00 (power then € 0.50 per kWh). Power costs € 0.412 per kWh now. Using the batteries only pays above € 0.474 per kWh, charging from the grid below € 0.301 (after losses, wear and margin).*
- **Next**: the next change, with its energy and reason;
- **Plan**: the charge and supply periods in one line and the expected saving compared with no battery;
- **Sun**: the solar production still expected today and tomorrow, and the surplus the batteries can store;
- **Cheapest**: the cheapest published price from now on and how far the published prices reach.

The thresholds come from the arbitrage plan itself, not from a rule of thumb: they are what a kWh in the batteries is worth in the rest of the plan (the cost of the rest of the plan with a little more or less stored), after the losses of charging and discharging, the wear, the minimum margin and the margin for estimated prices, and within your price rules. So they also say why the plan does *not* act at a price that looks good: e.g. energy that would be used in the morning at € 0.47 is worth more in the evening at € 0.51 when the sun cannot refill it in between, and charging from the grid at € 0.36 does not pay when tomorrow's solar surplus fills the battery anyway (that would push solar power to the grid at the export price). In a slot that charges or supplies, the threshold is the worth of that block of energy on average: up to which price that charge pays, from which price that supply pays. Plans without prices (zero on the meter, fixed modes) have no thresholds.

**Stable from cycle to cycle.** The plan is made again every few minutes. So that a price right at a threshold does not make it switch the batteries on and off every time, arbitrage changes what the batteries do *now* compared with the previous plan only when that brings at least € 0.01 per kWh changed; later slots are planned freely.

## Plan check

Afterwards, the plan is compared with what really happened, per day (dashboard, *Return* tab).

**Plan followed**: per slot, how closely the batteries' power matched their share of the plan (100 % = exactly; idle as planned counts as followed), apart for the **virtual** and the **real** batteries; the plan is for all batteries together, each group's share is its share of the capacity. Shown per day in the plan check and for the last 7 days on the *Accuracy* tab.

- **Virtual batteries** follow the plan: lower means they hit a limit (full, empty, a phase) or the sun differed from the forecast.
- **Real batteries**: under their own integration, their figure shows how close that comes to HomeBatteryAssist's plan; controlled by HomeBatteryAssist, lower means they hit a limit or did not follow their command.
