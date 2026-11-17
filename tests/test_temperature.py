"""Tests for the optional outdoor temperature in the consumption forecast."""

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.config_flow import (
    HomeBatteryAssistConfigFlow,
)
from custom_components.homebatteryassist.const import SUBENTRY_HEATING_COOLING
from custom_components.homebatteryassist.engine.forecast.consumption_forecast import (
    raw_forecast,
)
from custom_components.homebatteryassist.engine.forecast.forecasters import (
    Forecaster,
    ForecasterResult,
)
from custom_components.homebatteryassist.engine.forecast.planning_window import (
    HorizonLimit,
    PlanningWindow,
)
from custom_components.homebatteryassist.engine.forecast.temperature_effect import (
    TemperatureModel,
    fit_temperature,
    slot_temperatures,
)
from custom_components.homebatteryassist.engine.history.consumption_history import (
    ConsumptionHistory,
)
from custom_components.homebatteryassist.engine.history.temperature_import import (
    fill_temperatures,
)
from custom_components.homebatteryassist.engine.sources.weather.ha_weather_entity import (
    parse_forecast,
)

UTC = dt_util.UTC
H = timedelta(hours=1)
NOW = datetime(2026, 11, 20, 0, 0, tzinfo=UTC)


def _records(days: int, temp_of_day, power_of_temp, key: str = "avg_w") -> list:
    """Hourly records: each day one temperature, consumption from it."""
    records = []
    start = NOW - timedelta(days=days)
    for h in range(days * 24):
        when = start + h * H
        temp = temp_of_day(h // 24)
        record = {
            "start": when.isoformat(),
            "minutes": 60,
            "avg_w": 300.0,
            "coverage": 1.0,
            "temp_c": temp,
        }
        record[key] = power_of_temp(temp) + (300.0 if key == "avg_w" else 0.0)
        if key != "avg_w":
            record["avg_w"] = 300.0 + record[key]
        records.append(record)
    return records


def test_learns_heating_per_degree(hass: HomeAssistant) -> None:
    """50 W per degree below 16 °C is learned from the days."""
    records = _records(14, lambda d: 4.0 + d, lambda t: 50.0 * max(16.0 - t, 0.0))
    model = fit_temperature(records, NOW)
    assert model is not None and model.days >= 12  # whole local days
    assert abs(model.heat_w_per_deg - 50.0) < 0.5
    assert model.cool_w_per_deg == 0.0
    assert model.target == "avg_w"


def test_heating_meter_is_used(hass: HomeAssistant) -> None:
    """With a heating/cooling meter, that power is fitted."""
    records = _records(
        10, lambda d: 2.0 + d, lambda t: 80.0 * max(16.0 - t, 0.0), key="heating_w"
    )
    model = fit_temperature(records, NOW)
    assert model is not None and model.target == "heating_w"
    assert abs(model.heat_w_per_deg - 80.0) < 0.5


def test_not_enough_or_no_spread(hass: HomeAssistant) -> None:
    """Too few days, or the same weather every day: nothing learned."""
    few = _records(5, lambda d: 4.0 + d, lambda t: 50.0 * max(16.0 - t, 0.0))
    assert fit_temperature(few, NOW) is None
    flat = _records(10, lambda d: 10.0, lambda t: 50.0 * max(16.0 - t, 0.0))
    model = fit_temperature(flat, NOW)
    assert model is not None and not model.active
    assert fit_temperature([], NOW) is None


def test_effect_is_difference_with_recent_weather(hass: HomeAssistant) -> None:
    """Only the difference with what the profile already contains is added."""
    model = TemperatureModel(50.0, 0.0, 14, "avg_w", {12: 6.0}, {12: 0.0})
    noon = dt_util.as_utc(dt_util.as_local(NOW).replace(hour=12))
    assert model.effect(noon, 10.0) == 0.0  # 6 degrees, as usual
    assert model.effect(noon, 4.0) == 300.0  # 6 degrees colder than usual
    assert model.effect(noon, None) == 0.0


class _Flat(Forecaster):
    key = "flat"
    name = "Flat"

    def forecast(self, data):
        return ForecasterResult([500.0] * len(data.slots))


class _OwnTemperature(_Flat):
    key = "own_temperature"
    uses_temperature = True


def test_step_in_raw_forecast(hass: HomeAssistant) -> None:
    """The step is added after the forecaster, unless it does that itself."""
    window = PlanningWindow(NOW, NOW + 2 * H, HorizonLimit.PRICE)
    model = TemperatureModel(100.0, 0.0, 14, "avg_w", {}, {})
    temps = [6.0, None]  # 10 degrees below 16 °C; unknown
    out = raw_forecast(
        _Flat(), [], window, H, NOW, temperatures=temps, temperature=model
    )
    assert [v for _, _, v, _ in out] == [1500.0, 500.0]
    own = raw_forecast(
        _OwnTemperature(), [], window, H, NOW, temperatures=temps, temperature=model
    )
    assert [v for _, _, v, _ in own] == [500.0, 500.0]
    off = raw_forecast(_Flat(), [], window, H, NOW)
    assert [v for _, _, v, _ in off] == [500.0, 500.0]


def test_parse_weather_forecast() -> None:
    """Hourly and daily forecasts, °F converted, nonsense dropped."""
    hourly = parse_forecast(
        [
            {"datetime": "2026-11-20T10:00:00+00:00", "temperature": 5.5},
            {"datetime": "2026-11-20T11:00:00+00:00", "temperature": "x"},
            {"datetime": "2026-11-20T12:00:00+00:00", "temperature": 500},
        ],
        "hourly",
        "°C",
    )
    assert hourly == {datetime(2026, 11, 20, 10, tzinfo=UTC): 5.5}
    daily = parse_forecast(
        [{"datetime": "2026-11-20T00:00:00+00:00", "temperature": 41.0}],
        "daily",
        "°F",
    )
    assert len(daily) == 24 and abs(daily[NOW] - 5.0) < 0.01
    slots = [(NOW, NOW + H / 4), (NOW + 30 * H, NOW + 30 * H + H / 4)]
    assert slot_temperatures(slots, daily) == [daily[NOW], None]


async def test_history_records_heating_and_temperature(hass: HomeAssistant) -> None:
    """Heating power and outdoor temperature are averaged per interval."""
    history = ConsumptionHistory(hass, "test", 15)
    history.add_sample(NOW, 1000.0, heating=400.0, temperature=4.0)
    history.add_sample(NOW + timedelta(minutes=5), 1000.0, heating=100.0)
    record = history.close_interval(NOW + timedelta(minutes=15))
    assert record is not None
    assert record["heating_w"] == 200.0  # 5 min 400 W, 10 min 100 W
    assert record["temp_c"] == 4.0  # only known for 5 minutes


async def test_fill_temperatures(hass: HomeAssistant) -> None:
    """Past records get the mean of their hour; known ones are kept."""
    history = ConsumptionHistory(hass, "test", 15)
    history.records = [
        {"start": NOW.isoformat(), "minutes": 15, "avg_w": 1.0, "coverage": 1.0},
        {
            "start": (NOW + H / 4).isoformat(),
            "minutes": 15,
            "avg_w": 1.0,
            "coverage": 1.0,
            "temp_c": 9.0,
        },
    ]
    assert fill_temperatures(history, {NOW: 3.0}) == 1
    assert history.records[0]["temp_c"] == 3.0
    assert history.records[1]["temp_c"] == 9.0


def test_heating_cooling_subentry_offered(hass: HomeAssistant) -> None:
    """Heating/cooling can be added as a device."""
    types = HomeBatteryAssistConfigFlow.async_get_supported_subentry_types(None)
    assert SUBENTRY_HEATING_COOLING in types


async def test_cycle_with_weather_and_battery(hass: HomeAssistant) -> None:
    """A full forecast cycle with weather set up (and a battery, whose
    temperature derating shares the coordinator) runs without errors."""
    from homeassistant.config_entries import ConfigSubentryData
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.homebatteryassist.const import (
        CONF_INDOOR_TEMPERATURE,
        CONF_OUTDOOR_TEMPERATURE,
        CONF_WEATHER_ENTITY,
        DOMAIN,
        SUBENTRY_BATTERY,
        SUBENTRY_HEATING_COOLING,
    )

    from .test_batteries import BATTERY_INPUT, GRID

    hass.states.async_set("weather.home", "cloudy", {"temperature": 3.0})
    hass.states.async_set("sensor.airco", "800", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.room", "20.5", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.outside", "2.5", {"unit_of_measurement": "°C"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=GRID,
        options={
            "history_interval": 15,
            CONF_WEATHER_ENTITY: "weather.home",
            CONF_OUTDOOR_TEMPERATURE: "sensor.outside",
        },
        subentries_data=[
            ConfigSubentryData(
                data={**BATTERY_INPUT, "phase": "none"},
                subentry_type=SUBENTRY_BATTERY,
                title="Venus",
                unique_id="sensor.marstek_power",
            ),
            ConfigSubentryData(
                data={
                    "name": "Woonkamer",
                    "sensor": "sensor.airco",
                    "phase": "none",
                    CONF_INDOOR_TEMPERATURE: "sensor.room",
                },
                subentry_type=SUBENTRY_HEATING_COOLING,
                title="Woonkamer",
                unique_id="sensor.airco",
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    forecast = entry.runtime_data.forecast
    await forecast.async_refresh()
    await hass.async_block_till_done()
    assert forecast.last_update_success
    assert forecast.outdoor_temperature() == 2.5
    keys = [d["key"] for d in entry.runtime_data.decisions.entries]
    assert "temperature_no_forecast" in keys  # no weather service in tests
    assert [z.name for z in forecast.zones] == ["Woonkamer"]
    await hass.config_entries.async_unload(entry.entry_id)


def _zone_records(days: int, gain: float, slope: float) -> list:
    """Hourly records of one zone: 21 °C by day, 17 °C at night, the outdoor
    temperature one value per day; the zone heats ``slope`` W per degree
    below ``room - gain``."""
    from custom_components.homebatteryassist.engine.forecast.temperature_effect import (
        DAY_HOURS,
    )

    records = []
    start = dt_util.as_utc(dt_util.as_local(NOW - timedelta(days=days)).replace(hour=0))
    for h in range(days * 24):
        when = start + h * H
        local = dt_util.as_local(when)
        room = 21.0 if local.hour in DAY_HOURS else 17.0
        outdoor = float(h // 24)  # 0 .. days-1 °C
        power = slope * max(room - gain - outdoor, 0.0)
        records.append(
            {
                "start": when.isoformat(),
                "minutes": 60,
                "avg_w": 300.0 + power,
                "coverage": 1.0,
                "temp_c": outdoor + 1.0,  # the weather reads a bit warmer
                "zones": {"a": {"w": power, "in": room, "out": outdoor}},
            }
        )
    return records


def test_zone_learns_room_and_heating_point(hass: HomeAssistant) -> None:
    """A zone with a room sensor: W per degree, the gain and the room
    temperature by day and night are learned."""
    model = fit_temperature(_zone_records(24, 3.0, 60.0), NOW, "a", "Woonkamer")
    assert model is not None and model.target == "zone" and model.name == "Woonkamer"
    assert model.gain_c == 3.0
    assert abs(model.heat_w_per_deg - 60.0) < 1.0
    assert model.room_temperature(day=True) == 21.0
    assert model.room_temperature(day=False) == 17.0
    assert model.heating_point == 18.0
    # Colder than usual adds; a night slot heats less (lower room temperature).
    day = dt_util.as_utc(dt_util.as_local(NOW).replace(hour=12))
    night = dt_util.as_utc(dt_util.as_local(NOW).replace(hour=3))
    assert model.effect(day, -5.0) > model.effect(night, -5.0) > 0


def test_zones_add_up_or_fall_back_to_house(hass: HomeAssistant) -> None:
    """All zones learned: their effects add up; otherwise the house."""
    from custom_components.homebatteryassist.engine.forecast.temperature_effect import (
        ZoneModels,
        fit_effect,
    )

    records = _zone_records(24, 3.0, 60.0)
    for record in records:
        record["zones"]["b"] = dict(record["zones"]["a"])
    both = fit_effect(records, NOW, {"a": "Woonkamer", "b": "Slaapkamer"})
    assert isinstance(both, ZoneModels) and len(both.models) == 2
    noon = dt_util.as_utc(dt_util.as_local(NOW).replace(hour=12))
    single = both.models[0].effect(noon, 0.0)
    assert abs(both.effect(noon, 0.0) - 2 * single) < 1e-6
    missing = fit_effect(records, NOW, {"a": "Woonkamer", "c": "Zolder"})
    assert isinstance(missing, TemperatureModel) and missing.name == ""


async def test_history_records_zones(hass: HomeAssistant) -> None:
    """Per zone: power, room and outdoor temperature are averaged."""
    history = ConsumptionHistory(hass, "test", 15)
    history.add_sample(NOW, 1000.0, zones={"a": (400.0, 20.0, None)})
    history.add_sample(
        NOW + timedelta(minutes=5), 1000.0, zones={"a": (100.0, 21.5, 3.0)}
    )
    record = history.close_interval(NOW + timedelta(minutes=15))
    assert record is not None
    assert record["zones"] == {"a": {"w": 200.0, "in": 21.0, "out": 3.0}}


def test_heating_zone_reads_its_sensors(hass: HomeAssistant) -> None:
    """A zone reads its power and temperatures; nonsense is dropped."""
    from custom_components.homebatteryassist.engine.measure.heating_zones import (
        HeatingZone,
    )

    hass.states.async_set("sensor.airco", "-750", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.room", "70", {"unit_of_measurement": "°F"})
    hass.states.async_set("sensor.unit", "99", {"unit_of_measurement": "°C"})
    zone = HeatingZone("a", "Woonkamer", "sensor.airco", "sensor.room", "sensor.unit")
    power, indoor, outdoor = zone.read(hass)
    assert power == 750.0 and abs(indoor - 21.1) < 0.1 and outdoor is None


def test_room_temperature_per_day_of_the_week(hass: HomeAssistant) -> None:
    """Working from home on Wednesday: that day is learned on its own."""
    records = _zone_records(24, 3.0, 60.0)
    for record in records:
        local = dt_util.as_local(dt_util.parse_datetime(record["start"]))
        zone = record["zones"]["a"]
        if local.weekday() == 2 and zone["in"] == 21.0:
            zone["in"] = 22.0
    model = fit_temperature(records, NOW, "a", "Woonkamer")
    assert model is not None
    assert model.room_temperature(day=True, weekday=2) == 22.0
    assert model.room_temperature(day=True, weekday=1) == 21.0
    assert model.room(2, 12) == 22.0 and model.room(1, 12) == 21.0


def test_profile_has_no_weekend_split(hass: HomeAssistant) -> None:
    """The forecaster falls back from the weekday to the hour of all days."""
    from custom_components.homebatteryassist.engine.forecast.forecasters.weekday_hour_profile import (
        METHODS,
    )

    assert METHODS == ("weekday_hour", "hour", "overall")


def test_demand_and_room_for_the_dashboard(hass: HomeAssistant) -> None:
    """The power to expect itself (not the difference with the usual
    weather) and the learned room temperature; zones add up."""
    from custom_components.homebatteryassist.engine.forecast.temperature_effect import (
        ZoneModels,
    )

    model = TemperatureModel(
        100.0, 0.0, 14, "zone", {}, {}, gain_c=4.0, usual_indoor={1: 21.0}
    )
    start = dt_util.as_utc(dt_util.as_local(NOW).replace(hour=1))
    assert model.room_at(start) == 21.0
    assert model.demand(start, 7.0) == 1000.0  # 10 degrees below 21 - 4
    assert model.demand(start, 20.0) == 0.0
    assert model.demand(start, None) is None
    house = TemperatureModel(50.0, 0.0, 14, "avg_w", {}, {})
    assert house.room_at(start) is None
    both = ZoneModels((model, house))
    assert both.demand(start, 7.0) == 1000.0 + 50.0 * 9.0  # house: 20 - 4 - 7
    assert both.room_at(start) == 21.0
