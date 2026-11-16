"""Tests for recalculating the forecasts: action, button and event."""

import pytest
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.homebatteryassist.const import (
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_PHASES,
    CONF_PRICE_FORECAST,
    DOMAIN,
)
from custom_components.homebatteryassist.engine.coordinator import (
    EVENT_FORECAST_UPDATED,
)


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    hass.states.async_set("sensor.prices", "0.2", {"prices": []})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.l1"},
        options={CONF_HISTORY_INTERVAL: 15, CONF_PRICE_FORECAST: "sensor.prices"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_recalculate_action(hass: HomeAssistant) -> None:
    """The action recalculates now, returns the result and fires an event."""
    await _setup(hass)
    events = async_capture_events(hass, EVENT_FORECAST_UPDATED)

    response = await hass.services.async_call(
        DOMAIN, "recalculate", blocking=True, return_response=True
    )
    assert response["limited_by"] == "no_price"
    assert response["hours_ahead"] == 0

    # New prices, recalculated on request (not waiting for the 15-min cycle).
    hass.states.async_set(
        "sensor.prices",
        "0.2",
        {"prices": [{"start": "2099-01-01T00:00:00+00:00", "price": 0.2}]},
    )
    response = await hass.services.async_call(
        DOMAIN, "recalculate", blocking=True, return_response=True
    )
    assert response["limited_by"] == "setting"
    await hass.async_block_till_done()
    # The price sensor change itself also triggers a (debounced) recalculation.
    assert events[0].data["limited_by"] == "no_price"
    assert events[-1].data["limited_by"] == "setting"

    # Also callable without asking for a response (automations, scripts).
    assert await hass.services.async_call(DOMAIN, "recalculate", blocking=True) is None


async def test_recalculate_button(hass: HomeAssistant) -> None:
    """Pressing the button recalculates."""
    entry = await _setup(hass)
    events = async_capture_events(hass, EVENT_FORECAST_UPDATED)
    button = er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, f"{entry.entry_id}_recalculate"
    )
    await hass.services.async_call(
        "button", SERVICE_PRESS, {ATTR_ENTITY_ID: button}, blocking=True
    )
    await hass.async_block_till_done()
    assert len(events) == 1


async def test_recalculate_when_not_loaded(hass: HomeAssistant) -> None:
    """Without a loaded entry the action reports a clear error."""
    assert await async_setup_component(hass, DOMAIN, {})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "recalculate", blocking=True)
