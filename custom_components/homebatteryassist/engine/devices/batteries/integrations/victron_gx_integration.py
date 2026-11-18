"""Reader: Victron ESS through Home Assistant's Victron GX integration
(``victron_gx``, core since HA 2026.5, local MQTT to the GX).

NOT TESTED on a real installation: the translation keys come from the
integration's library (``victron_mqtt``), not from a live system. The system
device carries the battery state of charge and power and the ESS settings
(the integration places the ESS settings on it), so they are read together.

Notes:

- ``system_dc_battery_power`` is the battery's **DC** power, + charging. The
  AC side (what the house sees) is lower when discharging and higher when
  charging by the inverter's losses; HomeBatteryAssist uses it as the
  battery's power (not as an AC meter).
- The installed capacity is reported per battery in Ah, not kWh: enter the
  capacity yourself.
- Dynamic ESS, scheduled charging and Node-RED flows steer the battery too;
  HomeBatteryAssist only reads (for now).
"""

from __future__ import annotations

from .....const import SIGN_CHARGING_POSITIVE
from ..base import BatteryProfile
from .entity_reader import EntityReader


class VictronGxReader(EntityReader):
    """A Victron ESS through the Victron GX integration."""

    key = "victron_gx"
    name = "Victron GX"
    verified = False
    is_meter = True  # the battery's own power (DC side, see above)
    profile = BatteryProfile(
        platform="victron_gx",
        label="Victron GX",
        soc="system_dc_battery_soc",
        power="system_dc_battery_power",
        power_sign=SIGN_CHARGING_POSITIVE,
        max_charge=("number", "system_ess_max_charge_power"),
        max_discharge=("number", "system_ess_max_inverter_power_limit"),
        min_soc=("number", "system_ess_min_soc_limit"),
        verified=False,
    )
