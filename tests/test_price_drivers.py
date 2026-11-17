"""Tests for the price drivers."""

from datetime import timedelta

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist.engine.sources.prices import (
    DRIVERS,
    ROLE_EXPORT,
    ROLE_IMPORT,
    ROLE_MARKET,
    find_sources,
    split_key,
)
from custom_components.homebatteryassist.engine.sources.prices.ha_price_actions import (
    EnergyZeroDriver,
    points_from,
)
from custom_components.homebatteryassist.engine.sources.prices.template import (
    TemplatePriceDriver,
)


def test_template_is_not_offered() -> None:
    """The template is a code example only."""
    assert not any(isinstance(d, TemplatePriceDriver) for d in DRIVERS)
    assert len({d.key for d in DRIVERS}) == len(DRIVERS)


def test_points_from() -> None:
    hour = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    points = points_from(
        [
            ((hour + timedelta(hours=1)).isoformat(), None, 200.0),
            (hour.isoformat(), None, 100.0),
        ],
        1 / 1000,
    )
    assert [(p.start, p.end, p.price) for p in points] == [
        (hour, hour + timedelta(hours=1), 0.1),
        (hour + timedelta(hours=1), hour + timedelta(hours=2), 0.2),
    ]


async def test_dyntarnl_driver(hass: HomeAssistant) -> None:
    """All-in, bare market (published + forecast) and export prices."""
    entry = MockConfigEntry(domain="dyntarnl", title="Essent")
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    ms = int(dt_util.start_of_local_day().timestamp() * 1000)
    hour = 3600_000
    for suffix, object_id, attrs in (
        (
            "_electricity_forecast_total_avg_24h",
            "forecast",
            {
                "prices": [[ms + i * hour, 0.30 + i / 100, "p"] for i in range(48)]
                + [[ms + 48 * hour, 0.40, "f"]],
                "forecast_market": [[ms + 48 * hour, 0.20]],
            },
        ),
        (
            "_electricity_market_market_current",
            "market",
            {
                "prices": [[ms + i * hour, 0.10] for i in range(48)],
                "purchase_fee": 0.025,
            },
        ),
    ):
        registry.async_get_or_create(
            "sensor",
            "dyntarnl",
            f"x{suffix}",
            config_entry=entry,
            suggested_object_id=object_id,
        )
        hass.states.async_set(
            f"sensor.{object_id}", "0.3", {"unit_of_measurement": "€/kWh", **attrs}
        )
    (source,) = [s for s in find_sources(hass) if s.driver == "dyntarnl"]
    assert source.roles == {ROLE_IMPORT, ROLE_MARKET, ROLE_EXPORT}
    driver, source_id = split_key(source.key)
    data = await driver.async_read(hass, source_id, ROLE_IMPORT)
    assert len(data.points) == 49 and data.points[-1].estimated
    assert data.unit == "€/kWh"
    market = await driver.async_read(hass, source_id, ROLE_MARKET)
    assert [p.price for p in market.points[-2:]] == [0.10, 0.20]
    # Export: the market price minus the purchase fee (Essent).
    export = await driver.async_read(hass, source_id, ROLE_EXPORT)
    assert [p.price for p in export.points[-2:]] == [0.075, 0.175]
    assert set(driver.watch(hass, source_id)) == {"sensor.forecast", "sensor.market"}


async def test_dyntarnl_export_series(hass: HomeAssistant) -> None:
    """DynTarNL >= 1.2.0: published export prices, then forecast_export after
    the last published hour; negative prices kept; older versions (no
    ``prices`` on the export sensor) fall back to market minus the fee."""
    entry = MockConfigEntry(domain="dyntarnl", title="Essent")
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    ms = int(dt_util.start_of_local_day().timestamp() * 1000)
    hour = 3600_000
    states = {
        "_electricity_forecast_total_avg_24h": (
            "forecast",
            {
                "prices": [[ms + i * hour, 0.30, "p"] for i in range(4)],
                # overlaps the last published hour, then a gap, then more
                "forecast_export": [
                    [ms + 3 * hour, 0.99],
                    [ms + 4 * hour, 0.05],
                    [ms + 6 * hour, 0.07],
                ],
            },
        ),
        "_electricity_market_market_current": (
            "market",
            {
                "prices": [[ms + i * hour, 0.10] for i in range(4)],
                "purchase_fee": 0.025,
            },
        ),
        "_electricity_feedin_compensation_now": (
            "export",
            {
                "prices": [
                    [ms, 0.075],
                    [ms + hour, -0.04],
                    [ms + 2 * hour, 0.075],
                    [ms + 3 * hour, 0.075],
                ]
            },
        ),
    }
    for suffix, (object_id, attrs) in states.items():
        registry.async_get_or_create(
            "sensor",
            "dyntarnl",
            f"x{suffix}",
            config_entry=entry,
            suggested_object_id=object_id,
        )
        hass.states.async_set(
            f"sensor.{object_id}", "0.1", {"unit_of_measurement": "€/kWh", **attrs}
        )
    (source,) = [s for s in find_sources(hass) if s.driver == "dyntarnl"]
    driver, source_id = split_key(source.key)
    export = (await driver.async_read(hass, source_id, ROLE_EXPORT)).points
    assert [p.price for p in export] == [0.075, -0.04, 0.075, 0.075, 0.05, 0.07]
    assert [p.estimated for p in export] == [False] * 4 + [True] * 2
    assert "sensor.export" in driver.watch(hass, source_id)

    # Empty forecast_export: only the published series.
    attrs = dict(hass.states.get("sensor.forecast").attributes, forecast_export=[])
    hass.states.async_set("sensor.forecast", "0.1", attrs)
    export = (await driver.async_read(hass, source_id, ROLE_EXPORT)).points
    assert [p.price for p in export] == [0.075, -0.04, 0.075, 0.075]

    # Older DynTarNL / no data: no prices on the export sensor -> calculated.
    for state in ("0.1", "unknown"):
        hass.states.async_set("sensor.export", state, {})
        export = (await driver.async_read(hass, source_id, ROLE_EXPORT)).points
        assert [p.price for p in export] == [0.075] * 4


async def test_action_driver(hass: HomeAssistant) -> None:
    """Prices from a core integration's action response (EnergyZero)."""
    entry = MockConfigEntry(domain="energyzero", title="EnergyZero")
    entry.add_to_hass(hass)
    start = dt_util.start_of_local_day()

    async def get_prices(call: ServiceCall):
        assert call.data["config_entry"] == entry.entry_id
        return {
            "prices": [
                {"timestamp": (start + timedelta(hours=i)).isoformat(), "price": 0.2}
                for i in range(48)
            ]
        }

    hass.services.async_register(
        "energyzero",
        "get_energy_prices",
        get_prices,
        supports_response=SupportsResponse.ONLY,
    )
    data = await EnergyZeroDriver().async_read(hass, entry.entry_id, ROLE_IMPORT)
    assert len(data.points) == 48 and data.points[0].price == 0.2


def test_calibrate_forecast_to_real_prices() -> None:
    """A bare forecast is lifted to the level of the real (all-in) prices."""
    from custom_components.homebatteryassist.engine.sources.prices.price_points import (
        PricePoint,
        calibrate,
    )

    start = dt_util.start_of_local_day()
    h = timedelta(hours=1)
    bare = [
        PricePoint(start + i * h, start + (i + 1) * h, 0.05 + i / 100)
        for i in range(30)
    ]
    real = [  # all-in = 1.21 x bare + 0.13 for the first 24 hours
        PricePoint(p.start, p.end, round(1.21 * p.price + 0.13, 5)) for p in bare[:24]
    ]
    result = calibrate(bare, real)
    assert result[29].estimated
    assert abs(result[29].price - (1.21 * bare[29].price + 0.13)) < 0.001


async def test_forecast_only_sources(hass: HomeAssistant) -> None:
    """EpexPredictor is offered for NL, as forecast only."""
    await hass.config.async_update(country="NL")
    sources = [s for s in find_sources(hass) if s.driver == "epexpredictor"]
    assert len(sources) == 1 and sources[0].forecast_only
    await hass.config.async_update(country="FR")
    assert not [s for s in find_sources(hass) if s.driver == "epexpredictor"]


def test_epexpredictor_parse() -> None:
    from custom_components.homebatteryassist.engine.sources.prices.price_forecasts import (
        EpexPredictorDriver,
    )

    data = EpexPredictorDriver().parse(
        {
            "prices": [
                {"startsAt": "2026-11-16T01:15:00+01:00", "total": 0.1218},
                {"startsAt": "2026-11-16T01:30:00+01:00", "total": 0.1189},
            ],
            "knownUntil": "2026-11-17T00:00:00+01:00",
        }
    )
    assert [p.price for p in data.points] == [0.1218, 0.1189]
    assert data.points[0].end == data.points[1].start


async def test_pvpc_and_amber_formats(hass: HomeAssistant) -> None:
    """PVPC hourly attributes and Amber's forecasts list."""
    from homeassistant.core import State

    from custom_components.homebatteryassist.engine.sources.prices.price_points import (
        parse_price_forecast,
    )
    from custom_components.homebatteryassist.engine.sources.prices.regional import (
        pvpc_points,
    )

    points = pvpc_points(
        {"price_00h": 0.10, "price_01h": 0.12, "price_next_day_00h": 0.09, "x": 1}
    )
    assert [p.price for p in points] == [0.10, 0.12, 0.09]
    assert points[2].start - points[0].start == timedelta(days=1)
    start = dt_util.start_of_local_day()
    amber = State(
        "sensor.amber_general_price",
        "0.3",
        {
            "forecasts": [
                {
                    "start_time": start.isoformat(),
                    "end_time": (start + timedelta(minutes=30)).isoformat(),
                    "per_kwh": 0.31,
                }
            ]
        },
    )
    (point,) = parse_price_forecast(amber)
    assert point.price == 0.31 and point.end - point.start == timedelta(minutes=30)
