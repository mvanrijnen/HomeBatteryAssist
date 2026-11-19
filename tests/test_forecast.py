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
from custom_components.homebatteryassist.engine.forecast.planning_window import (
    HorizonLimit,
    PlanningWindow,
    planning_horizon,
)
from custom_components.homebatteryassist.engine.sources.prices.price_points import (
    parse_price_forecast,
)
from custom_components.homebatteryassist.engine.sources.pv_forecasts.energy_dashboard_platform import (
    async_get_pv_forecast,
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


def test_parse_epoch_arrays_with_published_and_forecast() -> None:
    """DynTarNL: [epoch ms, price, "p"/"f"] quarter-hour points incl. EPEX forecast."""
    ms = int(NOW.timestamp() * 1000)
    q = 15 * 60 * 1000
    state = State(
        "sensor.dyntarnl_e_all_in_forecast_avg",
        "0.34",
        {
            "prices": [
                [ms, 0.40233, "p"],
                [ms + q, 0.39, "p"],
                [ms + 2 * q, 0.31, "f"],
                [ms + 3 * q, 0.30, "f"],
            ],
            # Hourly forecast list: same starts as above, so not used twice.
            "forecast": [[ms, 0.37756]],
            "forecast_until": "2026-11-20T15:00:00+01:00",
        },
    )
    points = parse_price_forecast(state)
    quarter = timedelta(minutes=15)
    assert [(p.start, p.price, p.estimated) for p in points] == [
        (NOW, 0.40233, False),
        (NOW + quarter, 0.39, False),
        (NOW + 2 * quarter, 0.31, True),
        (NOW + 3 * quarter, 0.30, True),
    ]
    assert points[-1].end == NOW + 4 * quarter


def test_parse_epoch_seconds_and_iso_arrays() -> None:
    """Arrays with epoch seconds or ISO strings work too."""
    state = State(
        "sensor.x",
        "1",
        {"data": [[int(NOW.timestamp()), "0.1"], [(NOW + H).isoformat(), 0.2]]},
    )
    assert [(p.start, p.price) for p in parse_price_forecast(state)] == [
        (NOW, 0.1),
        (NOW + H, 0.2),
    ]


@pytest.mark.parametrize(
    ("price_end", "pv_end", "price_cfg", "pv_cfg", "expected", "limit"),
    [
        (None, None, False, False, NOW + timedelta(days=2), HorizonLimit.SETTING),
        (NOW + 30 * H, None, True, False, NOW + 30 * H, HorizonLimit.PRICE),
        (NOW + 30 * H, NOW + 20 * H, True, True, NOW + 20 * H, HorizonLimit.PV),
        (
            NOW + timedelta(days=5),
            None,
            True,
            False,
            NOW + timedelta(days=2),
            HorizonLimit.SETTING,
        ),
        (None, None, True, False, NOW, HorizonLimit.NO_PRICE),
        (NOW + 30 * H, NOW - H, True, True, NOW, HorizonLimit.NO_PV),
        (None, NOW + 5 * H, False, True, NOW + 5 * H, HorizonLimit.PV),
    ],
)
def test_planning_horizon(
    price_end: datetime | None,
    pv_end: datetime | None,
    price_cfg: bool,
    pv_cfg: bool,
    expected: datetime,
    limit: HorizonLimit,
) -> None:
    """The horizon is the minimum of the setting and the configured forecasts."""
    window = planning_horizon(
        NOW, 2, price_end, pv_end, price_configured=price_cfg, pv_configured=pv_cfg
    )
    assert (window.start, window.end, window.limited_by) == (NOW, expected, limit)
    assert window.is_empty == (expected == NOW)


def test_window_slots_and_overlap() -> None:
    """Slots are clock aligned, cut off at the end; nothing beyond the window."""
    q = timedelta(minutes=15)
    window = PlanningWindow(
        NOW + timedelta(minutes=7), NOW + timedelta(minutes=40), HorizonLimit.PRICE
    )
    assert window.hours == pytest.approx(33 / 60)
    assert window.slots(q) == [
        (NOW, NOW + q),
        (NOW + q, NOW + 2 * q),
        (NOW + 2 * q, NOW + timedelta(minutes=40)),
    ]
    assert window.overlaps(NOW, NOW + q)
    assert not window.overlaps(NOW + H, NOW + 2 * H)
    assert PlanningWindow(NOW, NOW, HorizonLimit.NO_PRICE).slots(q) == []


async def test_pv_forecast_is_summed(hass: HomeAssistant) -> None:
    """Solar forecasts of several integrations are added up per hour."""
    entries = []
    for name in ("east", "west"):
        entry = MockConfigEntry(domain="solcast_solar", title=name)
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
        "custom_components.homebatteryassist.engine.sources.pv_forecasts.energy_dashboard_platform._async_solar_forecast_platform",
        AsyncMock(return_value=platform),
    ):
        total = await async_get_pv_forecast(hass, [e.entry_id for e in entries])
    for entry in entries:  # fake integrations: don't let teardown unload them
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
    assert total == {NOW: 100.0, NOW + H: 250.0}


async def test_forecast_solar_keys_are_period_ends(hass: HomeAssistant) -> None:
    """Forecast.Solar labels an amount with the end of its period: 19:00 is
    18:00-19:00, so it counts in the hour before."""
    entry = MockConfigEntry(domain="forecast_solar", title="roof")
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    platform = SimpleNamespace(
        async_get_solar_forecast=AsyncMock(
            return_value={"wh_hours": {_iso(NOW + H): 300}}
        )
    )
    with patch(
        "custom_components.homebatteryassist.engine.sources.pv_forecasts.energy_dashboard_platform._async_solar_forecast_platform",
        AsyncMock(return_value=platform),
    ):
        total = await async_get_pv_forecast(hass, [entry.entry_id])
    entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
    (start,) = total
    assert start.replace(minute=0, second=0) == NOW.replace(minute=0, second=0)


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
        "custom_components.homebatteryassist.engine.sources.pv_forecasts.solar_forecast_integrations.async_get_pv_forecast",
        AsyncMock(return_value={NOW + h * H: 100.0 for h in range(24)}),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get(HORIZON)
        assert dt_util.parse_datetime(state.state) == NOW + 12 * H
        assert state.attributes["max_days"] == 2
        assert state.attributes["limited_by"] == "price"
        assert state.attributes["hours_ahead"] == 12
        # Expected PV in the current hour, for the dashboard.
        assert entry.runtime_data.forecast.data.pv_now_w == 100.0
        # Only data inside the window is used: 12 of the 24 PV hours.
        assert state.attributes["pv_forecast_hours"] == 12

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
        assert state.attributes["limited_by"] == "pv"

    # Each change of the limiting factor is explained once in the decision log.
    keys = [
        d["key"]
        for d in entry.runtime_data.decisions.entries
        if d["category"] == "planning" and d["key"].startswith("horizon_")
    ]
    assert keys == ["horizon_price", "horizon_pv"]
    # The longer price list in between is announced as new prices.
    assert any(
        d["key"] == "prices_updated" for d in entry.runtime_data.decisions.entries
    )


async def test_settings_step_lists_pv_forecasts(hass: HomeAssistant) -> None:
    """The PV forecast field appears only if a solar forecast integration exists."""
    pv = MockConfigEntry(domain="forecast_solar", title="Roof")
    pv.add_to_hass(hass)

    async def _to_settings() -> dict:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"source": "manual"}
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

    target = "custom_components.homebatteryassist.engine.sources.pv_forecasts.solar_forecast_integrations.async_solar_forecast_entries"
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


def test_pv_forecast_without_night_covers_its_day() -> None:
    """Forecast.Solar gives sunrise..sunset only: the forecast still covers
    its last day up to local midnight (no sun after sunset), so the window
    does not end at sunset; a forecast with night hours ends at its last."""
    from datetime import datetime

    from homeassistant.util import dt as dt_util

    from custom_components.homebatteryassist.engine.coordinator import _pv_end

    tz = dt_util.get_default_time_zone()
    day = [datetime(2026, 11, 19, h, tzinfo=tz) for h in range(8, 17)]
    end = _pv_end({dt_util.as_utc(k): 100.0 for k in day})
    assert dt_util.as_local(end) == datetime(2026, 11, 20, 0, tzinfo=tz)
    full = [datetime(2026, 11, 19, h, tzinfo=tz) for h in range(24)]
    end = _pv_end({dt_util.as_utc(k): 0.0 for k in full})
    assert dt_util.as_local(end) == datetime(2026, 11, 20, 0, tzinfo=tz)
    part = [datetime(2026, 11, 19, h, tzinfo=tz) for h in range(0, 13)]
    end = _pv_end({dt_util.as_utc(k): 0.0 for k in part})
    assert dt_util.as_local(end) == datetime(2026, 11, 19, 13, tzinfo=tz)
