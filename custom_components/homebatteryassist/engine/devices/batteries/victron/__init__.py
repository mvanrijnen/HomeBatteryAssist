"""Brand: Victron Energy. An ESS: a MultiPlus-II / Quattro with a GX device
(Cerbo GX, Venus OS) and batteries behind it (Victron or another brand
through the BMS). The capacity depends on the batteries installed, so there
is one generic type (``ess.py``). Read through Home Assistant's Victron GX
integration (``integrations/victron_gx_integration.py``) or directly over
Modbus TCP (``gx_direct_modbus.py``, prepared, not used). Not tested on a
real installation."""

from __future__ import annotations

from ..base import BatteryModel


class Victron(BatteryModel):
    """Victron Energy systems."""

    brand = "Victron Energy"
