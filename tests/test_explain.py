"""Tests for the decision log ("why" logging) and the last decision sensor."""

from datetime import datetime

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.homebatteryassist.const import (
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_PHASES,
    DOMAIN,
)
from custom_components.homebatteryassist.engine.explain import DecisionLog
from custom_components.homebatteryassist.engine.explain.decision_log import (
    EVENT_DECISION,
    MAX_ENTRIES,
)
from custom_components.homebatteryassist.engine.explain.messages import (
    KIND_NAMES,
    MESSAGES,
    TERMS,
    render,
)


def test_all_languages_have_all_messages() -> None:
    """Every explanation exists in every language."""
    keys = set(MESSAGES["en"])
    for language, messages in MESSAGES.items():
        assert set(messages) == keys, language


def test_all_languages_have_all_terms() -> None:
    """Phrases filled into messages and forecast kind names exist in every language."""
    for table in (TERMS, KIND_NAMES):
        keys = {lang: set(texts) for lang, texts in table.items()}
        assert keys["nl"] == keys["en"]


def test_render_terms() -> None:
    """A "@term" parameter is replaced by the phrase, filled from the others."""
    text = render(
        "nl",
        "battery_charging",
        {
            "name": "Venus",
            "since": "13:00",
            "extra": "@src_pv",
            "until": "@until_full",
            "time": "15:30",
            "plan": "@plan_same",
        },
    )
    assert text == (
        "Venus laadt sinds 13:00 met zonnestroom die anders naar het net zou gaan, "
        "naar verwachting tot ongeveer 15:30, dan is hij vol. Dat klopt met het plan."
    )


def test_render() -> None:
    """Placeholders are filled; unknown language falls back to English."""
    end = datetime(2026, 11, 16, 12, 0, tzinfo=dt_util.UTC)
    assert render("nl", "consumption_unavailable", {"sensors": "sensor.l1"}) == (
        "Huisverbruik onbekend: geen geldige meting van sensor.l1."
    )
    assert render("de", "consumption_restored", {}) == (
        "House consumption is measured again."
    )
    assert render("en", "horizon_price", {"end": end, "hours": 30}).startswith(
        "Planning 30 hours ahead (until 16-11"
    )
    assert render("en", "unknown_key", {}) == "unknown_key"


async def test_decision_log(hass: HomeAssistant) -> None:
    """Decisions are explained, fired as event, capped and persisted."""
    events = async_capture_events(hass, EVENT_DECISION)
    log = DecisionLog(hass, "test")

    decision = log.async_log(
        "measurement", "consumption_unavailable", sensors="sensor.l1"
    )
    await hass.async_block_till_done()
    assert decision["message"] == (
        "House consumption unknown: no valid measurement from sensor.l1."
    )
    assert log.latest == decision
    assert events[0].data["key"] == "consumption_unavailable"

    for _ in range(MAX_ENTRIES + 5):
        log.async_log("measurement", "consumption_restored")
    assert len(log.entries) == MAX_ENTRIES

    await log.async_save()
    reloaded = DecisionLog(hass, "test")
    await reloaded.async_load()
    assert reloaded.entries == log.entries


@pytest.mark.parametrize("language", ["nl"])
async def test_consumption_availability_is_explained(
    hass: HomeAssistant, language: str
) -> None:
    """Losing and regaining the grid measurement is explained (not at start-up)."""
    hass.config.language = language
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.l1"},
        options={CONF_HISTORY_INTERVAL: 15},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    decisions = entry.runtime_data.decisions
    # The entity id follows the (Dutch) name, so look it up by unique id.
    last_decision = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_last_decision"
    )
    assert last_decision == "sensor.homebatteryassist_laatste_beslissing"
    start_keys = [d["key"] for d in decisions.entries]

    # Becoming available for the first time is not a notable change.
    hass.states.async_set("sensor.l1", "500", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert [d["key"] for d in decisions.entries] == start_keys

    # A gap in the first minutes after a start is no message (sensors of
    # other integrations are often still starting).
    hass.states.async_set("sensor.l1", "unavailable")
    await hass.async_block_till_done()
    assert [d["key"] for d in decisions.entries] == start_keys
    hass.states.async_set("sensor.l1", "500", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert [d["key"] for d in decisions.entries] == start_keys

    entry.runtime_data.measurements._quiet_until = dt_util.utcnow()
    hass.states.async_set("sensor.l1", "unavailable")
    await hass.async_block_till_done()
    assert decisions.latest["key"] == "consumption_unavailable"
    assert hass.states.get(last_decision).state == (
        "Huisverbruik onbekend: geen geldige meting van sensor.l1."
    )

    hass.states.async_set("sensor.l1", "400", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    state = hass.states.get(last_decision)
    assert state.state == "Huisverbruik wordt weer gemeten."
    assert state.attributes["category"] == "measurement"
    assert state.attributes["recent"][1]["message"].startswith("Huisverbruik onbekend")


async def test_notifications(hass: HomeAssistant) -> None:
    """Chosen kinds of decisions go to the chosen notify services."""
    from homeassistant.core import ServiceCall

    from custom_components.homebatteryassist.engine.explain import DecisionLog
    from custom_components.homebatteryassist.engine.explain.notifications import (
        Notifier,
        kind_of,
    )

    assert kind_of("horizon_price") == "prices"
    assert kind_of("phase_relief") == "protection"
    assert kind_of("battery_switch") is None

    sent: list[ServiceCall] = []

    async def capture(call: ServiceCall) -> None:
        sent.append(call)

    hass.services.async_register("notify", "phone", capture)
    log = DecisionLog(hass, "test")
    log.notifier = Notifier(hass, ["phone"], ["protection"])
    log.async_log(
        "battery",
        "phase_relief",
        names="V1",
        action="ontladen",
        power="1 kW",
        phase="L1",
        current="26",
        limit="22.5",
    )
    log.async_log("measurement", "consumption_restored")  # not chosen
    await hass.async_block_till_done()
    assert len(sent) == 1
    assert sent[0].data["title"] == "HomeBatteryAssist"
    assert "L1" in sent[0].data["message"]
