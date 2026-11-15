"""Tests for the price drivers."""

from datetime import timedelta

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist.inputs.price_drivers import (
    DRIVERS,
    ROLE_IMPORT,
    ROLE_MARKET,
    find_sources,
    split_key,
)
from custom_components.homebatteryassist.inputs.price_drivers.actions import (
    EnergyZeroDriver,
    points_from,
)
from custom_components.homebatteryassist.inputs.price_drivers.template import (
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
    """All-in prices and bare market prices (published + forecast)."""
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
            {"prices": [[ms + i * hour, 0.10] for i in range(48)]},
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
    assert source.roles == {ROLE_IMPORT, ROLE_MARKET}
    driver, source_id = split_key(source.key)
    data = await driver.async_read(hass, source_id, ROLE_IMPORT)
    assert len(data.points) == 49 and data.points[-1].estimated
    assert data.unit == "€/kWh"
    market = await driver.async_read(hass, source_id, ROLE_MARKET)
    assert [p.price for p in market.points[-2:]] == [0.10, 0.20]
    assert set(driver.watch(hass, source_id)) == {"sensor.forecast", "sensor.market"}


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
