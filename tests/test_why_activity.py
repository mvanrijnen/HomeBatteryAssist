"""Why: what each battery (real and virtual) starts and stops doing, with the
plan's reason."""

from datetime import timedelta
from types import SimpleNamespace

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.homebatteryassist.engine.explain.plan_phases import reason_now
from custom_components.homebatteryassist.engine.planning.battery_plan import PlanSlot

from .test_batteries import NOW, _entry, _set
from .test_virtual_battery import _setup as _virtual_setup


def _latest(entry, name: str) -> dict:
    return next(
        (
            d
            for d in reversed(entry.runtime_data.decisions.entries)
            if d["category"] == "battery" and d["params"].get("name") == name
        ),
        {},
    )


async def _later(hass, freezer, minutes: int) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_real_battery_tells_the_plans_reason(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    freezer.move_to(NOW)
    entry = await _entry(hass)
    batteries = entry.runtime_data.batteries
    batteries.planned_now = lambda: -800.0
    batteries.expected_until = lambda battery_id, activity: None
    batteries.plan_reason = lambda: SimpleNamespace(
        kind="discharge",
        reason="power is expensive then (€0.42 per kWh)",
        end=NOW + timedelta(hours=2),
    )
    _set(hass, "sensor.grid", "0", "W")
    _set(hass, "sensor.marstek_soc", "50", "%")
    _set(hass, "sensor.marstek_power", "0", "W")
    await hass.async_block_till_done()
    await _later(hass, freezer, 1)
    _set(hass, "sensor.marstek_power", "800", "W")
    await hass.async_block_till_done()
    await _later(hass, freezer, 6)
    latest = _latest(entry, "Venus")
    assert latest["key"] == "battery_discharging"
    assert latest["message"].endswith(
        "That matches the plan: power is expensive then (€0.42 per kWh)."
    )
    # A real battery gets no "until" from the plan (its own control).
    assert "expected until" not in latest["message"]


async def test_virtual_battery_is_explained_with_the_plan(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    freezer.move_to(NOW)  # 13:00 local
    entry = await _virtual_setup(hass)
    batteries = entry.runtime_data.batteries
    batteries.planned_now = lambda: -800.0
    batteries.plan_reason = lambda: SimpleNamespace(
        kind="discharge",
        reason="power is expensive then (€0.42 per kWh)",
        end=NOW + timedelta(hours=2),
    )
    _set(hass, "sensor.grid", "800", "W")
    await hass.async_block_till_done()
    await _later(hass, freezer, 1)
    for _ in range(8):
        await _later(hass, freezer, 1)
    latest = _latest(entry, "Extra")
    assert latest["key"] in ("battery_discharging", "battery_now_discharging")
    assert "expected until about 15:00" in latest["message"]
    assert latest["message"].endswith(
        "That follows the plan: power is expensive then (€0.42 per kWh)."
    )

    # The plan says idle now while the simulation goes on: told as differing.
    batteries.planned_now = lambda: 0.0
    batteries.plan_reason = lambda: SimpleNamespace(
        kind="grid_only", reason="the batteries keep their energy", end=None
    )
    _set(hass, "sensor.grid", "-1500", "W")  # export: the simulation charges
    await hass.async_block_till_done()
    for _ in range(7):
        await _later(hass, freezer, 1)
    latest = _latest(entry, "Extra")
    assert latest["key"] == "battery_charging"
    assert "the simulation differs" in latest["message"]
    assert "(the batteries keep their energy)" in latest["message"]


def test_reason_now_picks_the_kind_of_now() -> None:
    start = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    hour = timedelta(hours=1)
    slots = [
        PlanSlot(start, start + hour, -800.0, 40.0, 0.0, 0.42),
        PlanSlot(start + hour, start + 2 * hour, -800.0, 30.0, 0.0, 0.42),
        PlanSlot(start + 2 * hour, start + 3 * hour, 0.0, 30.0, 500.0, 0.30),
    ]
    phase = reason_now(slots, start + timedelta(minutes=5), "arbitrage", 10.0, "en")
    assert phase.kind == "discharge" and phase.end == start + 2 * hour
    assert "expensive" in phase.reason
    later = reason_now(slots, start + 2 * hour, "arbitrage", 10.0, "en")
    assert later.kind == "grid_only"
    assert reason_now(slots, start + 5 * hour, "arbitrage") is None
