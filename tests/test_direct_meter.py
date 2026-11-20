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
from custom_components.homebatteryassist.engine.devices.meters.homewizard import (
    homewizard_phases,
)
from custom_components.homebatteryassist.engine.devices.meters.sma import decode


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
        "custom_components.homebatteryassist.engine.devices.meters.homewizard.read_homewizard",
        fake_read,
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
            "custom_components.homebatteryassist.engine.devices.meters.homewizard.read_homewizard",
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


def test_shelly_phases() -> None:
    """Shelly 3EM: Gen2+ EM.GetStatus and Gen1 /status (as documented)."""
    from custom_components.homebatteryassist.engine.devices.meters.shelly import (
        shelly_gen1_phases,
        shelly_gen2_phases,
    )

    assert shelly_gen2_phases(
        {"id": 0, "a_act_power": 120.5, "b_act_power": -800.0, "c_act_power": 0.0}
    ) == (120.5, -800.0, 0.0)
    assert shelly_gen2_phases({"a_act_power": 1.0}) is None
    meters = [{"power": 10.0, "is_valid": True}, {"power": -5.0}, {"power": 0.0}]
    assert shelly_gen1_phases({"emeters": meters}) == (10.0, -5.0, 0.0)
    assert shelly_gen1_phases({"emeters": meters[:1]}) is None


async def test_shelly_3em_found_in_config_entries(hass: HomeAssistant) -> None:
    from custom_components.homebatteryassist.engine.devices.meters.shelly import (
        shelly_3em_hosts,
    )

    for host, model in (
        ("192.0.2.10", "SPEM-003CEBEU"),
        ("192.0.2.11", "SHEM-3"),
        ("192.0.2.79", "SHPLG-S"),  # a plug: not a grid meter
    ):
        MockConfigEntry(
            domain="shelly", data={"host": host, "model": model}
        ).add_to_hass(hass)
    assert shelly_3em_hosts(hass) == {
        "192.0.2.10": "SPEM-003CEBEU",
        "192.0.2.11": "SHEM-3",
    }


def test_iammeter_phases() -> None:
    """Iammeter local API (as documented): Data (1 phase) or Datas (3 phases)."""
    from custom_components.homebatteryassist.engine.devices.meters.iammeter import (
        iammeter_phases,
    )

    assert iammeter_phases({"Data": [230.1, 1.2, 250.0, 1000.0, 20.0]}) == (250.0,)
    assert iammeter_phases(
        {"Datas": [[230, 1, 100, 1, 1], [231, 2, -400, 1, 1], [229, 0, 0, 1, 1]]}
    ) == (100.0, -400.0, 0.0)
    assert iammeter_phases({}) is None


async def test_homewizard_kwh_meters_found(hass: HomeAssistant) -> None:
    """HomeWizard kWh meters (1/3 phase) can be read directly; sockets cannot."""
    from homeassistant.helpers import device_registry as dr

    from custom_components.homebatteryassist.engine.devices.meters.discovery import (
        find_direct_meters,
    )

    for address, model in (
        ("192.0.2.21", "SDM230-wifi"),
        ("192.0.2.30", "HWE-KWH3"),
        ("192.0.2.112", "HWE-SKT"),
    ):
        entry = MockConfigEntry(domain="homewizard", data={"ip_address": address})
        entry.add_to_hass(hass)
        dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={("homewizard", address)},
            name="kWh Meter",
            model_id=model,
        )
    found = {(c.address, c.phases) for c in find_direct_meters(hass)}
    assert found == {("192.0.2.21", 1), ("192.0.2.30", 3)}


def test_decode_current_voltage_power_factor() -> None:
    """Per phase also current (mA), voltage (mV) and power factor (0.001)."""
    data = _telegram(
        1900000001,
        {
            1: 23000,
            2: 0,
            21: 23000,
            22: 0,
            41: 0,
            42: 0,
            61: 0,
            62: 0,
            31: 11500,
            51: 200,
            71: 300,
            32: 228000,
            52: 231000,
            72: 232000,
            33: 870,
            53: 1000,
            73: 1000,
        },
    )
    telegram = decode(data)
    assert telegram.phase_a == (11.5, 0.2, 0.3)
    assert telegram.phase_v == (228.0, 231.0, 232.0)
    assert telegram.phase_pf == (0.87, 1.0, 1.0)
    # Without them (older meters): only power.
    plain = decode(_telegram(1, {1: 0, 2: 0, 21: 0, 22: 0, 41: 0, 42: 0, 61: 0, 62: 0}))
    assert plain.phase_a is None and plain.phase_v is None


def test_phase_load_is_about_current() -> None:
    """The fuse sees current: measured; else power / (voltage x power
    factor); else power / 230 V."""
    from custom_components.homebatteryassist.engine.measure.house_measurement import (
        PowerFlow,
    )

    base = PowerFlow(2300.0, 0.0, 0.0, 0.0, 2300.0, (2300.0, -1150.0))
    assert base.phase_current(0) == 10.0 and base.phase_load_w == (2300.0, -1150.0)
    measured = PowerFlow(
        2300.0, 0.0, 0.0, 0.0, 2300.0, (2300.0, -1150.0), phase_a=(12.0, 5.0)
    )
    assert measured.phase_current(0) == 12.0  # low power factor: more current
    assert measured.phase_load_w == (2760.0, -1150.0)
    voltage = PowerFlow(
        2000.0, 0.0, 0.0, 0.0, 2000.0, (2000.0,), phase_v=(200.0,), phase_pf=(0.8,)
    )
    assert voltage.phase_current(0) == 12.5  # 2000 / (200 x 0.8)


def test_readings_with_current_and_voltage() -> None:
    """HomeWizard P1, Shelly 3EM (Gen1 and Gen2) and IAMMETER: current and
    voltage per phase too, when the meter gives them."""
    from custom_components.homebatteryassist.engine.devices.meters.homewizard import (
        homewizard_reading,
    )
    from custom_components.homebatteryassist.engine.devices.meters.iammeter import (
        iammeter_reading,
    )
    from custom_components.homebatteryassist.engine.devices.meters.shelly import (
        shelly_gen1_reading,
        shelly_gen2_reading,
    )

    hw = homewizard_reading(
        {
            **{f"active_power_l{n}_w": 100.0 * n for n in (1, 2, 3)},
            **{f"active_current_l{n}_a": 1.5 * n for n in (1, 2, 3)},
            **{f"active_voltage_l{n}_v": 230.0 + n for n in (1, 2, 3)},
        }
    )
    assert hw.phase_w == (100.0, 200.0, 300.0) and hw.phase_a == (1.5, 3.0, 4.5)
    assert hw.phase_v == (231.0, 232.0, 233.0)
    assert homewizard_reading({"active_power_l1_w": 5.0}).phase_a is None
    gen2 = shelly_gen2_reading(
        {
            **{f"{p}_act_power": 10.0 for p in "abc"},
            **{f"{p}_current": 0.5 for p in "abc"},
            **{f"{p}_voltage": 229.0 for p in "abc"},
            **{f"{p}_pf": -0.9 for p in "abc"},
        }
    )
    assert gen2.phase_a == (0.5, 0.5, 0.5) and gen2.phase_pf == (0.9, 0.9, 0.9)
    gen1 = shelly_gen1_reading(
        {"emeters": [{"power": 50.0, "current": 0.3, "voltage": 231.0, "pf": 0.7}] * 3}
    )
    assert gen1.phase_w == (50.0, 50.0, 50.0) and gen1.phase_v == (231.0,) * 3
    iam = iammeter_reading(
        {"Datas": [[230.1, 2.5, 500.0], [231.0, 0.1, -20.0], [229.0, 1.0, 200.0]]}
    )
    assert iam.phase_a == (2.5, 0.1, 1.0) and iam.phase_v == (230.1, 231.0, 229.0)


def test_reactive_current_learned_per_phase(hass: HomeAssistant) -> None:
    """From measured power and current per phase: the current besides the
    power (as W at 230 V); the plan's load counts with it."""
    from datetime import datetime

    from homeassistant.util import dt as dt_util

    from custom_components.homebatteryassist.engine.forecast.phase_shares import (
        PhaseProfile,
    )

    start = datetime(2026, 11, 20, tzinfo=dt_util.UTC).isoformat()
    records = [
        {
            "start": start,
            "minutes": 15,
            "avg_w": 300.0,
            "coverage": 1.0,
            "phase_grid_w": [300.0, 30.0],
            "phase_a": [300.0 / 230, 1.3],
            # Worked out per reading: L1 none, L2 228 W at 230 V
            "phase_q": [0.0, 228.0],
        }
    ] * 4
    profile = PhaseProfile(records, 2)
    assert profile.reactive[0] == 0.0
    assert profile.reactive[1] == 228.0
    assert profile._with_reactive(0.0, 228.0) == 228.0  # nothing on, still current
    assert profile._with_reactive(-500.0, 0.0) == -500.0
    assert PhaseProfile(records[:3], 2).reactive == [0.0, 0.0]  # too little yet


def test_homewizard_v2_reading() -> None:
    """API v2 measurement: power, current (as size) and voltage per phase."""
    from custom_components.homebatteryassist.engine.devices.meters.homewizard_v2 import (
        homewizard_v2_reading,
    )

    reading = homewizard_v2_reading(
        {
            "power_w": -543,
            "power_l1_w": -676,
            "power_l2_w": 133,
            "power_l3_w": 0,
            "current_l1_a": -4,
            "current_l2_a": 2,
            "current_l3_a": 0,
            "voltage_l1_v": 228,
            "voltage_l2_v": 229,
            "voltage_l3_v": 230,
        }
    )
    assert reading is not None
    assert reading.phase_w == (-676.0, 133.0, 0.0)
    assert reading.phase_a == (4.0, 2.0, 0.0)
    assert reading.phase_v == (228.0, 229.0, 230.0)
    one = homewizard_v2_reading({"power_w": 300})
    assert one is not None and one.phase_w == (300.0,)
    assert homewizard_v2_reading({}) is None


async def test_homewizard_v2_token_and_candidate(hass) -> None:
    """The v2 driver is offered only when the HomeWizard integration has a
    token; the token is taken from it, never created."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.homebatteryassist.engine.devices.meters.homewizard_v2 import (
        HomeWizardPush,
        homewizard_token,
    )

    entry = MockConfigEntry(
        domain="homewizard", data={"ip_address": "10.0.0.5", "token": "abc"}
    )
    entry.add_to_hass(hass)
    assert homewizard_token(hass, "10.0.0.5") == "abc"
    assert homewizard_token(hass, "10.0.0.6") is None
    meter = HomeWizardPush(hass, "10.0.0.5")
    meter.handle({"power_l1_w": 100, "power_l2_w": 200, "power_l3_w": -50})
    assert meter.available and meter.phase_w == (100.0, 200.0, -50.0)
    meter.cancel_stale()


def test_pv_share_per_hour() -> None:
    """East roof on L1 in the morning, west roof on L2 in the afternoon."""
    from datetime import datetime, timedelta

    from homeassistant.util import dt as dt_util

    from custom_components.homebatteryassist.engine.forecast.phase_shares import (
        PhaseProfile,
    )

    day = dt_util.as_local(datetime(2026, 6, 20, tzinfo=dt_util.UTC)).replace(
        hour=0, minute=0
    )
    morning, afternoon = day + timedelta(hours=9), day + timedelta(hours=16)
    records = [
        {
            "start": dt_util.as_utc(morning).isoformat(),
            "minutes": 60,
            "avg_w": 0.0,
            "coverage": 1.0,
            "phase_pv_w": [1000.0, 0.0],
        },
        {
            "start": dt_util.as_utc(afternoon).isoformat(),
            "minutes": 60,
            "avg_w": 0.0,
            "coverage": 1.0,
            "phase_pv_w": [0.0, 1000.0],
        },
    ]
    profile = PhaseProfile(records, 2)
    assert profile.pv_share(morning) == [1.0, 0.0]
    assert profile.pv_share(afternoon) == [0.0, 1.0]
    assert profile.pv_share(day + timedelta(hours=12)) == [0.5, 0.5]


def test_reactive_per_reading() -> None:
    """Reactive power per reading: measured voltage, whole-amp rounding of a
    smart meter is not reactive power, a pure load has none."""
    from custom_components.homebatteryassist.engine.history.consumption_history import (
        reactive_w,
    )

    assert reactive_w(2300.0, 10.0, 230.0) == 0.0  # 10 A rounded: 9.5 A
    assert reactive_w(138.0, 1.0) == 0.0  # 0.6 A shown as 1 A: no reactive
    assert abs(reactive_w(30.0, 1.3) - (299.0**2 - 30.0**2) ** 0.5) < 0.1
    # 240 V measured: 2 A x 240 = 480 VA, 0 W -> 2 A, as 460 W at 230 V
    assert abs(reactive_w(0.0, 2.05, 240.0) - 2.05 * 230) < 0.1


async def test_history_reactive_not_from_averages(hass) -> None:
    """A load switching on and off within an interval (import half the time,
    export the other half) has no reactive power."""
    from datetime import datetime, timedelta

    from homeassistant.util import dt as dt_util

    from custom_components.homebatteryassist.engine.history.consumption_history import (
        ConsumptionHistory,
    )

    history = ConsumptionHistory(hass, "test", 15)
    t0 = datetime(2026, 11, 20, 12, 0, tzinfo=dt_util.UTC)
    for k in range(15):
        watts = 2300.0 if k % 2 == 0 else -2300.0
        history.add_sample(
            t0 + timedelta(minutes=k),
            500.0,
            grid_phases=((watts,), (10.0,), (230.0,)),
        )
    history.add_sample(t0 + timedelta(minutes=15), 500.0)
    record = history.records[-1]
    assert abs(record["phase_grid_w"][0]) < 200  # the averages differ a lot
    assert record["phase_q"] == [0.0]  # but per reading there is none


def test_plan_room_with_reactive_part() -> None:
    """A learned reactive part: the room is sqrt(limit^2 - Q^2) - P, not
    limit + hypot(P, Q) (which would let the plan overload the phase)."""
    from custom_components.homebatteryassist.engine.planning.phase_limit import (
        PhaseDevice,
        max_power,
    )

    load = (50.0**2 + 2500.0**2) ** 0.5  # hypot(P, Q), signed as P (+)
    device = PhaseDevice("b", 0, 5000.0, 5000.0)
    room = max_power([device], [load], 5175.0, charging=False, active_w=[50.0])
    expected = (5175.0**2 - 2500.0**2) ** 0.5 + 50.0
    assert abs(room - expected) < 1.0
    assert room < 5000.0


async def test_speedwire_meter_known_by_serial(hass: HomeAssistant) -> None:
    """An SMA meter set up by serial follows it to any IP address (DHCP);
    one set up by IP address learns its serial and hands it on."""
    from custom_components.homebatteryassist.engine.devices.meters.sma import (
        SpeedwireMeter,
    )

    values = {1: 12000, 2: 0, 21: 12000, 22: 0, 41: 0, 42: 0, 61: 0, 62: 0}
    telegram = _telegram(1900000001, values)
    other = _telegram(1900000002, values)
    meter = SpeedwireMeter(hass, "1900000001")
    meter._received(other, "192.0.2.5")
    assert meter.count == 0  # another meter
    meter._received(telegram, "192.0.2.10")
    meter._received(telegram, "192.0.2.77")  # a new address
    assert meter.count == 2
    assert meter.host == "192.0.2.77"
    assert meter.phase_w[0] == 1200.0

    learned: list[int] = []
    old = SpeedwireMeter(hass, "192.0.2.10")
    old.on_serial = learned.append
    old._received(telegram, "192.0.2.99")
    assert old.count == 0  # not its address, serial unknown yet
    old._received(telegram, "192.0.2.10")
    assert learned == [1900000001]
    old._received(telegram, "192.0.2.99")
    assert old.count == 2  # known by its serial from now on
    meter.cancel_stale()
    old.cancel_stale()
