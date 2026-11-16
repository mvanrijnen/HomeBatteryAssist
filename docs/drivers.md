# Drivers: connecting a device

**Drivers** connect HomeBatteryAssist to physical *devices*: batteries and meters (layer 1, `engine/devices/`, see [Architecture](architecture.md)). Everything else that can be swapped — planners, consumption forecasters, price sources, tariffs, PV forecast sources — is a [module](modules.md).

Drivers are part of the integration: a new driver is added to the code and shared with everyone through a pull request.

## Rules

- A driver **only reads**: Home Assistant states and registries, a read-only local API, or data a device broadcasts anyway. It never changes a setting and never opens a connection that could compete with the device's own integration (e.g. a Marstek Venus allows only one Modbus TCP client).
- Battery drivers may *describe* how a battery would be controlled (write methods), but HomeBatteryAssist never calls them.
- Mark a driver **verified** only after testing it on a real installation.

## Batteries — `engine/devices/batteries/`

A battery driver has two parts (`base.py`):

1. **Model** — what the battery *is*, by inheritance **brand → type range → type**:

   ```
   marstek/__init__.py     class Marstek(BatteryModel)          brand = "Marstek"
   marstek/venus.py        class MarstekVenus(Marstek)          range = "Venus"
   marstek/venus_e_v3.py   class MarstekVenusEV3(MarstekVenus)  type = "Venus E v3", 5.12 kWh, 2500 W, …
   ```

   A type only sets what it knows for sure: capacity, charge/discharge power, usable part, rated cycles, warranty, and the model names integrations report for it (`models`). When a battery is linked, these are starting values for what its integration does not tell. Add a new type to `MODELS` in `__init__.py`.
2. **Reader** — how the battery is *read*, one per integration in `integrations/`: its `profile` recognises the batteries of that integration (state of charge and power sensor, starting values) and `telemetry` adds live details (temperature, voltages, cell voltages, cycles, energy today, efficiency). A reader also says whether it **serves as the battery's meter** (`is_meter`): whether its integration gives the battery's own power. Omnibattery and Marstek Modbus do (`ac_power`); a battery whose integration does not, needs an external meter. Add a new reader to `READERS` in `integrations/__init__.py`.

**Battery meter:** a battery can also get an external meter (setting *Battery meter* in the battery's form, with its address): its power (+ into the battery = charging) is then used instead of the power sensor — for a battery whose integration does not serve as its meter, or as a check. If the meter has no value for a moment, the power sensor counts again.

One battery type can be read through several integrations; the model and the reader are chosen separately. `template.py` shows both. The **virtual battery** (`virtual.py`) is a simulated device that follows the plan.

## Meters — `engine/devices/meters/`

One file per brand, sharing `direct_reading.py` (reading about once a second; a value older than 10 s counts as unknown):

| File | Meters | Status |
|---|---|---|
| `homewizard.py` | HomeWizard P1 meter and kWh meters (1/3 phase), local API v1 | verified |
| `sma.py` | SMA Sunny Home Manager 2.0 / Energy Meter, Speedwire (only received) | verified |
| `shelly.py` | Shelly Pro 3EM / 3EM / EM / Pro EM, local API | from the API documentation |
| `iammeter.py` | Iammeter WEM3080 / WEM3080T, local API | from the API documentation |

`discovery.py` finds these meters in Home Assistant and creates the right reader; `__init__.py` lists them (`DRIVERS`). Meters can also be read through the sensors of their own integration (`via_ha_integration.py`, HomeWizard P1 recognised). `template.py` is an example of a new meter. The same drivers serve every role: the grid connection, a PV source (a kWh meter on the inverter's line) and a battery (a kWh meter on the battery's line, see below). The role is a setting; the folder follows brand and type.

## Supported now

- **Batteries**: Marstek Venus E v3 (model); read through Omnibattery or Marstek Modbus (verified). Any other battery can be linked manually through its entities.
- **Meters**: see the table above.
