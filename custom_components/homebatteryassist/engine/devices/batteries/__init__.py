"""Battery drivers (see ``base.py``): models per brand → type range → type,
readers per HA integration (``integrations/``), and the virtual battery (simulation).

``template.py`` is an example only.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from ...measure.battery_monitor import BatteryConfig
from .anker.solarbank_direct_modbus import AnkerModbusDriver
from .anker.solarbank_e5000_pro import AnkerSolarbankE5000Pro
from .anker.solarbank_max import AnkerSolarbankMax
from .anker.solarbank_max_ac import AnkerSolarbankMaxAc
from .anker.solarbank_xe import AnkerSolarbankXe
from .anker.solarbank_xe_ac import AnkerSolarbankXeAc
from .base import BatteryModel, BatteryReader, BatteryTelemetry, platform_of
from .direct.base import DirectBatteryDriver
from .hoymiles.hibattery_1920_ac import HoymilesHiBattery1920Ac
from .hoymiles.hibattery_4020_ac import HoymilesHiBattery4020Ac
from .hoymiles.hibattery_4020_x import HoymilesHiBattery4020X
from .hoymiles.ms_a2 import HoymilesMsA2
from .hoymiles.smiles_direct_mqtt import HoymilesMqttDriver
from .huawei.luna2000_e1 import HuaweiLuna2000E1
from .huawei.sun2000_direct_modbus import HuaweiModbusDriver
from .indevolt.bk1600 import IndevoltBk1600
from .indevolt.flex_1200 import IndevoltFlex1200
from .indevolt.flex_2000 import IndevoltFlex2000
from .indevolt.flex_3000 import IndevoltFlex3000
from .indevolt.flex_direct_http import IndevoltHttpDriver
from .indevolt.solidflex_3600 import IndevoltSolidFlex3600
from .integrations import READERS
from .marstek.venus_a import MarstekVenusA
from .marstek.venus_d import MarstekVenusD
from .marstek.venus_direct_modbus import (
    MarstekVenusAModbus,
    MarstekVenusDModbus,
    MarstekVenusEV2Modbus,
    MarstekVenusEV3Modbus,
)
from .marstek.venus_e_v2 import MarstekVenusEV2
from .marstek.venus_e_v3 import MarstekVenusEV3
from .sessy.sessy import Sessy
from .sessy.sessy_direct_http import SessyHttpDriver
from .zendure.solarflow_800 import ZendureSolarFlow800
from .zendure.solarflow_800_plus import ZendureSolarFlow800Plus
from .zendure.solarflow_800_pro import ZendureSolarFlow800Pro
from .zendure.solarflow_1600_ac_plus import ZendureSolarFlow1600AcPlus
from .zendure.solarflow_2400_ac_plus import ZendureSolarFlow2400AcPlus
from .zendure.solarflow_2400_pro import ZendureSolarFlow2400Pro
from .zendure.solarflow_direct_http import ZendureHttpDriver

MODELS: tuple[BatteryModel, ...] = (
    MarstekVenusEV3(),
    MarstekVenusEV2(),
    MarstekVenusA(),
    MarstekVenusD(),
    AnkerSolarbankMaxAc(),
    AnkerSolarbankXeAc(),
    AnkerSolarbankE5000Pro(),
    AnkerSolarbankMax(),
    AnkerSolarbankXe(),
    HuaweiLuna2000E1(),
    ZendureSolarFlow800(),
    ZendureSolarFlow800Plus(),
    ZendureSolarFlow800Pro(),
    ZendureSolarFlow1600AcPlus(),
    ZendureSolarFlow2400AcPlus(),
    ZendureSolarFlow2400Pro(),
    Sessy(),
    IndevoltFlex1200(),
    IndevoltFlex2000(),
    IndevoltFlex3000(),
    IndevoltSolidFlex3600(),
    IndevoltBk1600(),
    HoymilesMsA2(),
    HoymilesHiBattery1920Ac(),
    HoymilesHiBattery4020X(),
    HoymilesHiBattery4020Ac(),
)

# Direct drivers (own connection to the battery): PREPARED, NOT USED. Listed
# for documentation and tests only; nothing offers or starts them.
DIRECT_DRIVERS: tuple[type[DirectBatteryDriver], ...] = (
    HoymilesMqttDriver,
    MarstekVenusEV2Modbus,
    MarstekVenusEV3Modbus,
    MarstekVenusAModbus,
    MarstekVenusDModbus,
    AnkerModbusDriver,
    HuaweiModbusDriver,
    ZendureHttpDriver,
    SessyHttpDriver,
    IndevoltHttpDriver,
)

__all__ = [
    "DIRECT_DRIVERS",
    "MODELS",
    "READERS",
    "BatteryModel",
    "BatteryReader",
    "BatteryTelemetry",
    "model_for",
    "reader_for",
    "telemetry",
]


def reader_for(hass: HomeAssistant, config: BatteryConfig) -> BatteryReader | None:
    """The reader of a (real) battery, by the integration of its sensors."""
    if config.virtual:
        return None
    platform = platform_of(hass, config)
    return next((r for r in READERS if r.key == platform), None)


def model_for(model: str | None) -> BatteryModel | None:
    """The battery type of a device model name, if known."""
    return next((m for m in MODELS if m.matches(model)), None)


def telemetry(hass: HomeAssistant, config: BatteryConfig) -> BatteryTelemetry:
    """Extra live details of a battery (empty without a reader)."""
    reader = reader_for(hass, config)
    return reader.telemetry(hass, config) if reader else BatteryTelemetry()
