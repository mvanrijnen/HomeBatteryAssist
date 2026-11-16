"""Tests for the PV source and excluded load subentry flows."""

import pytest
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    ConfigSubentryData,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist.const import (
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_PHASE,
    CONF_PHASES,
    CONF_SENSOR,
    DOMAIN,
    SUBENTRY_EXCLUDED_LOAD,
    SUBENTRY_PV_SOURCE,
)

THREE_PHASE = {
    CONF_PHASES: 3,
    CONF_MAX_CURRENT: 25,
    "sensor_l1": "sensor.l1",
    "sensor_l2": "sensor.l2",
    "sensor_l3": "sensor.l3",
    "return_l1": "sensor.r1",
}


async def _entry(
    hass: HomeAssistant, data: dict, subentries: list | None = None
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        options={CONF_HISTORY_INTERVAL: 15},
        subentries_data=subentries or [],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize("kind", [SUBENTRY_PV_SOURCE, SUBENTRY_EXCLUDED_LOAD])
async def test_add_device_three_phase(hass: HomeAssistant, kind: str) -> None:
    """On 3-phase, a device can be added with an optional phase."""
    entry = await _entry(hass, THREE_PHASE)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, kind), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    pv = {"pv_driver", "pv_address"} if kind == SUBENTRY_PV_SOURCE else set()
    assert set(result["data_schema"].schema) == {
        CONF_NAME,
        CONF_SENSOR,
        CONF_PHASE,
        "phase_sensor_l1",
        "phase_sensor_l2",
        "phase_sensor_l3",
        *pv,
    }

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {CONF_NAME: "Device", CONF_SENSOR: "sensor.device", CONF_PHASE: "l2"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()  # the entry reloads
    (subentry,) = entry.subentries.values()
    assert subentry.subentry_type == kind
    assert subentry.title == "Device"
    assert dict(subentry.data) == {
        CONF_NAME: "Device",
        CONF_SENSOR: "sensor.device",
        CONF_PHASE: "l2",
        **({"pv_driver": "sensor"} if kind == SUBENTRY_PV_SOURCE else {}),
    }


async def test_single_phase_has_no_phase_field(hass: HomeAssistant) -> None:
    """On 1-phase there is no phase to choose; it is stored as not bound."""
    entry = await _entry(
        hass, {CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.l1"}
    )
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_PV_SOURCE), context={"source": SOURCE_USER}
    )
    assert set(result["data_schema"].schema) == {
        CONF_NAME,
        CONF_SENSOR,
        "pv_driver",
        "pv_address",
    }

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_NAME: "Roof", CONF_SENSOR: "sensor.pv"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()  # the entry reloads
    (subentry,) = entry.subentries.values()
    assert subentry.data[CONF_PHASE] == "none"


@pytest.mark.parametrize(
    ("sensor", "error"),
    [
        ("sensor.l2", "sensor_is_phase_sensor"),
        ("sensor.r1", "sensor_is_phase_sensor"),
        ("sensor.pv", "sensor_in_use"),
    ],
)
async def test_sensor_validation(hass: HomeAssistant, sensor: str, error: str) -> None:
    """Grid sensors and sensors of other devices cannot be reused."""
    entry = await _entry(
        hass,
        THREE_PHASE,
        [
            ConfigSubentryData(
                data={CONF_NAME: "Roof", CONF_SENSOR: "sensor.pv", CONF_PHASE: "none"},
                subentry_type=SUBENTRY_PV_SOURCE,
                title="Roof",
                unique_id="sensor.pv",
            )
        ],
    )
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_EXCLUDED_LOAD), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {CONF_NAME: "EV", CONF_SENSOR: sensor, CONF_PHASE: "none"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_SENSOR: error}


async def test_reconfigure_device(hass: HomeAssistant) -> None:
    """An existing device can be changed, keeping its own sensor."""
    entry = await _entry(
        hass,
        THREE_PHASE,
        [
            ConfigSubentryData(
                data={CONF_NAME: "EV", CONF_SENSOR: "sensor.ev", CONF_PHASE: "none"},
                subentry_type=SUBENTRY_EXCLUDED_LOAD,
                title="EV",
                unique_id="sensor.ev",
            )
        ],
    )
    (subentry_id,) = entry.subentries

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_EXCLUDED_LOAD),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {CONF_NAME: "EV charger", CONF_SENSOR: "sensor.ev", CONF_PHASE: "l3"},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    subentry = entry.subentries[subentry_id]
    assert subentry.title == "EV charger"
    assert subentry.data[CONF_PHASE] == "l3"


async def test_pv_source_read_directly(hass: HomeAssistant) -> None:
    """A PV source can be a meter read directly instead of a sensor."""
    from unittest.mock import AsyncMock, patch

    entry = await _entry(hass, THREE_PHASE)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_PV_SOURCE), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_NAME: "Roof", "pv_driver": "homewizard"}
    )
    assert result["errors"] == {"pv_address": "address_required"}
    with patch(
        "custom_components.homebatteryassist.engine.devices.meters.discovery.HomeWizardP1.async_start",
        AsyncMock(),
    ):
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {CONF_NAME: "Roof", "pv_driver": "homewizard", "pv_address": "192.0.2.21"},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        measurements = entry.runtime_data.measurements
        (meter, _phase) = measurements.pv_meters[0]
        meter._set((1200.0,))  # the kWh meter on the inverter: 1.2 kW
        measurements._update(meter.updated)
        assert measurements.flow is None or measurements.flow.pv_w in (0.0, 1200.0)
        assert await hass.config_entries.async_unload(entry.entry_id)
