"""A repair issue names the sensors the recorder leaves out."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.homebatteryassist.const import DOMAIN
from custom_components.homebatteryassist.engine.measure.recorder_check import (
    check_recorder,
)


async def test_repair_issue_for_sensors_not_recorded(hass: HomeAssistant) -> None:
    """Left out: an issue naming them; recorded again: the issue goes."""
    registry = ir.async_get(hass)
    issue_id = "recorder_excluded_sensors_x"
    # Without a recorder nothing is checked.
    assert check_recorder(hass, "x", ["sensor.l1"]) == []
    hass.config.components.add("recorder")
    with patch(
        "homeassistant.components.recorder.is_entity_recorded",
        side_effect=lambda _hass, entity_id: entity_id != "sensor.l1",
    ):
        assert check_recorder(hass, "x", ["sensor.l1", "sensor.soc", ""]) == [
            "sensor.l1"
        ]
    issue = registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_placeholders == {"sensors": "sensor.l1"}
    with patch(
        "homeassistant.components.recorder.is_entity_recorded", return_value=True
    ):
        assert check_recorder(hass, "x", ["sensor.l1"]) == []
    assert registry.async_get_issue(DOMAIN, issue_id) is None
