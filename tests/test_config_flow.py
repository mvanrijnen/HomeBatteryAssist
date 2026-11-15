"""Tests for the HomeBatteryAssist config flow."""

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist.const import (
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_PHASES,
    CONF_PLANNING_HORIZON,
    CONF_PRICE_FORECAST,
    DOMAIN,
    NAME,
)


async def _init(hass: HomeAssistant) -> dict:
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


async def _start(hass: HomeAssistant) -> dict:
    """Start the setup and choose your own sensors in the meter step."""
    result = await _init(hass)
    assert result["step_id"] == "meter"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"source": "manual"}
    )


async def test_three_phase_flow(hass: HomeAssistant) -> None:
    """3-phase: phases -> connection size -> three phase sensors."""
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PHASES: "3"}
    )
    assert result["step_id"] == "max_current"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MAX_CURRENT: "35"}
    )
    assert result["step_id"] == "sensors"
    assert set(result["data_schema"].schema) == {
        "sensor_l1",
        "sensor_l2",
        "sensor_l3",
        "return_l1",
        "return_l2",
        "return_l3",
    }

    sensors = {
        "sensor_l1": "sensor.power_l1",
        "sensor_l2": "sensor.power_l2",
        "sensor_l3": "sensor.power_l3",
    }
    result = await hass.config_entries.flow.async_configure(result["flow_id"], sensors)
    assert result["step_id"] == "settings"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HISTORY_INTERVAL: "5",
            CONF_PLANNING_HORIZON: 3,
            CONF_PRICE_FORECAST: "sensor.prices",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {CONF_PHASES: 3, CONF_MAX_CURRENT: 35, **sensors}
    assert result["options"] == {
        CONF_HISTORY_INTERVAL: 5,
        CONF_PLANNING_HORIZON: 3,
        "forecast_interval": 15,  # default
        CONF_PRICE_FORECAST: "sensor.prices",
        "plan_mode": "nom",  # defaults of the battery plan
        "export_price_factor": 1.0,
        "export_price_mode": "factor",
        "max_cycles_per_day": 1.0,
        "cycle_cost": 0.02,
        "min_battery_power": 300,
        "phase_margin": 10,
        "balance_interval": 60,
        "full_charge_window_days": 3,
    }


async def test_single_phase_flow(hass: HomeAssistant) -> None:
    """1-phase: only one phase sensor is asked."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PHASES: "1"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MAX_CURRENT: "35"}
    )
    assert set(result["data_schema"].schema) == {"sensor_l1", "return_l1"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"sensor_l1": "sensor.power_l1"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HISTORY_INTERVAL: "15", CONF_PLANNING_HORIZON: 2}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {
        CONF_HISTORY_INTERVAL: 15,
        CONF_PLANNING_HORIZON: 2,
        "forecast_interval": 15,
        "plan_mode": "nom",  # defaults of the battery plan
        "export_price_factor": 1.0,
        "export_price_mode": "factor",
        "max_cycles_per_day": 1.0,
        "cycle_cost": 0.02,
        "min_battery_power": 300,
        "phase_margin": 10,
        "balance_interval": 60,
        "full_charge_window_days": 3,
    }
    assert result["data"] == {
        CONF_PHASES: 1,
        CONF_MAX_CURRENT: 35,
        "sensor_l1": "sensor.power_l1",
    }


@pytest.mark.parametrize(
    ("phases", "invalid"), [("1", "25x"), ("1", "50"), ("3", "10")]
)
async def test_connection_size_must_match_phases(
    hass: HomeAssistant, phases: str, invalid: str
) -> None:
    """Only connection sizes valid for the phase count are accepted."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PHASES: phases}
    )
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_MAX_CURRENT: invalid}
        )


async def test_duplicate_sensor_rejected(hass: HomeAssistant) -> None:
    """The same sensor cannot be used for two phases."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PHASES: "3"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MAX_CURRENT: "25"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "sensor_l1": "sensor.power_l1",
            "sensor_l2": "sensor.power_l1",
            "sensor_l3": "sensor.power_l3",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "duplicate_sensor"}


async def test_single_instance(hass: HomeAssistant) -> None:
    """A second instance is rejected."""
    MockConfigEntry(domain=DOMAIN).add_to_hass(hass)

    result = await _init(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow_changes_settings(hass: HomeAssistant) -> None:
    """Settings can be changed afterwards; clearing the price sensor removes it."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.power_l1"},
        options={
            CONF_HISTORY_INTERVAL: 15,
            CONF_PLANNING_HORIZON: 2,
            CONF_PRICE_FORECAST: "sensor.prices",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["settings", "grid"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    assert result["step_id"] == "settings"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_HISTORY_INTERVAL: "60",
            CONF_PLANNING_HORIZON: 5,
            "forecast_interval": "5",
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_HISTORY_INTERVAL: 60,
        CONF_PLANNING_HORIZON: 5,
        "forecast_interval": 5,
        "plan_mode": "nom",  # defaults of the battery plan
        "export_price_factor": 1.0,
        "export_price_mode": "factor",
        "max_cycles_per_day": 1.0,
        "cycle_cost": 0.02,
        "min_battery_power": 300,
        "phase_margin": 10,
        "balance_interval": 60,
        "full_charge_window_days": 3,
    }
    await hass.async_block_till_done()
    # The reloaded entry recalculates every 5 minutes.
    assert entry.runtime_data.forecast.update_interval.total_seconds() == 300


async def test_reconfigure_grid_connection(hass: HomeAssistant) -> None:
    """The grid connection can be changed; emptied return sensors are removed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_PHASES: 3,
            CONF_MAX_CURRENT: 25,
            "sensor_l1": "sensor.current_l1",
            "sensor_l2": "sensor.current_l2",
            "sensor_l3": "sensor.current_l3",
            "return_l1": "sensor.pv_l1",
            "return_l2": "sensor.pv_l2",
            "return_l3": "sensor.pv_l3",
        },
        options={CONF_HISTORY_INTERVAL: 15},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "meter"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"source": "manual"}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PHASES: "3"}
    )
    assert result["step_id"] == "max_current"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MAX_CURRENT: "25"}
    )
    assert result["step_id"] == "sensors"
    suggested = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }
    assert suggested["return_l2"] == "sensor.pv_l2"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "sensor_l1": "sensor.power_l1",
            "sensor_l2": "sensor.power_l2",
            "sensor_l3": "sensor.power_l3",
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert dict(entry.data) == {
        CONF_PHASES: 3,
        CONF_MAX_CURRENT: 25,
        "sensor_l1": "sensor.power_l1",
        "sensor_l2": "sensor.power_l2",
        "sensor_l3": "sensor.power_l3",
    }
    assert entry.options == {CONF_HISTORY_INTERVAL: 15}  # settings untouched


def _homewizard(hass: HomeAssistant, prefix: str, phases: int, marker: bool) -> None:
    """Register a HomeWizard device like the core integration does."""
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    source = MockConfigEntry(domain="homewizard")
    source.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=source.entry_id,
        identifiers={("homewizard", prefix)},
        name="P1 meter" if marker else "kWh meter",
        model="HWE-P1" if marker else "HWE-KWH1",
    )
    registry = er.async_get(hass)
    if marker:
        registry.async_get_or_create(
            "sensor",
            "homewizard",
            f"{prefix}_smr_version",
            device_id=device.id,
            translation_key="dsmr_version",
        )
    for n in range(1, phases + 1):
        registry.async_get_or_create(
            "sensor",
            "homewizard",
            f"{prefix}_active_power_l{n}_w",
            device_id=device.id,
            translation_key="active_power_phase_w",
            suggested_object_id=f"{prefix.lower()}_power_l{n}",
        )


async def test_detected_meter_fills_in_sensors(hass: HomeAssistant) -> None:
    """A HomeWizard P1 meter is offered; kWh meters are not grid meters."""
    _homewizard(hass, "HWE-P1_abc", 3, marker=True)
    _homewizard(hass, "HWE-KWH1_def", 1, marker=False)
    result = await _init(hass)
    assert result["step_id"] == "meter"
    options = result["data_schema"].schema["source"].config["options"]
    assert [o["value"] for o in options][-1] == "manual"
    # the P1 meter (via its sensors), a direct meter by address, manual
    assert [o["value"] for o in options][1:] == ["direct_manual", "manual"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"source": options[0]["value"]}
    )
    assert result["step_id"] == "max_current"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MAX_CURRENT: "25"}
    )
    assert result["step_id"] == "settings"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HISTORY_INTERVAL: "15", CONF_PLANNING_HORIZON: 2}
    )
    assert result["data"] == {
        CONF_PHASES: 3,
        CONF_MAX_CURRENT: 25,
        "sensor_l1": "sensor.hwe_p1_abc_power_l1",
        "sensor_l2": "sensor.hwe_p1_abc_power_l2",
        "sensor_l3": "sensor.hwe_p1_abc_power_l3",
    }


async def test_detected_meter_manual_choice(hass: HomeAssistant) -> None:
    """Separate sensors stay possible next to a detected meter."""
    _homewizard(hass, "HWE-P1_abc", 3, marker=True)
    result = await _init(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"source": "manual"}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PHASES: "1"}
    )
    assert result["step_id"] == "max_current"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MAX_CURRENT: "35"}
    )
    assert result["step_id"] == "sensors"


async def test_options_flow_changes_grid_meter(hass: HomeAssistant) -> None:
    """The meter and phases can also be changed under Configure."""
    _homewizard(hass, "HWE-P1_abc", 3, marker=True)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.power_l1"},
        options={CONF_HISTORY_INTERVAL: 15, CONF_PLANNING_HORIZON: 2},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "grid"}
    )
    assert result["step_id"] == "meter"
    options = result["data_schema"].schema["source"].config["options"]
    values = [o["value"] for o in options]
    assert values[1:] == ["direct_manual", "manual"]  # P1 sensors first
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"source": values[0]}
    )
    assert result["step_id"] == "max_current"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MAX_CURRENT: "25"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.data[CONF_PHASES] == 3
    assert entry.data[CONF_MAX_CURRENT] == 25
    assert entry.data["sensor_l3"] == "sensor.hwe_p1_abc_power_l3"
    assert entry.options[CONF_PLANNING_HORIZON] == 2


async def test_direct_meter_keeps_own_sensors(
    hass: HomeAssistant, no_speedwire_discovery
) -> None:
    """Switching to a direct meter keeps the sensors; back to manual: prefilled."""
    from unittest.mock import AsyncMock, patch

    no_speedwire_discovery.return_value = {"192.0.2.199": 1900000001}
    # No network in tests: the meter does not really listen.
    with patch(
        "custom_components.homebatteryassist.inputs.direct.SpeedwireMeter.async_start",
        AsyncMock(),
    ):
        await _direct_meter_keeps_own_sensors(hass)


async def _direct_meter_keeps_own_sensors(hass: HomeAssistant) -> None:
    data = {
        CONF_PHASES: 3,
        CONF_MAX_CURRENT: 25,
        "sensor_l1": "sensor.p1_l1",
        "sensor_l2": "sensor.p1_l2",
        "sensor_l3": "sensor.p1_l3",
    }
    entry = MockConfigEntry(
        domain=DOMAIN, data=data, options={CONF_HISTORY_INTERVAL: 15}
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "meter"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"source": "direct:speedwire:192.0.2.199"}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PHASES: "3"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MAX_CURRENT: "25"}
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {
        **data,
        "meter_source": "speedwire",
        "meter_address": "192.0.2.199",
    }

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "meter"
    key = next(k for k in result["data_schema"].schema if str(k) == "source")
    assert key.default() == "direct:speedwire:192.0.2.199"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"source": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PHASES: "3"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MAX_CURRENT: "25"}
    )
    assert result["step_id"] == "sensors"
    suggested = {
        str(key): key.description.get("suggested_value")
        for key in result["data_schema"].schema
        if key.description
    }
    assert suggested["sensor_l1"] == "sensor.p1_l1"
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_direct_meter_by_address(hass: HomeAssistant) -> None:
    """A meter not in Home Assistant can be read directly at an address."""
    from unittest.mock import AsyncMock, patch

    with patch(
        "custom_components.homebatteryassist.inputs.direct.IammeterMeter.async_start",
        AsyncMock(),
    ):
        await _direct_meter_by_address(hass)
    (entry,) = hass.config_entries.async_entries(DOMAIN)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def _direct_meter_by_address(hass: HomeAssistant) -> None:
    result = await _init(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"source": "direct_manual"}
    )
    assert result["step_id"] == "direct"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"meter_source": "iammeter", "meter_address": " 192.0.2.50 "},
    )
    assert result["step_id"] == "user"  # Iammeter: 1 or 3 phases, so ask
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PHASES: "3"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MAX_CURRENT: "25"}
    )
    assert result["step_id"] == "settings"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HISTORY_INTERVAL: "15", CONF_PLANNING_HORIZON: 2}
    )
    assert result["data"] == {
        CONF_PHASES: 3,
        CONF_MAX_CURRENT: 25,
        "meter_source": "iammeter",
        "meter_address": "192.0.2.50",
    }
