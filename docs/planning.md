# Planning (advice)

HomeBatteryAssist plans what the batteries could best do over the [planning window](forecasting.md#planning-window). **For now it is advice**: in this phase of development no physical battery is controlled; virtual batteries follow the plan, as a simulation. The plan is designed to become battery commands 1:1.

## Plan modes

Every plan mode is a [planner module](modules.md); all are calculated every cycle, with the expected saving compared with no battery:

- **More or less sun than forecast**: in every mode the batteries follow the solar surplus that is really there — an unexpected surplus is stored on top of the plan, missing sun is not taken from the grid. See [When the sun differs from the forecast](#when-the-sun-differs-from-the-forecast).
- **Zero on the meter (NOM)**: charge with surplus solar power, supply the house on shortage — not excluded devices (e.g. an EV charger) and, when switched on, not random [short peaks](measuring.md#short-peaks).
- **Arbitrage** (own use): charge when power is cheap, supply the house when it is expensive.
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
| **Arbitrage and other plans per slot** | stored **on top of** the planned power — never more than the surplus, so never from the grid | the part of a planned charge that was to come **from the sun** is only charged as far as the surplus is really there: the grid does not fill in for the missing sun; a planned charge **from the grid** goes on |
| **A planned discharge** | followed as planned | followed as planned |
| **Why** | after **5 minutes**: *Unexpected solar surplus* | after **5 minutes**: *Less solar than forecast* |

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

In this phase of development the [virtual batteries](measuring.md#virtual-batteries) do this; your real batteries are controlled by their own integration. Once HomeBatteryAssist controls batteries, it uses the same rule.

## Rules and limits

- **Max. cycles per day** for arbitrage, to spare the batteries.
- **Your own rules**: a reserve state of charge (backup), max. charge/discharge power of all batteries together, a target grid power for zero on the meter, discharge only from a price, charge from the grid only up to a price, a minimum arbitrage margin, and a charge hysteresis.
- **Warm batteries**: with an optional temperature sensor per battery the plans use less power above a temperature limit.
- **Negative prices**: charging when import is negative, making room before a negative export price.
- **Night reserve**: from the evening (the sun gone) until the sun is up again (per the PV forecast) the batteries are not discharged below this state of charge. Arbitrage charges from the grid for it at the cheapest moment before sunrise when needed; zero on the meter only keeps it. Without a PV forecast it does nothing.
- **Peak shaving** on the total grid import: the plan keeps energy in reserve for peaks; virtual batteries shave them live. With a **peak reserve** the batteries only discharge for the import above the peak limit once they are below that state of charge.
- **Phase limits**: the plan never lets a phase exceed the main fuse (with an adjustable safety margin). The share of each phase is learned from your history.
- **Phase protection** (virtual batteries): when a phase is overloaded, batteries on that phase take load off it within seconds. The load per phase is the **current** (what the main fuse sees): measured when the meter sends it (an SMA Home Manager does, with voltage and power factor), else power / (measured voltage × power factor), else power / 230 V. Phase protection and peak shaving cannot be undone by an [interceptor](#interceptor-your-last-say). Without a grid measurement (meter gone for 10 s) the batteries do nothing until it is back; *Why* says so.
- **Distribution over several batteries**: as few batteries as possible at a sensible minimum power, kept in balance.

## Periodic full charge

Per battery (for the battery management's calibration), every so many days, at the cheapest moment, optionally on a preferred weekday and preferably with solar power; batteries charge fully at the same time when the grid connection allows it. The full charge is always inserted **after** the planner, whatever planner is chosen.

## Reaction on the meter

Settings section *Reaction on the meter*: the batteries are adjusted to the grid meter **every 5 seconds** (adjustable, 1–60 s), by default on the **average over that round**, so a single outlier steers nothing. With **react at once on a large jump** (on by default, 1000 W) an oven or EV charger switching on gets an extra round right away. Phase overload and the peak limit are always acted on at once. Every second would hardly bring anything: the batteries take 1–2 seconds themselves, and a few seconds of delay on a 2 kW jump is about 2 Wh. When control is switched on later, a new power goes to a battery at most every 5 seconds; a change between charging, discharging and idle is never held back. For now this drives the virtual batteries.

## Interceptor (your last say)

Before a command would go to a battery, the chosen **interceptor** [module](modules.md#interceptor--enginecontrolinterceptorsbasepy) gets the proposal per battery — with the batteries, phases, grid, prices and plan — and may approve it, **limit** it (less power, same direction), **hold it back** (0 W) or **release** the battery (back to its own control); what is held back may be taken over by the other batteries. It can only intercept, never ask more. After it comes HomeBatteryAssist's own final check (phase limits, power and state of charge), which always wins. None by default (settings section *Planning*); *Why* and the overview say what it holds back or limits. For now it acts on the virtual batteries.

## Explanation

The plan is explained in plain language, as periods — what happens until when, and why — and compared with no battery, e.g.:

> *Until 17:00 the batteries do not discharge and the house runs on the grid, because power is not expensive enough now (€ 0.31 per kWh): they keep their energy for Mon 17:00-20:00, when power costs € 0.46 per kWh.*

What each real battery does by its own control is explained as periods too — since when it charges or supplies, with what (solar power or the grid), until when it is expected to go on, and what happens when it stops — and whether that matches the plan.

## Plan check

Afterwards, the plan is compared with what really happened, per day (dashboard, *Return* tab).
