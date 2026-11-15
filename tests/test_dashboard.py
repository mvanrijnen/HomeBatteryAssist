"""Tests for the power flow sensors and the status panel's websocket command."""

from datetime import timedelta

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.homebatteryassist.const import (
    CONF_CAPACITY,
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_CURRENT,
    CONF_MAX_DISCHARGE_POWER,
    CONF_PHASE,
    CONF_PHASES,
    CONF_POWER_SENSOR,
    CONF_SENSOR,
    CONF_SOC_SENSOR,
    DOMAIN,
    SUBENTRY_BATTERY,
    SUBENTRY_PV_SOURCE,
)

GRID = {
    CONF_PHASES: 3,
    CONF_MAX_CURRENT: 25,
    "sensor_l1": "sensor.l1",
    "sensor_l2": "sensor.l2",
    "sensor_l3": "sensor.l3",
}


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=GRID,
        options={CONF_HISTORY_INTERVAL: 15},
        subentries_data=[
            ConfigSubentryData(
                data={CONF_NAME: "Roof", CONF_SENSOR: "sensor.pv", CONF_PHASE: "none"},
                subentry_type=SUBENTRY_PV_SOURCE,
                title="Roof",
                unique_id="sensor.pv",
            ),
            ConfigSubentryData(
                data={
                    CONF_NAME: "Venus",
                    CONF_SOC_SENSOR: "sensor.bat_soc",
                    CONF_POWER_SENSOR: "sensor.bat_power",
                    CONF_CAPACITY: 5.12,
                    CONF_MAX_CHARGE_POWER: 2500,
                    CONF_MAX_DISCHARGE_POWER: 800,
                },
                subentry_type=SUBENTRY_BATTERY,
                title="Venus",
                unique_id="sensor.bat_power",
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _set(hass: HomeAssistant, entity_id: str, value: str, unit: str = "W") -> None:
    hass.states.async_set(entity_id, value, {"unit_of_measurement": unit})


async def test_flow_and_phase_load_sensors(hass: HomeAssistant) -> None:
    """Grid import/export, PV and phase load (% of the fuse) are exposed."""
    entry = await _setup(hass)
    registry = er.async_get(hass)

    def value(key: str) -> str:
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_{key}"
        )
        return hass.states.get(entity_id)

    _set(hass, "sensor.l1", "-1150")  # 5 A export
    _set(hass, "sensor.l2", "200")
    _set(hass, "sensor.l3", "10", "A")  # 2300 W
    _set(hass, "sensor.pv", "3000")
    _set(hass, "sensor.bat_soc", "50", "%")
    _set(hass, "sensor.bat_power", "500")  # charging
    await hass.async_block_till_done()

    assert float(value("grid_power").state) == 1350.0
    assert float(value("grid_import_power").state) == 1350.0
    assert float(value("grid_export_power").state) == 0.0
    assert float(value("pv_power").state) == 3000.0
    # 1350 + 3000 - 500 charging
    assert float(value("house_consumption").state) == 3850.0

    l1 = value("phase_l1_load")
    assert float(l1.state) == 20.0  # 5 A of 25 A
    assert l1.attributes["current"] == 5.0
    assert l1.attributes["max_current"] == 25
    assert float(value("phase_l3_load").state) == 40.0

    _set(hass, "sensor.l3", "-10", "A")
    await hass.async_block_till_done()
    assert float(value("grid_export_power").state) == 3250.0


async def test_status_websocket(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """The panel gets the entity ids, batteries and planning window."""
    entry = await _setup(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/status"})
    response = await client.receive_json()
    assert response["success"], response
    result = response["result"]

    assert result["phases"] == 3
    assert result["max_current"] == 25
    assert result["has_pv"] is True
    assert result["has_pv_forecast"] is False
    assert result["pv_forecast_now_w"] is None
    assert result["entities"]["house_consumption"].startswith("sensor.")
    assert set(result["entities"]) >= {
        "grid_power",
        "phase_l3_load",
        "batteries_soc",
        "last_decision",
    }
    (battery,) = result["batteries"]
    assert battery["name"] == "Venus"
    assert battery["capacity_kwh"] == 5.12
    assert "battery_soc" in battery["entities"]
    assert result["window"]["limited_by"] == "setting"
    assert result["reach"]["has_price"] is False
    assert result["reach"]["price_end"] is None
    assert result["reach"]["max_end"] > result["window"]["start"]
    assert result["decisions"][0]["message"]

    await hass.config_entries.async_unload(entry.entry_id)
    await client.send_json_auto_id({"type": f"{DOMAIN}/status"})
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "not_loaded"


async def test_history_websocket(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Hourly series and the weekday/weekend day profile for the charts."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    entry = await _setup(hass)
    history = entry.runtime_data.history
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    history.records = [
        # two 15-min records in one hour -> hourly average 300 W
        {
            "start": (now - timedelta(hours=2)).isoformat(),
            "minutes": 15,
            "avg_w": 200.0,
            "coverage": 1.0,
        },
        {
            "start": (now - timedelta(hours=2, minutes=-15)).isoformat(),
            "minutes": 15,
            "avg_w": 400.0,
            "coverage": 1.0,
        },
        # Monday 2026-11-09 12:00 local (11:00 UTC), imported hourly record
        {
            "start": "2026-11-09T11:00:00+00:00",
            "minutes": 60,
            "avg_w": 1000.0,
            "coverage": 1.0,
            "source": "import",
        },
        # Saturday 2026-11-14 12:00 local
        {
            "start": "2026-11-14T11:00:00+00:00",
            "minutes": 60,
            "avg_w": 500.0,
            "coverage": 0.5,
        },
    ]
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/history", "days": 1})
    result = (await client.receive_json())["result"]

    assert result["interval_minutes"] == 15
    assert result["imported"] == 1
    assert result["hourly"] == [
        [int((now - timedelta(hours=2)).timestamp() * 1000), 300.0, 0.0]
    ]
    assert result["has_excluded"] is False
    assert result["profile"]["weekday"][12] == 1000.0
    assert result["profile"]["weekend"][12] == 500.0
    assert result["profile"]["weekend"][3] is None
    assert result["days_covered"] == round((15 + 15 + 60 + 30) / 1440, 1)
