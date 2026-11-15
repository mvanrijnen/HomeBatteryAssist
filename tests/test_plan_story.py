"""Tests for the plain-language explanation of the battery plan."""

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.explain.plan_story import plan_story
from custom_components.homebatteryassist.planning.battery_plan import (
    BatteryPlan,
    PlanSlot,
)

T0 = datetime(2026, 11, 16, 1, 0, tzinfo=dt_util.UTC)  # 02:00 local (Amsterdam)
H = timedelta(hours=1)


def _plan(powers: list[float], prices: list[float], house: float = 500.0, saving=0.5):
    slots = [
        PlanSlot(T0 + i * H, T0 + (i + 1) * H, p, 50.0, house + p, prices[i])
        for i, p in enumerate(powers)
    ]
    return BatteryPlan("arbitrage", "arbitrage", slots, 1.0, 1.0 + saving)


async def test_story_charge_now_and_use_later(hass: HomeAssistant) -> None:
    """Charging from the grid now, used later: why, what for and what it brings."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    plan = _plan([2000.0, 2000.0, -500.0, -500.0], [0.20, 0.20, 0.45, 0.45])
    nom = BatteryPlan("nom", "nom", [], 1.0, 1.0 - 0.3)
    text = plan_story(plan, {"nom": nom}, T0, "nl", 0.85, 0.02, False)
    assert text.startswith(
        "De batterijen laden nu 2.0 kW uit het net, omdat stroom nu goedkoop is (€ 0,20 per kWh)."
    )
    assert "laden we 4,0 kWh uit het net tegen € 0,20 per kWh" in text
    assert "als stroom € 0,45 per kWh kost" in text
    assert "Met nul op de meter zou het € 0,80 minder opleveren." in text


async def test_story_idle_without_gain(hass: HomeAssistant) -> None:
    """Idle: explained by the small price difference."""
    plan = _plan([0.0, 0.0], [0.30, 0.32])  # 0.32 x 0.85 - 0.02 < 0.30
    text = plan_story(plan, {}, T0, "nl", 0.85, 0.02, False)
    assert "doen nu niets" in text and "niet genoeg duurder" in text
    assert "laden niet nodig of levert het niets op" in text

    empty = plan_story(plan, {}, T0, "nl", 0.85, 0.02, True)
    assert empty.startswith(
        "De batterijen doen nu niets: ze zijn zo leeg als ingesteld"
    )


async def test_story_joins_charge_blocks(hass: HomeAssistant) -> None:
    """Two charge blocks with only a pause in between are one charge moment."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    plan = _plan(
        [0.0, 2000.0, 0.0, 2000.0, -500.0, -500.0],
        [0.30, 0.20, 0.25, 0.20, 0.45, 0.45],
    )
    text = plan_story(plan, {}, T0, "nl", 0.85, 0.02, False)
    assert "laden we 4,0 kWh uit het net" in text
    assert "als stroom € 0,45 per kWh kost" in text


async def test_story_waits_for_cheaper_power(hass: HomeAssistant) -> None:
    """Idle now because a cheaper charge moment comes later."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    plan = _plan([0.0, 2000.0, -500.0], [0.32, 0.27, 0.46])
    # Empty: waiting for cheaper power is the reason.
    text = plan_story(plan, {}, T0, "nl", 0.85, 0.02, True)
    assert text.startswith(
        "De batterijen doen nu niets: ze wachten op goedkopere stroom (€ 0,27 per kWh"
    )
    # With energy stored it keeps it for later and charges cheaper first.
    text = plan_story(plan, {}, T0, "nl", 0.85, 0.02, False)
    assert text.startswith("De batterijen leveren nu niet")


async def test_story_explains_why_not_discharging(hass: HomeAssistant) -> None:
    """Idle with energy stored: it is kept for a more expensive moment."""
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    plan = _plan([0.0, 0.0, -500.0], [0.30, 0.31, 0.46])
    text = plan_story(plan, {}, T0, "nl", 0.85, 0.02, False)
    assert text.startswith(
        "De batterijen leveren nu niet, omdat stroom nu niet duur genoeg is (€ 0,30 per kWh)"
    )
    assert "€ 0,46 per kWh kost." in text
    # ... and a cheap charge before that moment is mentioned too.
    plan = _plan([0.0, 2000.0, -500.0], [0.32, 0.27, 0.46])
    text = plan_story(plan, {}, T0, "nl", 0.85, 0.02, False)
    assert "en laden vannacht bij tegen € 0,27 per kWh" in text or (
        "bij tegen € 0,27 per kWh" in text
    )
