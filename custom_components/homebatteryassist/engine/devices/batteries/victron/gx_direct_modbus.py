"""Direct driver: a Victron ESS through its GX device over Modbus TCP —
PREPARED, NOT USED, NOT TESTED.

Modbus TCP must be switched on in the GX (Settings → Services → Modbus
TCP); port 502. The system values are on unit 100 (``com.victronenergy.
system``); other devices (VE.Bus, battery) have unit ids that differ per GX
and port, listed by the GX under *Available services*. Function code 3 (or
4) reads; 6/16 write. Several clients can read at the same time (in practice
next to Node-RED or VRM; not documented by Victron).

Read on unit 100: battery SoC 843 (%), battery power 842 (s16 W, + charging,
DC side), grid L1-L3 820-822 (s16 W, + import), AC consumption 817-819, PV on
AC output 808-810 and on AC input 811-813, DC PV 850; ESS minimum SoC 2901
(x 0.1 %), ESS mode 2902 (1 = optimised with phase compensation, 2 = without,
3 = external control).

Control (never called while HomeBatteryAssist is read-only), two ways:

- ESS mode 2: the grid setpoint 2700 (s16 W, whole system; 2716-2717 s32 on
  Venus OS >= 3.50), with 2704 (max discharge, x 10 W, -1 = no limit) and
  2705 (max charge current A, -1 = no limit); the GX does the regulating.
- ESS mode 3 (external control, 2902 = 3; turns BatteryLife off): per phase
  setpoints on the VE.Bus unit, 37 / 40 / 41 (s16 W, + = take from the grid),
  38 disable charge, 39 disable feed-in; **rewritten at least every 60 s**,
  else the Multi goes to passthru.

Hazards: Dynamic ESS, scheduled charging and Node-RED flows control the same
system (they must be off before HomeBatteryAssist would control); DVCC and
the BMS limits always win.

Device facts: Victron's Modbus TCP register list and ESS mode 2/3 page,
the register table of ``sfstar/hass-victron`` (facts only).
"""

from __future__ import annotations

from ..direct.modbus_driver import ModbusBatteryDriver, Point
from .ess import VictronEss


class VictronGxModbusDriver(ModbusBatteryDriver):
    """A Victron ESS through the GX (address = IP / host; unit 100)."""

    key = "victron_gx_modbus"
    name = "Victron GX (Modbus TCP)"
    models = (VictronEss,)
    verified = False
    can_write = False  # control described above, not implemented
    # Control needs (engine/control): the GX regulates the setpoint itself;
    # mode 3 needs a refresh within 60 s.
    refresh_s = 30.0
    min_interval_s = 5.0
    deadband_w = 50.0
    idle_is_release = True  # back to ESS mode 1 / setpoint 0
    source = "Victron Modbus TCP register list, ESS mode 2/3; hass-victron (facts only)"
    port = 502
    unit = 100
    points = (
        Point("pv_ac_output_l1_w", 808),
        Point("pv_ac_output_l2_w", 809),
        Point("pv_ac_output_l3_w", 810),
        Point("pv_ac_input_l1_w", 811),
        Point("pv_ac_input_l2_w", 812),
        Point("pv_ac_input_l3_w", 813),
        Point("consumption_l1_w", 817),
        Point("consumption_l2_w", 818),
        Point("consumption_l3_w", 819),
        Point("grid_l1_w", 820, "s16"),
        Point("grid_l2_w", 821, "s16"),
        Point("grid_l3_w", 822, "s16"),
        Point("power_w", 842, "s16"),  # + charging (DC side)
        Point("soc", 843),
        Point("dc_pv_w", 850),
        Point("min_soc", 2901, scale=0.1),
        Point("ess_mode", 2902),
    )
