# Measuring

## Grid connection and meter

- **Grid connection** with 1 or 3 phases and its size (1x10A up to 3x80A).
- **Grid meter**, chosen during setup:
  - **read directly**, about once a second, read-only (nothing on the meter is changed, and the meter's own integration keeps working):
    - HomeWizard P1 meter and kWh meters (1- and 3-phase), local API;
    - SMA Sunny Home Manager 2.0 / Energy Meter, Speedwire (only received: the meter sends its data on the network anyway);
    - Shelly Pro 3EM / 3EM and Shelly EM / Pro EM, local API *(not yet verified on a device)*;
    - Iammeter WEM3080 / WEM3080T, local API *(not yet verified on a device)*;

    Meters already in Home Assistant are offered automatically; any of these can also be entered by IP address;
  - **via the sensors of its integration** (e.g. a HomeWizard P1 is recognised and filled in);
  - **your own sensors** per phase: one signed sensor, or separate import and return sensors; power (W) or current (A).

New meters are added as [drivers](drivers.md).

## Batteries

Batteries are linked **read-only** through the entities of their own integration. Batteries of **Omnibattery** and **Marstek Modbus** are recognised and filled in, and their *battery driver* adds temperature, voltages, cell voltages, cycles, energy of today and measured efficiency; any other battery can be linked manually.

Optionally a battery gets an **external meter** on its line (e.g. a HomeWizard kWh meter, read directly): its power is then used instead of the power sensor — see [Drivers](drivers.md).

Per battery: state of charge, power, status, stored/usable energy, time to full/empty, charged/discharged energy, last full charge and realised return, plus totals over all batteries.

What a battery does by its own control (charging, supplying, stopping) is explained as periods in *Why*, compared with the plan — see [Planning](planning.md#explanation).

## Virtual batteries

Simulated what-if batteries (capacity, power, state-of-charge limits, losses, phase) that follow the plan live, so you can see what a (bigger) battery would bring before buying one. They also show phase protection and peak shaving at work.

## PV sources and excluded devices

**PV sources** and **excluded devices** (e.g. an EV charger): on one phase, on all phases (3-phase, spread evenly) or measured per phase with a sensor per phase. A PV source can also be a meter read directly (e.g. a HomeWizard kWh meter on the inverter's line).

An **excluded device** is not part of the house consumption: it is not in the consumption forecast, and **the battery never discharges for it** — the grid supplies it (solar surplus is still charged). This is also the way to keep a big consumer with its own power sensor (an EV charger, a sauna, a dryer on a smart plug) away from the battery. Whether excluded devices count for the peak limit is a setting of their own.

**Heating/cooling** (optional; a heat pump, electric heating or airco): measured like an excluded device, but its consumption **stays part of the house consumption**. It is recorded apart so the consumption forecast can follow the outdoor temperature. Optionally give it the room temperature (and its own outdoor sensor): it then becomes a zone, learned on its own — see [Forecasting](forecasting.md#outdoor-temperature-optional).

## Short peaks

Short, high peaks at random moments (a kettle, a microwave, an induction hob) need no sensor of their own: a **spike filter** [module](modules.md) recognises them in the house consumption while they happen. Settings section *Short peaks*, both on by default:

- **Do not discharge for random peaks** — zero on the meter does not discharge (extra) for a recognised peak; the grid supplies it.
- **Leave random peaks out of the average consumption** — their energy is recorded apart (`spike_w` in the history) and left out of the consumption forecast and its accuracy check, so the battery plan does not count on them.

The built-in filter (*Short peaks above a threshold*): a rise of at least **2000 W** above the usual consumption that is over within **5 minutes** is a peak (both adjustable). While it lasts it is not discharged for; when it lasts longer it is normal consumption (e.g. an oven) and is followed from then on — a kettle on top of the oven is again a peak.

A peak that **comes back regularly** — on at least half of the days of that day of the week at the same hour, at least twice in the last 4 weeks (e.g. the coffee every weekday morning) — is not random: it stays in the average and the battery covers it.

## House consumption

**House consumption** = grid + PV − excluded devices − battery charging, plus grid import/export, PV power and the load per phase as % of the main fuse.

Consumption is kept as history (28 days) for the [consumption forecast](forecasting.md#consumption); past consumption can be imported once from Home Assistant's statistics.

## Current per phase

The main fuse protects against **current**, not power: with standby devices, chargers and motors (power factor below 1) more current flows than power / 230 V suggests — at night easily 1 A on a phase that uses 30 W. So HomeBatteryAssist uses the current per phase wherever it can:

- **measured**: a directly read meter that sends it (SMA Home Manager, HomeWizard P1, Shelly 3EM, IAMMETER), or the optional **current sensors** per phase in the grid connection settings (with your own sensors);
- else **power / (measured voltage × power factor)**, with a voltage sensor or a meter that sends the voltage;
- else **power / 230 V**.

The history keeps the measured current per phase; from it the current that flows besides the power is learned per phase, and the battery plan counts with it for the coming slots. The battery's own share is converted with the measured voltage of its phase.
