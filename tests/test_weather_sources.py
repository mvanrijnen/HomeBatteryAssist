"""Tests for the weather source modules."""

from datetime import date, datetime, timedelta
from pathlib import Path

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.homebatteryassist.engine.sources.weather import (
    BUILTIN,
    KnmiWeatherSource,
    OpenMeteoKnmiSource,
    WeatherEntitySource,
    WeatherSettings,
    WeerliveWeatherSource,
    checked_forecast,
    combine,
    create_weather_source,
    daily_curve,
    load_weather_sources_from,
)
from custom_components.homebatteryassist.engine.sources.weather.open_meteo import (
    URL as OPEN_METEO_URL,
)
from custom_components.homebatteryassist.engine.sources.weather.weerlive_api import (
    URL as WEERLIVE_URL,
)
from custom_components.homebatteryassist.engine.sources.weather.weerlive_api import (
    parse_weerlive,
)

PACKAGE = (
    Path(__file__).parent.parent
    / "custom_components/homebatteryassist/engine/sources/weather"
)
UTC = dt_util.UTC


async def test_daily_curve_and_combine(hass: HomeAssistant) -> None:
    """Coldest early morning, warmest mid afternoon; hourly values first."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    curve = daily_curve(
        {date(2026, 11, 20): (2.0, 10.0), date(2026, 11, 21): (4.0, 8.0)}
    )
    local = {
        dt_util.as_local(k).hour: v
        for k, v in curve.items()
        if dt_util.as_local(k).day == 20
    }
    assert len(curve) == 48
    assert local[5] == 2.0 and local[15] == 10.0
    assert 2.0 < local[10] < 10.0 and local[0] == 2.0  # held before the minimum
    assert min(local.values()) == 2.0 and max(local, key=local.get) == 15
    assert local[20] > local[23] > 4.0  # on to the next day's minimum
    first = min(curve)
    hourly = {first: 7.5}
    both = combine(hourly, curve)
    assert both[first] == 7.5
    assert len(both) == len(curve)


def test_final_check() -> None:
    """Nonsense from a module is dropped; times are put on the UTC hour."""
    when = datetime(2026, 11, 20, 10, 30, tzinfo=UTC)
    raw = {
        when: 5,
        datetime(2026, 11, 20, 11): 6,  # naive
        when + timedelta(hours=1): 99,  # not believable
    }
    assert checked_forecast(raw) == {datetime(2026, 11, 20, 10, tzinfo=UTC): 5.0}
    assert checked_forecast(None) == {}


async def test_weerlive_answer(hass: HomeAssistant) -> None:
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    payload = {
        "liveweer": [{"temp": 13.2}],
        "uur_verw": [
            {"timestamp": 1794924000, "temp": 12},
            {"timestamp": "x", "temp": 11},
        ],
        "wk_verw": [{"dag": "19-11-2026", "min_temp": 3, "max_temp": 8}],
    }
    now, forecast = parse_weerlive(payload)
    assert now == 13.2
    assert forecast[datetime.fromtimestamp(1794924000, tz=UTC)] == 12.0
    assert len(forecast) == 1 + 24  # the hour, then the whole day 19-11


def _forecast_service(hass: HomeAssistant, hourly: list, daily: list) -> None:
    async def get_forecasts(call: ServiceCall):
        kind = call.data["type"]
        items = hourly if kind == "hourly" else daily if kind == "daily" else []
        ids = call.data["entity_id"]
        ids = [ids] if isinstance(ids, str) else ids
        return {e: {"forecast": items} for e in ids}

    hass.services.async_register(
        "weather",
        "get_forecasts",
        get_forecasts,
        supports_response=SupportsResponse.ONLY,
    )


async def test_weather_entity_hourly_then_days(hass: HomeAssistant) -> None:
    """24 hours per hour, then the daily minimum/maximum as a curve."""
    start = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    hourly = [
        {"datetime": (start + timedelta(hours=i)).isoformat(), "temperature": 5.0}
        for i in range(24)
    ]
    today = dt_util.start_of_local_day()
    daily = [
        {
            "datetime": (today + timedelta(days=d)).isoformat(),
            "temperature": 9.0,
            "templow": 1.0,
        }
        for d in range(5)
    ]
    _forecast_service(hass, hourly, daily)
    hass.states.async_set(
        "weather.home", "cloudy", {"temperature": 4.0, "temperature_unit": "°C"}
    )
    source = WeatherEntitySource(WeatherSettings(entity_id="weather.home"))
    forecast = await source.async_forecast(hass)
    assert source.temperature_now(hass) == 4.0
    assert forecast[start] == 5.0
    assert max(forecast) > start + timedelta(days=3)  # beyond the hourly
    later = [v for k, v in forecast.items() if k > start + timedelta(hours=24)]
    assert min(later) == 1.0 and max(later) == 9.0


async def test_knmi_finds_its_entity(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    registry.async_get_or_create("weather", "knmi", "abc", suggested_object_id="thuis")
    hass.states.async_set("weather.thuis", "sunny", {"temperature": 7.0})
    hass.states.async_set("weather.other", "sunny", {"temperature": 20.0})
    source = KnmiWeatherSource(WeatherSettings(entity_id="weather.other"))
    assert source.temperature_now(hass) == 7.0  # not a KNMI entity: its own
    assert source.describe() == "weather.thuis"


async def test_weerlive_request(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Asks with the key and the home place (2 decimals); keeps the last
    good forecast on Weerlive's own error answer."""
    hass.config.latitude, hass.config.longitude = 52.123456, 5.654321
    aioclient_mock.get(
        WEERLIVE_URL,
        json={
            "liveweer": [{"temp": 6.5}],
            "uur_verw": [{"timestamp": 1794924000, "temp": 6}],
            "wk_verw": [],
            "api": [{"rest_verz": 250}],
        },
    )
    source = WeerliveWeatherSource(WeatherSettings(api_key="secret"))
    forecast = await source.async_forecast(hass)
    assert forecast and source.temperature_now(hass) == 6.5
    assert source.requests_left == 250
    url = aioclient_mock.mock_calls[0][1]
    assert url.query["locatie"] == "52.12,5.65" and url.query["key"] == "secret"
    assert "secret" not in source.describe()
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        WEERLIVE_URL, json={"liveweer": [{"fout": "Vraag eerst een API-key op"}]}
    )
    source._read_at = None
    assert await source.async_forecast(hass) == forecast
    assert "API-key" in source.describe()


async def test_open_meteo_knmi_request(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        OPEN_METEO_URL,
        json={
            "current": {"temperature_2m": 3.5},
            "hourly": {"time": [1794873600, 1794877200], "temperature_2m": [2.7, None]},
        },
    )
    source = OpenMeteoKnmiSource(WeatherSettings(location="52.09,5.12"))
    forecast = await source.async_forecast(hass)
    assert forecast == {datetime.fromtimestamp(1794873600, tz=UTC): 2.7}
    assert source.temperature_now(hass) == 3.5
    query = aioclient_mock.mock_calls[0][1].query
    assert query["models"] == "knmi_seamless" and query["latitude"] == "52.09"


def test_create_and_own_module(tmp_path: Path) -> None:
    """Not set up -> no source; the template loads as an own module."""
    settings = WeatherSettings()
    assert create_weather_source("weather_entity", {}, settings) is None
    assert create_weather_source("weerlive", {}, settings) is None
    assert isinstance(create_weather_source("knmi", {}, settings), KnmiWeatherSource)
    assert create_weather_source("custom_gone", {}, settings) is None
    assert set(BUILTIN) == {
        "weather_entity",
        "knmi",
        "weerlive",
        "open_meteo",
        "open_meteo_knmi",
    }
    source = (PACKAGE / "template.py").read_text(encoding="utf-8")
    (tmp_path / "mine.py").write_text(
        source.replace(
            "from .base import",
            "from custom_components.homebatteryassist.engine.sources.weather.base import",
        ),
        encoding="utf-8",
    )
    own = load_weather_sources_from(tmp_path)
    assert list(own) == ["custom_template"]
    assert create_weather_source("custom_template", own, settings) is not None
