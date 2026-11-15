"""Tests for grid meters read directly (HomeWizard P1 API, SMA Speedwire)."""

import struct
from datetime import timedelta
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.homebatteryassist.const import (
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_METER_ADDRESS,
    CONF_METER_SOURCE,
    CONF_PHASES,
    DOMAIN,
)
from custom_components.homebatteryassist.inputs.direct import homewizard_phases
from custom_components.homebatteryassist.inputs.speedwire import decode


def _telegram(serial: int, values: dict[int, int]) -> bytes:
    """An energy meter telegram like an SMA Home Manager sends (0.1 W units)."""
    body = b"".join(
        struct.pack(">BBBBI", 0, index, 4, 0, value) for index, value in values.items()
    )
    body += struct.pack(">BBBBQ", 0, 1, 8, 0, 123456789)  # a counter
    body += struct.pack(">BBBBI", 0x90, 0, 0, 0, 0x02001252)  # software version
    payload = struct.pack(">HHII", 0x6069, 501, serial, 1000) + body
    return (
        b"SMA\x00"
        + struct.pack(">HHI", 4, 0x02A0, 1)
        + struct.pack(">HH", len(payload) + 2, 0x0010)
        + payload
        + b"\x00\x00\x00\x00"
    )


def test_decode_speedwire() -> None:
    """Import minus export, per phase (verified against a real Home Manager)."""
    data = _telegram(
        1900000001,
        {1: 5899, 2: 0, 21: 384, 22: 0, 41: 0, 42: 1205, 61: 2010, 62: 0},
    )
    telegram = decode(data)
    assert telegram.serial == 1900000001
    assert telegram.power_w == 589.9
    assert telegram.phase_w == (38.4, -120.5, 201.0)
    assert decode(b"SMA\x00" + bytes(40)) is None
    assert decode(b"garbage") is None


def test_homewizard_phases() -> None:
    assert homewizard_phases(
        {"active_power_l1_w": 41, "active_power_l2_w": -355, "active_power_l3_w": 201}
    ) == (41.0, -355.0, 201.0)
    assert homewizard_phases(
        {"active_power_l1_w": 41, "active_power_l2_w": None, "active_power_l3_w": None}
    ) == (41.0,)
    assert homewizard_phases({}) is None


async def test_measurements_from_homewizard_api(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The P1 API is polled every second; entities update at most every 10 s."""
    readings = [
        {"active_power_l1_w": 100, "active_power_l2_w": 200, "active_power_l3_w": 300}
    ]

    async def fake_read(hass, address):
        assert address == "192.0.2.229"
        return readings[-1]

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_PHASES: 3,
            CONF_MAX_CURRENT: 25,
            CONF_METER_SOURCE: "homewizard",
            CONF_METER_ADDRESS: "192.0.2.229",
        },
        options={CONF_HISTORY_INTERVAL: 15},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.homebatteryassist.inputs.direct.read_homewizard", fake_read
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        measurements = entry.runtime_data.measurements
        assert measurements.flow.phase_w == (100.0, 200.0, 300.0)
        house = er.async_get(hass).async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_house_consumption"
        )
        assert float(hass.states.get(house).state) == 600.0

        readings.append(
            {"active_power_l1_w": 100, "active_power_l2_w": 200, "active_power_l3_w": 0}
        )
        freezer.tick(timedelta(seconds=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert float(hass.states.get(house).state) == 300.0  # first change: at once
        readings.append(
            {"active_power_l1_w": 100, "active_power_l2_w": 0, "active_power_l3_w": 0}
        )
        freezer.tick(timedelta(seconds=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert measurements.power == 100.0  # internal: at once
        assert float(hass.states.get(house).state) == 300.0  # entity: throttled
        freezer.tick(timedelta(seconds=10))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert float(hass.states.get(house).state) == 100.0

        # No answer for a while: unknown.
        async def failing(hass, address):
            raise TimeoutError

        with patch(
            "custom_components.homebatteryassist.inputs.direct.read_homewizard",
            failing,
        ):
            for _ in range(12):
                freezer.tick(timedelta(seconds=1))
                async_fire_time_changed(hass)
                await hass.async_block_till_done()
            # a state change of anything recalculates; the meter is stale now
            measurements._update(measurements.direct.updated + timedelta(seconds=12))
            assert measurements.power is None
            assert measurements.missing == ["homewizard 192.0.2.229"]
        assert await hass.config_entries.async_unload(entry.entry_id)
