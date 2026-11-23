"""Block tariff: fixed prices per time block as a price source."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist.config_flow import settings_errors
from custom_components.homebatteryassist.const import DOMAIN
from custom_components.homebatteryassist.engine.sources.prices import (
    ROLE_IMPORT,
    get_driver,
)
from custom_components.homebatteryassist.engine.sources.prices.block_tariff import (
    BlockError,
    block_prices,
    parse_blocks,
)

TEXT = """0,30
23:00-07:00 0,22
ma-vr 17:00-21:00 0.40
sat,sun 11:00-15:00 0,18"""


@pytest.fixture(autouse=True)
def amsterdam():
    old = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(dt_util.get_time_zone("Europe/Amsterdam"))
    yield
    dt_util.set_default_time_zone(old)


def _price_at(points, when):
    utc = dt_util.as_utc(when)
    return next((p.price for p in points if p.start <= utc < p.end), None)


def test_rules_and_overlaps():
    blocks = parse_blocks(TEXT)
    tz = dt_util.get_default_time_zone()
    monday = datetime(2026, 11, 23, tzinfo=tz)
    points = block_prices(blocks, monday, monday + timedelta(days=7))
    assert _price_at(points, monday.replace(hour=3)) == 0.22  # night
    assert _price_at(points, monday.replace(hour=23, minute=30)) == 0.22
    assert _price_at(points, monday.replace(hour=12)) == 0.30  # rest
    assert _price_at(points, monday.replace(hour=18)) == 0.40  # working day
    saturday = monday + timedelta(days=5)
    assert _price_at(points, saturday.replace(hour=18)) == 0.30
    assert _price_at(points, saturday.replace(hour=12)) == 0.18
    # Past midnight on Sunday night: Monday morning is night too.
    assert _price_at(points, (monday + timedelta(days=7)).replace(hour=0)) is None
    # Neighbours with the same price are one point.
    assert len(points) < 7 * 24


def test_no_rule_means_no_price():
    tz = dt_util.get_default_time_zone()
    monday = datetime(2026, 11, 23, tzinfo=tz)
    points = block_prices(
        parse_blocks("07:00-09:00 0,40"), monday, monday + timedelta(days=1)
    )
    assert len(points) == 1
    assert _price_at(points, monday.replace(hour=8)) == 0.40
    assert _price_at(points, monday.replace(hour=10)) is None


def test_whole_day_and_comments():
    blocks = parse_blocks("# winter\nza 00:00-24:00 0,10; 0,30")
    tz = dt_util.get_default_time_zone()
    saturday = datetime(2026, 11, 28, tzinfo=tz)
    points = block_prices(blocks, saturday, saturday + timedelta(days=2))
    assert _price_at(points, saturday.replace(hour=12)) == 0.30  # later wins
    assert parse_blocks("0,30; za 00:00-24:00 0,10")[1].start is None


@pytest.mark.parametrize(
    "text",
    ["17:00-21:00", "mon-xx 17:00 0,4", "25:00-26:00 0,3", "08:00-08:00 0,3", "abc"],
)
def test_unreadable_rules(text):
    with pytest.raises(BlockError):
        parse_blocks(text)


async def test_driver_reads_the_setting(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, options={"price_blocks": TEXT}).add_to_hass(hass)
    driver = get_driver("blocks")
    assert driver is not None and not driver.verified
    [source] = driver.find(hass)
    data = await driver.async_read(hass, source.id, ROLE_IMPORT)
    assert data.points and data.unit.endswith("/kWh")
    assert not any(p.estimated for p in data.points)
    assert data.points[-1].end - data.points[0].start >= timedelta(days=7)


async def test_settings_errors(hass: HomeAssistant) -> None:
    assert await settings_errors(hass, {"price_blocks": TEXT}) == {}
    assert (await settings_errors(hass, {"price_blocks": "x"}))[
        "price_blocks"
    ] == "price_blocks_invalid"
    assert (await settings_errors(hass, {"price_source": "blocks:settings"}))[
        "price_blocks"
    ] == "price_blocks_missing"
