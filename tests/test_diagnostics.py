"""Tests for the diagnostics download."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist.const import (
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_PHASES,
    DOMAIN,
)
from custom_components.homebatteryassist.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics(hass: HomeAssistant) -> None:
    """Diagnostics show configuration and the state of every module."""
    hass.states.async_set("sensor.l1", "750", {"unit_of_measurement": "W"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.l1"},
        options={CONF_HISTORY_INTERVAL: 15},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert set(diag) == {"config", "inputs", "history", "forecasts", "decisions"}
    assert diag["config"]["data"]["sensor_l1"] == "sensor.l1"
    assert diag["inputs"]["house_consumption_w"] == 750.0
    assert diag["inputs"]["sources"]["sensor.l1"]["state"] == "750"
    assert diag["history"]["interval_minutes"] == 15
    assert diag["forecasts"]["horizon_limited_by"] == "setting"
    assert diag["decisions"][0]["key"] == "horizon_setting"
