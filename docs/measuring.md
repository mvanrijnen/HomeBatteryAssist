---
description: "How HomeBatteryAssist measures the grid per phase (HomeWizard P1, SMA Home Manager, Shelly), home batteries (Marstek), solar and house consumption in Home Assistant."
---

# Measuring

## Grid connection and meter

The grid connection is its own device, *Grid connection* (model: the meter read directly; next to the HomeBatteryAssist device, with the grid power, import, export and the load per phase). It is part of the basic setup, not a sub-item: change it with the cog of HomeBatteryAssist → *Grid connection*. Its button **Test inputs** listens to the meter for 10 seconds and then shows a notification with everything HomeBatteryAssist reads: the source and how many values it sent, per phase power, current, voltage, power factor and load, the power flows derived from it, and every sensor read (grid, PV sources, excluded devices, heating/cooling, batteries) with its value now — handy after setting up, or when something looks wrong.

- **Grid connection** with 1 or 3 phases and its size (1x10A up to 3x80A).
- **Grid meter**, chosen during setup:
  - **read directly**, about once a second, read-only (nothing on the meter is changed, and the meter's own integration keeps working):
    - HomeWizard P1 meter and kWh meters (1- and 3-phase), local API;
    - SMA Sunny Home Manager 2.0 / Energy Meter, Speedwire (only received: the meter sends its data on the network anyway; known by its serial number, so a new IP address changes nothing);
    - Shelly Pro 3EM / 3EM and Shelly EM / Pro EM, local API *(not yet verified on a device)*;
    - Iammeter WEM3080 / WEM3080T, local API *(not yet verified on a device)*;

    Meters already in Home Assistant are offered automatically; any of these can also be entered by IP address;
  - **via the sensors of its integration** (e.g. a HomeWizard P1 is recognised and filled in);
  - **your own sensors** per phase: one signed sensor, or separate import and return sensors, in power (W); a current sensor (A) has no sign, so it only goes in the optional current fields (phase protection).

New meters are added as [drivers](drivers.md).

## Batteries

Batteries are linked through the entities of their own integration, or optionally over a [direct connection](drivers.md#direct-battery-drivers) (then state of charge and power come from the battery itself). HomeBatteryAssist only reads them unless you switch on control (*Control on* and *Controlled by HomeBatteryAssist* in the battery's form; off by default). Batteries of **Omnibattery** and **Marstek Modbus** are recognised and filled in, and their *battery driver* adds temperature, voltages, cell voltages, cycles, energy of today and measured efficiency; any other battery can be linked manually.

Optionally a battery gets an **external meter** on its line (e.g. a HomeWizard kWh meter, read directly): its power is then used instead of the power sensor — see [Drivers](drivers.md).

Per battery: state of charge, power, status, stored/usable energy, time to full/empty, charged/discharged energy, last full charge and realised return (after wear: the cycle cost per kWh through the battery, as the plan counts it; attributes `before_wear` and `wear`), plus totals over all batteries.

### Today and measured efficiency

HomeBatteryAssist keeps its own energy counters per battery (from its power, at the battery's AC side), the virtual batteries included. From them come:

- **Charged / discharged today** — since local midnight; the same for every battery, whatever its integration offers.
- **Round-trip efficiency (measured)** — of a real battery: (discharged + stored energy now − stored energy then) / charged, over the last 30 days at most. Shown once at least one full capacity was charged and the stored energy changed little against it (so the guess for what is still inside hardly matters). When the battery moved while its power was not counted (Home Assistant restarting, its power sensor gone), the measurement starts anew from the next day, so energy the counters never saw does not skew it. Also a sensor per battery (*Round-trip efficiency (measured)*, with the days and kWh it is based on). The battery's own figure, if its integration has one, is shown next to it as *efficiency (according to the battery)*.

The battery card also shows the **cell difference** now (highest − lowest cell voltage) when the driver reads the cells.

### Does the battery follow its command?

Whoever controls a battery tells it to charge or discharge at a power — its own integration (e.g. Omnibattery), or HomeBatteryAssist itself when it controls the battery. The battery driver reads that **command** (for Omnibattery and Marstek Modbus: RS485 control mode, force mode and the charge/discharge power) and HomeBatteryAssist checks every 15 seconds whether the battery follows it: at least half of the commanded power (or of its maximum power, when lower), in that direction.

- Not following for **2 minutes** (setting *Tell after*, section *Battery follows its command*; commands from **100 W**, setting *Check commands from*) is told in *Why*, so starting up and ramping are no message.
- **Explained** — the battery is full or almost full (charging: from 5 % below its maximum its BMS lowers the charge power itself), cold (charging below 5 °C, with a temperature sensor), at its minimum (discharging), charging/discharging is switched off on the battery, its hysteresis holds charging back after a full charge, or it moves a steady part of the command in the right direction (at least 20 %, and 100 W: its own management limits the power, e.g. a cold battery charging at 800 W instead of 2500 W) — *Why* says so with the reason. That is no problem: no alarm, no notification, and HomeBatteryAssist's control keeps the battery.
- **Not explained** — a **problem**: *Why* says so, the battery's problem sensor *Does not follow its command* turns on (attributes: the command, the battery's power, since when), the battery card shows it in red, and a notification goes out when you chose *A battery does not follow its command*. Once it follows again for a minute, *Why* says that too.

The battery card shows the command it has now (*Command*: charge / discharge at a power, or stop). A battery that controls itself (no external control) has no command and is not checked.

What a battery does by its own control (charging, supplying, stopping) is explained as periods in *Why*, compared with the plan — see [Planning](planning.md#explanation).

### Test control (off by default) {#test-control-switched-off-for-now}

To test controlling a battery by hand — e.g. before switching on *Control on* — each real battery's device has a **test control**. **It is off by default**: the buttons send nothing; *Why* only says that the test control is switched off. Switch it on with the setting *Test control on* (section *Control*), only while you are there.

| Entity | What it is |
|---|---|
| *Test: charge* / *Test: discharge* (buttons) | Start a test: charge or discharge at the test power for the test duration. |
| *Test: charge full* (button) | Charge at the battery's max charge power until it is full, then on a little so the cells balance (until it takes less than 100 W, at most 30 min); 6 hours at most in all. Counts as a full charge. |
| *Test: stop* (button) | Stop the test at once; the battery goes back to its own control. |
| *Test power* (number) | The power of a test, 50 W up to the battery's max power. Default 300 W. |
| *Test duration* (number) | How long a test lasts, 1–30 minutes. Default 5 min. |
| *Test control* (sensor) | *Switched off (read-only)*, *Not possible* (its integration cannot be controlled), *Ready*, *Charging (test)* or *Discharging (test)*; attributes: the test settings, and the running test (power, since, until). |

Once switched on, a test:

1. **checks first**: the state of charge must be known, a charge test does not start when the battery is full, a discharge test not at or below its lowest allowed state of charge (max(min SoC, reserve SoC));
2. **sends the command over the battery's [direct connection](drivers.md#direct-battery-drivers)** when it has one — for a Marstek Venus: RS485 control on, the charge or discharge power and the force mode in its registers — **or else through the battery's own integration** — for Omnibattery: the battery's manual mode with the charge or discharge power — through the safety layer the control (*Control on*) uses too (a watchdog, always handing back, at most one new command every 5 s, power limits);
3. **stops by itself** when the time is up, when the battery becomes full or reaches its lowest allowed state of charge, when it [does not follow the command](#does-the-battery-follow-its-command), when a command fails, by *Test: stop* and when HomeBatteryAssist stops or reloads;
4. **always hands the battery back** to its own control (direct: power 0, force mode off, RS485 control off; through Omnibattery: Omnibattery takes over again), and tells in *Why* why it stopped and how much was charged and discharged.

Use it the first time on a real installation with someone present.

## Virtual batteries

Simulated what-if batteries (capacity, power, state-of-charge limits, losses, phase) that follow the plan live, so you can see what a (bigger) battery would bring before buying one. They also show phase protection and peak shaving at work.

Each battery has **Value today** (realised value since midnight, after wear), the virtual ones included.

### Twin of a real battery

To compare HomeBatteryAssist with the integration that controls your battery now (e.g. Omnibattery), make a virtual battery the **twin** of that battery (field *Twin of* when adding or changing it):

- it takes the real battery's properties (capacity, power, state-of-charge limits, round-trip efficiency as its loss, phase, full charges); its own fields are then not used;
- it **starts at the real battery's state of charge** (also when an existing virtual battery is made a twin); the button **Sync with the real battery** sets it to the real state of charge again at any moment (*Why* says so). It is not synced by itself, so both run on their own from the same start;
- it is **planned in the real battery's place**: the real battery is left out of the plan (and of *plan followed*), and keeps its own control (HomeBatteryAssist does not control a battery that has a twin, even with *Control on*);
- it acts on the grid **as it would be without the real battery**: the real battery's power is taken off the grid and its phase, so where the real battery already stores the solar surplus, the twin sees that surplus too. Its value is counted the same way, the real battery's on the grid as measured.

The sensor **Difference with the real battery today** on the twin = its value today − the real battery's (positive: HomeBatteryAssist's plan did better), with attributes for both values, both states of charge and how much more the twin stored since midnight (energy still inside is worth something tomorrow, so look at both). The overview then shows only the twin (its card with the real battery's state of charge and power and the difference today; the phases with *with the twin instead*): HomeBatteryAssist is linked with the twin only. A real battery can have one twin. Other virtual batteries go on as extra what-if batteries on top.

## PV sources and excluded devices

**PV sources** and **excluded devices** (e.g. an EV charger): on one phase, on all phases (3-phase, spread evenly) or measured per phase with a sensor per phase. A PV source can also be a meter read directly (e.g. a HomeWizard kWh meter on the inverter's line).

An **excluded device** is not part of the house consumption: it is not in the consumption forecast, and **the battery never discharges for it** — the grid supplies it (solar surplus is still charged). This is also the way to keep a big consumer with its own power sensor (an EV charger, a sauna, a dryer on a smart plug) away from the battery. Whether excluded devices count for the peak limit is a setting of their own.

**Heating/cooling** (optional; a heat pump, electric heating or airco): measured like an excluded device, but its consumption **stays part of the house consumption**. It is recorded apart so the consumption forecast can follow the outdoor temperature. Optionally give it the room temperature (and its own outdoor sensor): it then becomes a zone, learned on its own — see [Forecasting](forecasting.md#outdoor-temperature-optional).

## Short peaks

Short, high peaks at random moments (a kettle, a microwave, an induction hob) need no sensor of their own: a **spike filter** [module](modules.md) recognises them in the house consumption while they happen. Settings section *Short peaks*, both on by default:

- **Do not discharge for random peaks** — zero on the meter does not discharge (extra) for a recognised peak; the grid supplies it.
- **Leave random peaks out of the average consumption** — their energy is recorded apart (`spike_w` in the history) and left out of the consumption forecast and its accuracy check, so the battery plan does not count on them.

The built-in filter (*Short peaks above a threshold*): a rise of at least **2000 W** above the usual consumption that is over within **5 minutes** is a peak (both adjustable). While it lasts it is not discharged for; when it lasts longer it is normal consumption (e.g. an oven) and is followed from then on — a kettle on top of the oven is again a peak. A jump shorter than 15 seconds is no peak but sensor timing (grid, PV and battery sensors do not update at the same moment) and is not counted.

A peak that **comes back regularly** — on at least half of the days of that day of the week at the same hour, at least twice in the last 4 weeks (e.g. the coffee every weekday morning) — is not random: it stays in the average and the battery covers it.

## House consumption

**House consumption** = grid + PV − excluded devices − battery charging, plus grid import/export, PV power and the load per phase as % of the main fuse.

When the grid, a battery, an excluded device or a PV source that gave power in the last 30 minutes (while the sun is up) has no value, the house consumption is unknown for that moment (not counted with 0 W, which would record wrong consumption). An inverter that is unavailable at night, or still asleep after sunrise, counts as 0 W. A heating/cooling sensor without a value makes only the heating unknown.

Consumption is kept as history (28 days) for the [consumption forecast](forecasting.md#consumption); past consumption can be imported once from Home Assistant's statistics.

## Current per phase

The main fuse protects against **current**, not power: with standby devices, chargers and motors (power factor below 1) more current flows than power / 230 V suggests — at night easily 1 A on a phase that uses 30 W. So HomeBatteryAssist uses the current per phase wherever it can:

- **measured**: a directly read meter that sends it (SMA Home Manager, HomeWizard P1, Shelly 3EM, IAMMETER), or the optional **current sensors** per phase in the grid connection settings (with your own sensors);
- else **power / (measured voltage × power factor)**, with a voltage sensor or a meter that sends the voltage;
- else **power / 230 V**.

The history keeps the measured current per phase; from it the current that flows besides the power is learned per phase, and the battery plan counts with it for the coming slots. The battery's own share is converted with the measured voltage of its phase.

The **final check** that holds the batteries within the phase limit (the last step before a power is used, after the plan, protection and an interceptor) works from the **worst case** of what is measured, so the current stays under the limit whatever the exact values are:

- a measured current in whole amps (many meters round it, e.g. a P1 port) can be up to half an amp more;
- without a measured voltage it counts with **207 V**, the lowest grid voltage allowed (230 V − 10 %): every W of the house and of a battery then counts for the most current;
- without a measured current or power factor the reactive part cannot be known; only the phase margin covers it.

So near the limit the batteries get a little less room than the exact values would leave; with a meter or sensors that send the **current and voltage** per phase that is the least.
