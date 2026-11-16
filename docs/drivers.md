# Drivers: adding a device or price source

Prices, batteries, grid meters and PV meters are read through *drivers*, one per kind of source. Unlike [modules](modules.md), drivers are part of the integration: a new driver is added to the code (and shared with everyone through a pull request).

| Kind | Package | Template |
|---|---|---|
| Price sources (incl. forecast-only sources) | `engine/prices/` | `template.py` |
| Batteries (reading; write methods are defined but never used) | `engine/batteries/` | `template.py` |
| Grid and PV meters read directly | `engine/meters/` | `template.py` |

Every kind has an empty template that is only a code example (never offered in the settings).

## Rules

- A driver **only reads**: Home Assistant states and registries, a read-only local API, or data a device broadcasts anyway. It never changes a setting and never opens a connection that could compete with the device's own integration (e.g. a Marstek Venus allows only one Modbus TCP client).
- Battery drivers may *describe* how a battery would be controlled (write methods), but HomeBatteryAssist never calls them.

## Adding one

1. Copy the template of the kind and fill it in.
2. Add it to `DRIVERS` in the package's `__init__.py`.
3. Add tests, and mark it **verified** only after testing it on a real installation.

## Supported now

- **Price sources**: DynTarNL (verified), Nord Pool, Tibber, EnergyZero, easyEnergy, ENTSO-e, EPEX Spot, Frank Energie, Zonneplan, Amber Electric, PVPC, Essent, Pure Energie, or any sensor with prices in its attributes.
- **Batteries**: Omnibattery and Marstek Modbus (verified for reading); any other battery can be linked manually through its entities.
- **Meters read directly**: HomeWizard P1 and kWh meters, SMA Sunny Home Manager / Energy Meter (Speedwire) — verified; Shelly Pro 3EM / 3EM / EM / Pro EM and Iammeter WEM3080(T) — from their API documentation, not yet verified on a device.

A PV *forecast* is not a driver but a [module](modules.md) (PV forecast source).
