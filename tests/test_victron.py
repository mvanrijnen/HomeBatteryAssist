"""Victron: recognised through the Victron GX integration, as a battery and
as a grid meter; prepared direct and export-limit drivers. Not tested on a
real installation, so marked as such everywhere."""

from __future__ import annotations

import re

from custom_components.homebatteryassist.engine.devices.batteries import (
    DIRECT_DRIVERS,
    MODELS,
    READERS,
)
from custom_components.homebatteryassist.engine.devices.inverters import get_driver
from custom_components.homebatteryassist.engine.devices.meters.via_ha_integration import (
    PROFILES,
)


def test_victron_reader_and_model_are_not_tested() -> None:
    reader = next(r for r in READERS if r.key == "victron_gx")
    assert not reader.verified and reader.profile is not None
    assert not reader.profile.verified
    assert reader.profile.soc == "system_dc_battery_soc"
    assert reader.profile.power_sign == "charging_positive"
    assert any(m.brand == "Victron Energy" for m in MODELS)
    driver = next(d for d in DIRECT_DRIVERS if d.key == "victron_gx_modbus")
    assert not driver.enabled and not driver.verified and not driver.can_write
    assert driver.unit == 100


def test_victron_grid_meter_profile() -> None:
    profile = next(p for p in PROFILES if p.platform == "victron_gx")
    assert not profile.verified
    match = re.search(profile.phase_pattern, "c0619ab_system_0_system_grid_power_l2")
    assert match is not None and match.group(1) == "2"


def test_victron_feed_in_limit_describes_the_register() -> None:
    driver = get_driver("victron_gx_feed_in")
    assert driver is not None and driver.limits == "export"
    assert driver.describe("192.168.1.30", 0) == (
        "Victron GX 192.168.1.30: unit 100 2706=0 W / 100"
    )
