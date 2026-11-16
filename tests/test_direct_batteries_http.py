"""Tests for the direct HTTP battery drivers (Zendure, Sessy, Indevolt):
prepared, not used. No sockets: the session is a fake."""

from __future__ import annotations

import base64
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.homebatteryassist.engine.devices.batteries.indevolt import (
    flex_direct_http as indevolt,
)
from custom_components.homebatteryassist.engine.devices.batteries.sessy import (
    sessy_direct_http as sessy,
)
from custom_components.homebatteryassist.engine.devices.batteries.zendure import (
    solarflow_direct_http as zendure,
)

DRIVERS = (
    zendure.ZendureHttpDriver,
    sessy.SessyHttpDriver,
    indevolt.IndevoltHttpDriver,
)


class FakeResponse:
    """An aiohttp-like response: awaitable and an async context manager."""

    def __init__(self, body: Any, status: int = 200) -> None:
        self.status = status
        self._raw = body if isinstance(body, bytes) else json.dumps(body).encode()

    def __await__(self):
        async def itself() -> FakeResponse:
            return self

        return itself().__await__()

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def read(self) -> bytes:
        return self._raw

    async def json(self, content_type: str | None = None) -> Any:
        return json.loads(self._raw)


class FakeSession:
    """Records requests and answers them from a queue."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        reply = self.replies.pop(0)
        return reply if isinstance(reply, FakeResponse) else FakeResponse(reply)


def session_for(module: Any, fake: FakeSession) -> Any:
    """Patch the module's session getter with ``fake``."""
    return patch.object(module, "async_get_clientsession", return_value=fake)


@pytest.mark.parametrize("driver", DRIVERS)
async def test_disabled_http_drivers_do_not_connect(
    hass: HomeAssistant, driver: type
) -> None:
    """Prepared drivers are disabled, unverified and refuse to open."""
    assert not driver.enabled
    assert not driver.verified
    assert driver.source
    with pytest.raises(RuntimeError, match="not enabled"):
        await driver(hass, "192.0.2.1").async_open()


# --- Zendure -----------------------------------------------------------------

ZENDURE_REPORT = {
    "sn": "HOA1NAH4N123456",
    "product": "SolarFlow 800 Pro",
    "properties": {
        "electricLevel": 64,
        "outputPackPower": 0,
        "packInputPower": 420,
        "gridInputPower": 0,
        "outputHomePower": 600,
        "solarInputPower": 180,
        "BatVolt": 4810,
        "hyperTmp": 3031,
        "remainOutTime": 59940,
        "packNum": 2,
        "packState": 2,
        "socStatus": 0,
        "chargeMaxLimit": 800,
        "inverseMaxPower": 800,
        "socSet": 1000,
        "minSoc": 100,
        "acMode": 2,
        "outputLimit": 600,
    },
    "packData": [
        {"sn": "CO4H123", "maxTemp": 2981, "minVol": 331, "maxVol": 334},
        {"sn": "CO4H456", "maxTemp": 3001, "minVol": 330, "maxVol": 335},
    ],
}


def test_zendure_reading(hass: HomeAssistant) -> None:
    """Pack in - out = + charging; 0.1 K, 0.01 V, 0.1 %; 59940 dropped."""
    driver = zendure.ZendureHttpDriver(hass, "192.0.2.10")
    reading = driver.reading(ZENDURE_REPORT)
    assert reading.soc == 64
    assert reading.power_w == -420  # discharging
    assert reading.telemetry.voltage_v == 48.1
    assert zendure.int16(65036) == -500  # BatVolt is signed 16-bit
    assert reading.telemetry.temperature_c == 27.0  # hottest pack
    assert reading.telemetry.extra["enclosure_temperature_c"] == 30.0
    assert reading.telemetry.cell_min_v == 3.30
    assert reading.telemetry.cell_max_v == 3.35
    assert reading.extra["ac_power_w"] == -600  # delivering to the home
    assert reading.extra["pv_power_w"] == 180
    assert reading.extra["remaining_discharge_min"] is None
    assert reading.extra["status"] == "discharging"
    assert reading.extra["max_soc"] == 100
    assert reading.extra["min_soc"] == 10
    assert reading.extra["capacity_kwh"] == 3.84  # 2 x C pack (1.92)
    assert reading.extra["model"] == "SolarFlow 800 Pro"
    assert driver.serial == "HOA1NAH4N123456"


def test_zendure_ac_power_unknown_when_negative(hass: HomeAssistant) -> None:
    driver = zendure.ZendureHttpDriver(hass, "192.0.2.10")
    report = {"properties": {"gridInputPower": -1, "outputHomePower": 0}}
    assert driver.reading(report).extra["ac_power_w"] is None


@pytest.mark.parametrize(
    ("product", "expected"),
    [
        ("SolarFlow 800 Pro", "SolarFlow 800 Pro"),
        ("SolarFlow 800 Plus", "SolarFlow 800 Plus"),
        ("zdsf800-x", "SolarFlow 800"),
        ("SolarFlow 1600 AC+", "SolarFlow 1600 AC+"),
        ("SolarFlow 2400 Pro", "SolarFlow 2400 Pro"),
        ("SolarFlow 2400 AC+", "SolarFlow 2400 AC+"),
        ("4000 Mix Pro", None),
        ("", "SolarFlow 2400 Pro"),
    ],
)
def test_zendure_product_type(product: str, expected: str | None) -> None:
    model = zendure.product_type(product)
    assert (model.type if model else None) == expected


async def test_zendure_writes(hass: HomeAssistant) -> None:
    """One write per setpoint, with the serial and always smartMode 1; the
    serial is read first when unknown."""
    driver = zendure.ZendureHttpDriver(hass, "192.0.2.10")
    fake = FakeSession(ZENDURE_REPORT, {}, {}, {})
    with session_for(zendure, fake):
        await driver.async_set_power(500)
        await driver.async_set_power(-300.4)
        await driver.async_release()
    assert fake.calls[0]["method"] == "GET"
    assert fake.calls[0]["url"] == "http://192.0.2.10/properties/report"
    writes = [(c["method"], c["url"], c["json"]) for c in fake.calls[1:]]
    url = "http://192.0.2.10/properties/write"
    sn = "HOA1NAH4N123456"
    assert writes == [
        (
            "POST",
            url,
            {"sn": sn, "properties": {"acMode": 1, "inputLimit": 500, "smartMode": 1}},
        ),
        (
            "POST",
            url,
            {"sn": sn, "properties": {"acMode": 2, "outputLimit": 300, "smartMode": 1}},
        ),
        (
            "POST",
            url,
            {"sn": sn, "properties": {"acMode": 2, "outputLimit": 0, "smartMode": 1}},
        ),
    ]


async def test_zendure_refuses_flash_write(hass: HomeAssistant) -> None:
    driver = zendure.ZendureHttpDriver(hass, "192.0.2.10")
    with pytest.raises(ValueError, match="smartMode"):
        await driver.async_write({"acMode": 1, "inputLimit": 100})


async def test_zendure_retries_431(hass: HomeAssistant) -> None:
    driver = zendure.ZendureHttpDriver(hass, "192.0.2.10")
    fake = FakeSession(FakeResponse({}, 431), ZENDURE_REPORT)
    with session_for(zendure, fake), patch.object(zendure, "RETRY_DELAY", 0):
        reading = await driver.async_read()
    assert reading.soc == 64
    assert len(fake.calls) == 2


# --- Sessy -------------------------------------------------------------------

SESSY_STATUS = {
    "status": "ok",
    "sessy": {
        "state_of_charge": 0.537,
        "power": -1200,  # charging
        "power_setpoint": -1250,
        "pack_voltage": 52450,
    },
    "renewable_energy_phase1": {"power": 300},
    "renewable_energy_phase2": {"power": 0},
    "renewable_energy_phase3": {"power": None},
}
SESSY_ENERGY = {"sessy_energy": {"import_wh": 123456, "export_wh": 100000}}


def test_sessy_reading(hass: HomeAssistant) -> None:
    """Fraction → %, + discharging → + charging, mV → V, Wh → kWh."""
    driver = sessy.SessyHttpDriver(hass, "192.0.2.20")
    reading = driver.reading(SESSY_STATUS, SESSY_ENERGY)
    assert reading.soc == 53.7
    assert reading.power_w == 1200
    assert reading.telemetry.voltage_v == 52.45
    assert reading.telemetry.extra == {
        "charged_total_kwh": 123.456,
        "discharged_total_kwh": 100.0,
    }
    assert reading.extra["setpoint_w"] == 1250
    assert reading.extra["pv_power_w"] == 300


async def test_sessy_read_uses_auth_and_fresh_connections(
    hass: HomeAssistant,
) -> None:
    driver = sessy.SessyHttpDriver(
        hass, "192.0.2.20", username="ABCD1234", password="secret"
    )
    fake = FakeSession(SESSY_STATUS, SESSY_ENERGY)
    with session_for(sessy, fake):
        reading = await driver.async_read()
    assert reading.power_w == 1200
    assert [c["url"] for c in fake.calls] == [
        "http://192.0.2.20/api/v1/power/status",
        "http://192.0.2.20/api/v1/energy/status",
    ]
    token = base64.b64encode(b"ABCD1234:secret").decode()
    for call in fake.calls:
        assert call["headers"] == {
            "Connection": "close",
            "Authorization": f"Basic {token}",
        }


async def test_sessy_writes(hass: HomeAssistant) -> None:
    """Original strategy read once; API strategy then setpoint (+ discharge
    on the wire, clamped); release sets 0 and restores the strategy."""
    driver = sessy.SessyHttpDriver(hass, "192.0.2.20", username="u", password="p")
    fake = FakeSession({"strategy": "POWER_STRATEGY_NOM"}, b"", {}, {}, b"ok", {}, {})
    with session_for(sessy, fake):
        await driver.async_set_power(3000)  # charge, clamped to 2200
        await driver.async_set_power(-800)
        await driver.async_release()
    base = "http://192.0.2.20/api/v1/power/"
    assert [(c["method"], c["url"], c["json"]) for c in fake.calls] == [
        ("GET", base + "active_strategy", None),
        ("POST", base + "active_strategy", {"strategy": "POWER_STRATEGY_API"}),
        ("POST", base + "setpoint", {"setpoint": -2200}),
        ("POST", base + "active_strategy", {"strategy": "POWER_STRATEGY_API"}),
        ("POST", base + "setpoint", {"setpoint": 800}),
        ("POST", base + "setpoint", {"setpoint": 0}),
        ("POST", base + "active_strategy", {"strategy": "POWER_STRATEGY_NOM"}),
    ]


def test_sessy_setpoint_clamp() -> None:
    assert sessy.SessyHttpDriver.setpoint(-5000) == 1700
    assert sessy.SessyHttpDriver.setpoint(5000) == -2200


# --- Indevolt ----------------------------------------------------------------

INDEVOLT_DATA = {
    "1": "YZ-E3000",
    "6000": 850,  # discharging
    "6001": 1002,
    "6002": 57,
    "2278": -900,
    "667": -50,
    "7101": 4,
    "11006": 10,
    "6107": 1002,
    "6108": 52,
    "6109": 850,
    "1501": 0,
    "11016": 120,
    "9012": 24.5,
    "9003": 112,
    "9009": 3.31,
    "9011": 3.33,
    "11019": 9999,
    "11020": 95,
    "6004": 1.2,
    "6005": 3.4,
    "6006": 410.5,
    "6007": 380.2,
    "1505": 12000,
    "6105": 10,
    "11009": 2400,
    "114": 3000,
    "11011": 2400,
    "11032": 2000,
    "115": 3000,
    "142": 3.0,
    "606": "1002",
}


def test_indevolt_reading(hass: HomeAssistant) -> None:
    """+ discharging → + charging; bypass subtracted; 9999 dropped; missing
    points unknown; string enums parsed."""
    driver = indevolt.IndevoltHttpDriver(hass, "192.0.2.30")
    reading = driver.reading(INDEVOLT_DATA)
    assert reading.soc == 57
    assert reading.power_w == -850
    assert reading.telemetry.temperature_c == 24.5
    assert reading.telemetry.cycles == 112
    assert reading.telemetry.cell_min_v == 3.31
    assert reading.telemetry.charged_today_kwh == 1.2
    assert reading.telemetry.extra["discharged_total_kwh"] == 380.2
    extra = reading.extra
    assert extra["model"] == "SolidFlex/PowerFlex 3000"
    assert extra["ac_power_w"] == -850
    assert extra["pv_total_kwh"] == 12.0
    assert extra["status"] == "discharging"
    assert extra["work_mode"] == "realtime"
    assert extra["operating_status"] == "grid_discharging"
    assert extra["device_mode"] == "standalone"
    assert extra["remaining_charge_min"] is None
    assert extra["remaining_discharge_min"] == 95
    assert extra["max_charge_w"] == 2400
    assert extra["max_discharge_w"] == 2000
    assert extra["capacity_kwh"] == 3.0
    assert driver.reading({}).soc is None


async def test_indevolt_read_request(hass: HomeAssistant) -> None:
    """One GetData POST: points URL-encoded as compact JSON, no body, port
    8080, Connection: close; a non-finite number is refused."""
    driver = indevolt.IndevoltHttpDriver(hass, "192.0.2.30")
    fake = FakeSession(INDEVOLT_DATA, b'{"6002": NaN}')
    with session_for(indevolt, fake):
        assert (await driver.async_read()).soc == 57
        driver._last_start = None  # no pacing wait in the test
        with pytest.raises(ValueError, match="non-finite"):
            await driver.async_points([6002])
    call = fake.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "http://192.0.2.30:8080/rpc/Indevolt.GetData"
    assert "json" not in call and "data" not in call
    assert call["headers"]["Connection"] == "close"
    config = json.loads(call["params"]["config"])
    assert config["t"] == list(indevolt.POINTS.values())
    assert len(config["t"]) <= 50
    assert " " not in call["params"]["config"]


async def test_indevolt_pacing(hass: HomeAssistant) -> None:
    """At least 1 s between request starts, whatever the option says."""
    driver = indevolt.IndevoltHttpDriver(hass, "192.0.2.30", spacing=0.2)
    assert driver.spacing == 1.0
    clock = [100.0]
    driver._now = lambda: clock[0]
    driver._sleep = AsyncMock()
    fake = FakeSession({"6002": 50}, {"6002": 51})
    with session_for(indevolt, fake):
        await driver.async_points([6002])
        clock[0] = 100.25
        await driver.async_points([6002])
    driver._sleep.assert_awaited_once_with(pytest.approx(0.75))


async def test_indevolt_writes(hass: HomeAssistant) -> None:
    """Only point 47015: STOP and its echo when taking control, then the
    tuple with a rolling target; identical tuples are not resent; release
    is STOP."""
    driver = indevolt.IndevoltHttpDriver(hass, "192.0.2.30")
    driver._sleep = AsyncMock()
    control = {k: INDEVOLT_DATA[k] for k in map(str, indevolt.CONTROL_POINTS)}
    accepted = {"result": True}
    echo = {"6107": 1000, "6000": 20, "2278": 0, "667": 0}
    fake = FakeSession(
        control, accepted, echo, accepted,  # take control, charge
        control, accepted,  # discharge
        control,  # same discharge: nothing sent
        accepted,  # release
    )  # fmt: skip
    with session_for(indevolt, fake):
        await driver.async_set_power(5000)
        await driver.async_set_power(-1500)
        await driver.async_set_power(-1500)
        await driver.async_release()
    writes = [
        json.loads(c["params"]["config"])
        for c in fake.calls
        if c["url"].endswith("Indevolt.SetData")
    ]
    assert writes == [
        {"f": 16, "t": 47015, "v": [0, 0, 0]},
        {"f": 16, "t": 47015, "v": [1, 2400, 62]},
        {"f": 16, "t": 47015, "v": [2, 1500, 52]},
        {"f": 16, "t": 47015, "v": [0, 0, 0]},
    ]
    assert not fake.replies


@pytest.mark.parametrize(
    ("changes", "message"),
    [({"1": "YZ-E1600"}, "not controllable"), ({"7101": 1}, "realtime")],
)
async def test_indevolt_refuses_control(
    hass: HomeAssistant, changes: dict[str, Any], message: str
) -> None:
    """Generation 1 / unknown models and a work mode other than realtime are
    refused before anything is written (the mode is never written)."""
    driver = indevolt.IndevoltHttpDriver(hass, "192.0.2.30")
    fake = FakeSession({**INDEVOLT_DATA, **changes})
    with session_for(indevolt, fake), pytest.raises(RuntimeError, match=message):
        await driver.async_set_power(500)
    assert len(fake.calls) == 1


def test_indevolt_command_validation() -> None:
    """Only valid realtime tuples; discharge target never below the reserve."""
    state = {"6002": 12, "6105": 10, "11011": 2400, "115": 3000}
    assert indevolt.IndevoltHttpDriver.command(-800, state) == (2, 800, 10)
    assert indevolt.IndevoltHttpDriver.command(0.3, state) == (0, 0, 0)
    with pytest.raises(ValueError):
        indevolt.valid_realtime((1, 20000, 50))
    with pytest.raises(ValueError):
        indevolt.valid_realtime((3, 100, 50))
    with pytest.raises(ValueError):
        indevolt.valid_realtime((1, 100.0, 50))
