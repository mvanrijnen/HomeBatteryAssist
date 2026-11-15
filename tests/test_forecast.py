"""Tests for price / PV forecasts and the planning horizon."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant, State
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.homebatteryassist.const import (
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_PHASES,
    CONF_PLANNING_HORIZON,
    CONF_PRICE_FORECAST,
    CONF_PV_FORECAST,
    DOMAIN,
)
from custom_components.homebatteryassist.forecast import (
    async_get_pv_forecast,
    parse_price_forecast,
    planning_horizon_end,
)

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=dt_util.UTC)
H = timedelta(hours=1)
HORIZON = "sensor.homebatteryassist_planning_horizon"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_parse_list_with_start_end() -> None:
    """Nordpool-style raw_today / raw_tomorrow lists with start/end/value."""
    state = State(
        "sensor.nordpool",
        "0.25",
        {
            "raw_today": [
                {"start": _iso(NOW), "end": _iso(NOW + H), "value": 0.25},
                {"start": _iso(NOW + H), "end": _iso(NOW + 2 * H), "value": 0.30},
            ],
            "raw_tomorrow": [
                {"start": _iso(NOW + 2 * H), "end": _iso(NOW + 3 * H), "value": 0.10}
            ],
        },
    )
    points = parse_price_forecast(state)
    assert [(p.start, p.end, p.price) for p in points] == [
        (NOW, NOW + H, 0.25),
        (NOW + H, NOW + 2 * H, 0.30),
        (NOW + 2 * H, NOW + 3 * H, 0.10),
    ]


def test_parse_list_without_end_infers_periods() -> None:
    """ENTSO-e style prices list with time/price; 15-minute periods are inferred."""
    q = timedelta(minutes=15)
    state = State(
        "sensor.entsoe",
        "0.2",
        {
            "prices": [
                {"time": _iso(NOW + q), "price": 0.21},
                {"time": _iso(NOW), "price": 0.20},
                {"time": _iso(NOW + 2 * q), "price": 0.22},
            ]
        },
    )
    points = parse_price_forecast(state)
    assert [p.start for p in points] == [NOW, NOW + q, NOW + 2 * q]
    assert points[-1].end == NOW + 3 * q


def test_parse_mapping_and_garbage() -> None:
    """{timestamp: price} mappings work; unusable items are skipped."""
    state = State(
        "sensor.prices",
        "1",
        {
            "forecast": {_iso(NOW): "0.3", "not a time": 1, _iso(NOW + H): "x"},
            "data": [{"from": "2026-11-16 13:00"}, "junk"],  # naive time, no price
        },
    )
    points = parse_price_forecast(state)
    assert [(p.start, p.end, p.price) for p in points] == [(NOW, NOW + H, 0.3)]
    assert parse_price_forecast(None) == []


@pytest.mark.parametrize(
    ("price_end", "pv_end", "price_cfg", "pv_cfg", "expected"),
    [
        (None, None, False, False, NOW + timedelta(days=2)),  # setting only
        (NOW + 30 * H, None, True, False, NOW + 30 * H),  # prices limit
        (NOW + 30 * H, NOW + 20 * H, True, True, NOW + 20 * H),  # PV limits
        (NOW + timedelta(days=5), None, True, False, NOW + timedelta(days=2)),
        (None, None, True, False, NOW),  # configured but no data
    ],
)
def test_planning_horizon_end(
    price_end: datetime | None,
    pv_end: datetime | None,
    price_cfg: bool,
    pv_cfg: bool,
    expected: datetime,
) -> None:
    """The horizon is the minimum of the setting and the configured forecasts."""
    assert (
        planning_horizon_end(
            NOW,
            2,
            price_end,
            pv_end,
            price_configured=price_cfg,
            pv_configured=pv_cfg,
        )
        == expected
    )


async def test_pv_forecast_is_summed(hass: HomeAssistant) -> None:
    """Solar forecasts of several integrations are added up per hour."""
    entries = []
    for name in ("east", "west"):
        entry = MockConfigEntry(domain="forecast_solar", title=name)
        entry.add_to_hass(hass)
        entry.mock_state(hass, ConfigEntryState.LOADED)
        entries.append(entry)

    forecasts = {
        entries[0].entry_id: {"wh_hours": {_iso(NOW): 100, _iso(NOW + H): 200}},
        entries[1].entry_id: {"wh_hours": {_iso(NOW + H): 50}},
    }
    platform = SimpleNamespace(
        async_get_solar_forecast=AsyncMock(side_effect=lambda h, eid: forecasts[eid])
    )
    with patch(
        "custom_components.homebatteryassist.forecast._async_solar_forecast_platform",
        AsyncMock(return_value=platform),
    ):
        total = await async_get_pv_forecast(hass, [e.entry_id for e in entries])
    for entry in entries:  # fake integrations: don't let teardown unload them
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
    assert total == {NOW: 100.0, NOW + H: 250.0}


async def test_planning_horizon_sensor(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The sensor shows the effective horizon and follows new prices."""
    freezer.move_to(NOW)
    hass.states.async_set(
        "sensor.prices",
        "0.25",
        {"prices": [{"start": _iso(NOW), "end": _iso(NOW + 12 * H), "price": 0.25}]},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.l1"},
        options={
            CONF_HISTORY_INTERVAL: 15,
            CONF_PLANNING_HORIZON: 2,
            CONF_PRICE_FORECAST: "sensor.prices",
            CONF_PV_FORECAST: ["pv_entry"],
        },
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.homebatteryassist.forecast.async_get_pv_forecast",
        AsyncMock(return_value={NOW + h * H: 100.0 for h in range(24)}),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get(HORIZON)
        assert dt_util.parse_datetime(state.state) == NOW + 12 * H
        assert state.attributes["pv_forecast_hours"] == 24
        assert state.attributes["max_days"] == 2

        # Tomorrow's prices arrive: now PV (24h) limits the horizon.
        hass.states.async_set(
            "sensor.prices",
            "0.25",
            {"prices": [{"start": _iso(NOW), "end": _iso(NOW + 36 * H), "price": 0.2}]},
        )
        await hass.async_block_till_done()
        freezer.tick(timedelta(seconds=15))  # debounce of the refresh request
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

        state = hass.states.get(HORIZON)
        assert dt_util.parse_datetime(state.state) == NOW + 24 * H


async def test_settings_step_lists_pv_forecasts(hass: HomeAssistant) -> None:
    """The PV forecast field appears only if a solar forecast integration exists."""
    pv = MockConfigEntry(domain="forecast_solar", title="Roof")
    pv.add_to_hass(hass)

    async def _to_settings() -> dict:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PHASES: "1"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_MAX_CURRENT: "35"}
        )
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], {"sensor_l1": "sensor.l1"}
        )

    target = (
        "custom_components.homebatteryassist.config_flow.async_solar_forecast_entries"
    )
    with patch(target, AsyncMock(return_value=[])):
        result = await _to_settings()
    assert CONF_PV_FORECAST not in result["data_schema"].schema

    with patch(target, AsyncMock(return_value=[pv])):
        result = await _to_settings()
        assert CONF_PV_FORECAST in result["data_schema"].schema
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HISTORY_INTERVAL: "15",
                CONF_PLANNING_HORIZON: 2,
                CONF_PV_FORECAST: [pv.entry_id],
            },
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_PV_FORECAST] == [pv.entry_id]
