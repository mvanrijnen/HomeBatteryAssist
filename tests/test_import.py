"""Tests for importing past consumption from Home Assistant's statistics."""

from datetime import datetime, timedelta
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist.const import (
    CONF_CAPACITY,
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_CURRENT,
    CONF_MAX_DISCHARGE_POWER,
    CONF_PHASE,
    CONF_PHASES,
    CONF_POWER_SENSOR,
    CONF_POWER_SIGN,
    CONF_SENSOR,
    CONF_SOC_SENSOR,
    DOMAIN,
    SUBENTRY_BATTERY,
    SUBENTRY_PV_SOURCE,
)
from custom_components.homebatteryassist.engine.history.consumption import (
    ConsumptionHistory,
    ConsumptionRecord,
)
from custom_components.homebatteryassist.engine.history.importer import (
    SOURCE_IMPORT,
    Term,
    combine,
    merge,
    to_records,
)

NOW = datetime(2026, 11, 15, 18, 2, tzinfo=dt_util.UTC)
H = timedelta(hours=1)
M5 = timedelta(minutes=5)
FETCH = "custom_components.homebatteryassist.engine.history.importer._async_fetch"


def test_combine_formula() -> None:
    """Grid + PV - battery (+ discharging sensor); no grid value -> skipped."""
    t0 = NOW - 2 * H
    terms = [
        Term("grid", 1.0, required=True),
        Term("pv", 1.0, absolute=True),
        Term("bat_old", 1.0),
        Term("bat_new", 1.0),
    ]
    series = {
        "grid": {t0: 500.0, t0 + H: -300.0},
        "pv": {t0: 0.0, t0 + H: 2000.0, t0 + 2 * H: 1000.0},
        "bat_old": {t0: 400.0},  # discharging 400 W (older sensor)
        "bat_new": {t0 + H: -1000.0},  # charging 1000 W
    }
    result = combine(terms, series, [t0, t0 + H, t0 + 2 * H])
    assert result == {t0: 900.0, t0 + H: 700.0}  # t0+2H: no grid value


def test_to_records_groups_and_coverage() -> None:
    """5-minute values become 15-minute records; hourly stays hourly."""
    t0 = datetime(2026, 11, 15, 12, 0, tzinfo=dt_util.UTC)
    values = {t0: 100.0, t0 + M5: 200.0, t0 + 3 * M5: 400.0}  # 3rd slot missing
    records = to_records(values, M5, 15)
    assert records == [
        {
            "start": t0.isoformat(),
            "minutes": 15,
            "avg_w": 150.0,
            "coverage": 0.667,
            "source": "import",
        },
        {
            "start": (t0 + 3 * M5).isoformat(),
            "minutes": 15,
            "avg_w": 400.0,
            "coverage": 0.333,
            "source": "import",
        },
    ]
    with_ev = to_records({t0: 100.0, t0 + M5: 100.0}, M5, 15, {t0 + M5: 4000.0})
    assert with_ev[0]["excluded_w"] == 2000.0
    hourly = to_records({t0: 300.0}, H, 15)
    assert hourly[0]["minutes"] == 60
    assert hourly[0]["coverage"] == 1.0


def _record(
    start: datetime, minutes: int, avg: float, source: str | None = None
) -> ConsumptionRecord:
    record = ConsumptionRecord(
        start=start.isoformat(), minutes=minutes, avg_w=avg, coverage=1.0
    )
    if source:
        record["source"] = source
    return record


async def test_merge_keeps_own_measurements(hass: HomeAssistant) -> None:
    """Own records win; earlier imports are replaced; replace=True overrides."""
    t0 = datetime(2026, 11, 15, 12, 0, tzinfo=dt_util.UTC)
    history = ConsumptionHistory(hass, "test", 15)
    own = _record(t0 + H, 15, 999.0)
    history.records = [_record(t0, 15, 1.0, SOURCE_IMPORT), own]
    imported = [
        _record(t0, 60, 100.0, SOURCE_IMPORT),
        _record(t0 + H, 60, 200.0, SOURCE_IMPORT),
    ]

    assert merge(history, imported, replace=False) == (1, 1)
    assert [(r["start"], r["avg_w"]) for r in history.records] == [
        (t0.isoformat(), 100.0),
        ((t0 + H).isoformat(), 999.0),
    ]

    history.records = [own]
    assert merge(history, imported, replace=True) == (2, 1)
    assert [r["avg_w"] for r in history.records] == [100.0, 200.0]


async def test_import_history_action(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The action reconstructs consumption from the configured sensors."""
    freezer.move_to(NOW)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.grid"},
        options={CONF_HISTORY_INTERVAL: 15},
        subentries_data=[
            ConfigSubentryData(
                data={CONF_NAME: "SMA", CONF_SENSOR: "sensor.pv", CONF_PHASE: "none"},
                subentry_type=SUBENTRY_PV_SOURCE,
                title="SMA",
                unique_id="sensor.pv",
            ),
            ConfigSubentryData(
                data={
                    CONF_NAME: "Venus",
                    CONF_SOC_SENSOR: "sensor.soc",
                    CONF_POWER_SENSOR: "sensor.bat",
                    CONF_POWER_SIGN: "discharging_positive",
                    CONF_CAPACITY: 5.12,
                    CONF_MAX_CHARGE_POWER: 2500,
                    CONF_MAX_DISCHARGE_POWER: 2500,
                },
                subentry_type=SUBENTRY_BATTERY,
                title="Venus",
                unique_id="sensor.bat",
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    old = dt_util.parse_datetime("2026-11-01T10:00:00+00:00")
    recent = dt_util.parse_datetime("2026-11-15T17:00:00+00:00")
    calls = []

    async def fake_fetch(hass, entity_ids, start, end, period):
        calls.append((period, set(entity_ids)))
        if period == "hour":
            return {"sensor.grid": {old: 800.0}, "sensor.pv": {old: 500.0}}
        return {
            "sensor.grid": {recent: 300.0, recent + M5: 300.0, recent + 2 * M5: 300.0},
            "sensor.bat_old": {
                recent: 200.0,
                recent + M5: 200.0,
                recent + 2 * M5: 200.0,
            },
        }

    with patch(FETCH, side_effect=fake_fetch):
        response = await hass.services.async_call(
            DOMAIN,
            "import_history",
            {"days": 28, "battery_power_history": ["sensor.bat_old"]},
            blocking=True,
            return_response=True,
        )

    assert response["imported"] == 2
    assert response["sensors"] == [
        "sensor.bat",
        "sensor.bat_old",
        "sensor.grid",
        "sensor.pv",
    ]
    assert [p for p, _ in calls] == ["hour", "5minute"]
    records = [
        r for r in entry.runtime_data.history.records if r.get("source") == "import"
    ]
    assert [(r["start"], r["minutes"], r["avg_w"]) for r in records] == [
        (old.isoformat(), 60, 1300.0),  # grid 800 + PV 500
        (recent.isoformat(), 15, 500.0),  # grid 300 + discharging 200
    ]
    assert entry.runtime_data.decisions.latest["key"] == "history_imported"
    # PV and battery (+ charging) are kept alongside.
    assert records[0]["pv_w"] == 500.0
    assert records[1]["battery_w"] == -200.0  # the old sensor reported discharging


async def test_import_from_source_entity(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A ready-made consumption sensor is taken over as is."""
    freezer.move_to(NOW)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.grid"},
        options={CONF_HISTORY_INTERVAL: 60},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    recent = dt_util.parse_datetime("2026-11-15T16:00:00+00:00")

    async def fake_fetch(hass, entity_ids, start, end, period):
        assert entity_ids == {"sensor.omnibattery_home_consumption"}
        if period == "hour":
            return {}
        return {
            "sensor.omnibattery_home_consumption": {
                recent + i * M5: 600.0 for i in range(12)
            }
        }

    with patch(FETCH, side_effect=fake_fetch):
        response = await hass.services.async_call(
            DOMAIN,
            "import_history",
            {"days": 3, "source_entity": "sensor.omnibattery_home_consumption"},
            blocking=True,
            return_response=True,
        )
    assert response["imported"] == 1
    (record,) = entry.runtime_data.history.records
    assert (record["minutes"], record["avg_w"], record["coverage"]) == (60, 600.0, 1.0)
