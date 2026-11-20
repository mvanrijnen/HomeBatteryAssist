---
description: "Devices in HomeBatteryAssist: home batteries through their own integration (Marstek Venus, Victron) and grid meters read directly (HomeWizard P1, SMA, Shelly, IAMMETER)."
---

# Drivers: connecting a device

**Drivers** connect HomeBatteryAssist to physical *devices*: batteries and meters (layer 1, `engine/devices/`, see [Architecture](architecture.md)). Everything else that can be swapped — planners, consumption forecasters, price sources, tariffs, PV forecast sources — is a [module](modules.md).

Drivers are part of the integration: a new driver is added to the code and shared with everyone through a pull request.

## Rules

- For now a driver **only reads**: Home Assistant states and registries, a read-only local API, or data a device broadcasts anyway. It never changes a setting and never opens a connection that could compete with the device's own integration (e.g. a Marstek Venus allows only one Modbus TCP client).
- Battery drivers already *describe* how a battery is controlled (write methods); in this phase of development HomeBatteryAssist does not call them yet.
- Mark a driver **verified** only after testing it on a real installation. Until then every list where it can be chosen shows it as **(not tested)** — built-in modules, drivers, recognised devices and your own modules alike (a test checks the labels against the flags).

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

### Direct battery drivers — prepared, not used

Next to the readers (which go through another integration), every brand can have a **direct driver**: HomeBatteryAssist's own connection to the battery, for the day it controls batteries itself instead of e.g. Omnibattery. They are **disabled** (`enabled = False`): never offered, never connecting, and their write methods are never called. Many batteries allow only one connection, which today belongs to another integration.

Generic bases in `direct/` (a brand only adds its specifics): `modbus_driver.py` (a register map as data, read in blocks that never cross undefined registers; own small Modbus TCP client in `engine/devices/transports/modbus_tcp.py`), `http_driver.py` (local JSON API) and `mqtt_driver.py` (through Home Assistant's MQTT integration).

| Brand | Driver | Types (models) | Connection |
|---|---|---|---|
| Marstek | `marstek/venus_direct_modbus.py` | Venus E v2, Venus E v3, Venus A, Venus D | Modbus TCP |
| Anker | `anker/solarbank_direct_modbus.py` | SOLIX Solarbank Max AC, XE AC, E5000 Pro, Max, XE | Modbus TCP |
| Huawei | `huawei/sun2000_direct_modbus.py` | LUNA2000 (through the SUN2000 inverter) | Modbus TCP |
| Zendure | `zendure/solarflow_direct_http.py` | SolarFlow 800, 800 Plus, 800 Pro, 1600 AC+, 2400 AC+, 2400 Pro | local HTTP |
| Sessy | `sessy/sessy_direct_http.py` | Sessy home battery | local HTTP |
| Indevolt | `indevolt/flex_direct_http.py` | SolidFlex/PowerFlex 1200, 2000, 3000, SolidFlex 3600, BK1600 | local HTTP |
| Victron | `victron/gx_direct_modbus.py` | ESS (MultiPlus-II / Quattro) through the GX, unit 100 | Modbus TCP |
| Hoymiles | `hoymiles/smiles_direct_mqtt.py` | MS-A2, HiBattery 1920 AC, 4020 X, 4020 AC | MQTT |

None is verified on a device yet. The device facts (registers, endpoints, scales, signs, control sequences) were taken from Omnibattery's drivers (GPL-3.0) and, where available, the vendors' own documentation — facts only; the code is HomeBatteryAssist's own. Each driver also states how it must be controlled (`refresh_s`, `min_interval_s`, `deadband_w`, `idle_is_release`, limits), which the control layer enforces — see [Architecture](architecture.md#control-layer-built-not-active).

## Meters — `engine/devices/meters/`

One file per brand, sharing `direct_reading.py` (reading about once a second; a value older than 10 s counts as unknown; HomeWizard API v2, pushed per telegram: 25 s):

| File | Meters | Status |
|---|---|---|
| `homewizard.py` | HomeWizard P1 meter and kWh meters (1/3 phase), local API v1 | verified |
| `homewizard_v2.py` | The same through the local API v2: the meter pushes every reading (websocket). Uses the token of Home Assistant's HomeWizard integration (only offered when it talks API v2; HBA never creates a token) | not tested |
| `sma.py` | SMA Sunny Home Manager 2.0 / Energy Meter, Speedwire (only received; known by its serial number, so a new IP address does not matter) | verified |
| `shelly.py` | Shelly Pro 3EM / 3EM / EM / Pro EM, local API | from the API documentation |
| `iammeter.py` | Iammeter WEM3080 / WEM3080T, local API | from the API documentation |

Besides the power per phase every meter driver also reads the **current, voltage and power factor per phase** when the meter gives them (SMA Home Manager: current, voltage and power factor, verified; HomeWizard P1: current and voltage; Shelly 3EM: current, voltage and power factor; IAMMETER: current and voltage), for the phase protection: the main fuse sees current, not power. `discovery.py` finds these meters in Home Assistant and creates the right reader; `__init__.py` lists them (`DRIVERS`). Meters can also be read through the sensors of their own integration (`via_ha_integration.py`, HomeWizard P1 recognised; Victron GX recognised, not tested). `template.py` is an example of a new meter. The same drivers serve every role: the grid connection, a PV source (a kWh meter on the inverter's line) and a battery (a kWh meter on the battery's line, see below). The role is a setting; the folder follows brand and type.

## PV inverters — `engine/devices/inverters/`

How an inverter's power could be limited for the [export limit](planning.md#export-limit-pv-inverters). **Prepared, not used**: every driver has `enabled = False`, `async_set_limit` is never called, and HomeBatteryAssist opens no connection to an inverter in this phase; the sensor *Max export* only shows what a driver would send. `base.py` = `InverterDriver` (`points`: the settings it would write, `{limit_w}` = the limit in W; `limits`: the inverter's own output or the export), `template.py` = an example.

- `sma_home_manager.py` — SMA inverters with a **Sunny Home Manager 2.0** (together in ennexOS / Sunny Portal): the limit then belongs to the Home Manager, which limits all its SMA inverters; an inverter must not be written directly beside it. The Home Manager (software package ≥ 2.10) is a Modbus TCP server for grid management services: unit **2**, register **40016** = setpoint in % of the system's PMAX. It takes the house consumption into account, so it limits the **export**. Switch on in Sunny Portal / ennexOS: *Grid management services via Ethernet based communication* and *Limitation of active power feed-in* (*Implement external setpoints only*). A setpoint is valid 60 minutes, then it falls back to 100 %. The Home Manager is read as a [meter](#meters--enginedevicesmeters) already.
- `sma_modbus.py` — older SMA types (Sunny Boy TL-21, Sunny Tripower TL-10/-20/-30) **without** a Home Manager: register **40023** = limit in % × 100 of WMax (unit 3). The fallback is set in the inverter's web interface (*Use fallback setting*); otherwise it keeps the last limit.
- `sma_storage_x.py` — SMA Sunny Tripower Storage X / Sunny Island X without a Home Manager: 40210 = 1077 (manual in W), 40212 = limit in W, fallback 41193 = 2507 with timeout 41195 (unit 3).
- `sunspec_modbus.py` — **any inverter with SunSpec Modbus** (SMA, Fronius, SolarEdge, Kostal, Huawei, ABB / FIMER, ...): the vendor-neutral register map. It starts at 40000 (`SunS`), followed by a chain of models whose addresses differ per device, so the driver walks the chain. The limit goes through model **123** (*Immediate Controls*): `WMaxLimPct` (offset 3, % of `WMax` from model 121, scaled by `WMaxLimPct_SF`), `WMaxLimPct_RvrtTms` (offset 5: after 60 s without a new write the inverter returns to full power by itself) and `WMaxLim_Ena` (offset 7, 1 = on). Address `host[:port][/unit]`; the unit id differs per brand (SMA 126, Fronius and SolarEdge 1). Newer devices with model 704 (SunSpec 2018 / IEEE 1547) are not covered yet. From the SunSpec specification. With a Sunny Home Manager the SHM driver applies, not this one.
- `victron_gx_feed_in.py` — a **Victron ESS**: the GX limits the feed-in of the whole system itself (register 2706 on unit 100, in units of 100 W, -1 = no limit; in Home Assistant the number *max feed-in power* of the Victron GX integration), so this limits the **export**. Not tested.

All from the manufacturers' documentation and users' reports, *not verified on a device*.

### SMA per type {#sma-per-type}

| Type | Driver | Limit | Fallback when the setpoints stop | SunSpec |
|---|---|---|---|---|
| Any SMA inverter with a **Sunny Home Manager 2.0** | `sma_home_manager` | unit 2, 40016 = % of PMAX (export) | after 60 min back to 100 % | — |
| Sunny Boy 3.0–6.0-1AV-40/41 | `sunspec_modbus` | model 123 `WMaxLimPct` (unit 126) | `WMaxLimPct_RvrtTms` | 1AV-41 from firmware 4.00.23.R |
| Sunny Tripower 3.0–10.0-3AV-40 | `sunspec_modbus` | model 123 `WMaxLimPct` (unit 126) | `WMaxLimPct_RvrtTms` | from firmware 4.00.02.R |
| Sunny Tripower CORE1 | `sunspec_modbus` | model 123 `WMaxLimPct` (unit 126) | `WMaxLimPct_RvrtTms` | from firmware 3.14 |
| Sunny Boy TL-21, Sunny Tripower TL-10/-20/-30 | `sma_modbus` | 40023 = % × 100 (unit 3) | web interface: *Use fallback setting* | no |
| Sunny Tripower Storage X, Sunny Island X | `sma_storage_x` | 40210 = 1077, 40212 = W (unit 3) | 41193 = 2507, timeout 41195 | — |
| Sunny Tripower X (STP 12–25-50), Sunny Boy Smart Energy | — (registers not published yet; SunSpec on the STP X after a firmware update) | | | |

- **Modbus is off by default**: switch it on in the inverter (port 502). SMA's unit id is 3; SunSpec is SMA's unit + 123 (126).
- **Flash memory**: write only grid management values cyclically (SunSpec model 123, the % setpoints, the Home Manager's 40016). Normal settings such as `WMax` (40915) are stored in flash; SMA warns that changing them cyclically destroys the flash memory.
- **Possible power**: SMA publishes no register for the power the panels could give now; *Possible power* of a PV source needs a sensor of its own (e.g. from the DC power per string). An inverter that is limited only produces what is asked.
- Sources: SMA's Modbus documents (*SMA-Modbus-general-TI*, *SunSpecModbus-TI*, *SMAModbus-ennexOS-TI*, *SMAModbus-STPS-X-SI-X-TI*, *HM-20-Modbus-NSD-TI*, on files.sma.de) and users' reports for the TL types.

## Supported now

- **Batteries**: Marstek Venus E v3 (model); read through Omnibattery or Marstek Modbus (verified). A **Victron ESS** (MultiPlus-II / Quattro with a GX) is recognised through Home Assistant's *Victron GX* integration (`integrations/victron_gx_integration.py`: state of charge and battery power of the system, + charging, on the DC side; ESS limits and minimum SoC as starting values; enter the capacity yourself) — not tested. Any other battery can be linked manually through its entities.
- **Meters**: see the table above.
