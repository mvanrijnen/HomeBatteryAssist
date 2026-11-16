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

Per battery: state of charge, power, status, stored/usable energy, time to full/empty, charged/discharged energy, last full charge and realised return, plus totals over all batteries.

What a battery does by its own control (charging, supplying, stopping) is explained as periods in *Why*, compared with the plan — see [Planning](planning.md#explanation).

## Virtual batteries

Simulated what-if batteries (capacity, power, state-of-charge limits, losses, phase) that follow the plan live, so you can see what a (bigger) battery would bring before buying one. They also show phase protection and peak shaving at work.

## PV sources and excluded devices

**PV sources** and **excluded devices** (e.g. an EV charger): on one phase, on all phases (3-phase, spread evenly) or measured per phase with a sensor per phase. A PV source can also be a meter read directly (e.g. a HomeWizard kWh meter on the inverter's line).

## House consumption

**House consumption** = grid + PV − excluded devices − battery charging, plus grid import/export, PV power and the load per phase as % of the main fuse.

Consumption is kept as history (28 days) for the [consumption forecast](forecasting.md#consumption); past consumption can be imported once from Home Assistant's statistics.
