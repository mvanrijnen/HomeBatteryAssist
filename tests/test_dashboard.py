"""Tests for the power flow sensors and the status panel's websocket command."""

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
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
    assert result["decisions"][0]["message"]

    await hass.config_entries.async_unload(entry.entry_id)
    await client.send_json_auto_id({"type": f"{DOMAIN}/status"})
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "not_loaded"
