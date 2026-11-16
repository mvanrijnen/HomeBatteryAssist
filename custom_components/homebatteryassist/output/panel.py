"""Status dashboard: a sidebar panel plus the websocket command it reads.

The panel (``frontend/panel.js``) asks ``homebatteryassist/status`` which
entities and batteries exist, then shows their live states from ``hass.states``.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from ..const import DOMAIN, NAME, NOMINAL_VOLTAGE
from ..forecasts.accuracy import BUCKET_KEYS, KINDS
from ..history.profile import day_profile, days_covered, hourly_series, week_profiles
from ..inputs.battery_drivers import telemetry as battery_telemetry
from ..inputs.direct import SOURCE_NAMES, find_direct_meters
from ..inputs.measurements import MeasurementInput
from ..inputs.meters import find_meter_candidates
from ..models import HomeBatteryAssistConfigEntry
from ..planning.battery_plan import (
    ARBITRAGE_MODES,
    MODE_ARBITRAGE,
    MODE_NOM,
    compare_modes,
    reach_times,
)
from ..planning.phase_limit import phase_limit_w
from ..planning.verification import slot_saving
from .batteries import BATTERY_SENSORS, TOTAL_SENSORS

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = DOMAIN
PANEL_COMPONENT = "homebatteryassist-panel"
STATIC_URL = f"/{DOMAIN}_static"
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
DATA_REGISTERED = f"{DOMAIN}_panel_registered"
RECENT_DECISIONS = 10

MAIN_KEYS = (
    "house_consumption",
    "grid_power",
    "grid_import_power",
    "grid_export_power",
    "pv_power",
    "excluded_power",
    "planning_horizon",
    "last_decision",
    "phase_l1_load",
    "phase_l2_load",
    "phase_l3_load",
    *(d.key for d in TOTAL_SENSORS),
)


async def async_setup_panel(hass: HomeAssistant, version: str) -> None:
    """Register the websocket command and, if the frontend runs, the panel."""
    if hass.data.get(DATA_REGISTERED):
        return
    websocket_api.async_register_command(hass, websocket_status)
    websocket_api.async_register_command(hass, websocket_history)
    if "frontend" in hass.config.components:
        from homeassistant.components import panel_custom
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
        )
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=PANEL_COMPONENT,
            sidebar_title=NAME,
            sidebar_icon="mdi:home-battery-outline",
            module_url=f"{STATIC_URL}/panel.js?v={version}",
            require_admin=False,
        )
        _LOGGER.debug("Status panel registered")
    hass.data[DATA_REGISTERED] = True


def _entity_ids(registry: er.EntityRegistry, prefix: str, keys: Any) -> dict[str, str]:
    ids = {}
    for key in keys:
        if entity_id := registry.async_get_entity_id(
            "sensor", DOMAIN, f"{prefix}_{key}"
        ):
            ids[key] = entity_id
    return ids


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _expected_reach(data: Any, battery_id: str) -> dict[str, str | None]:
    """When the battery is expected to be empty / full: following the selected
    plan, and (if that is another mode) at zero on the meter — the usual own
    control of a home battery. Only for a single battery: the plans pool all
    batteries."""
    states = [s for s in data.batteries.states.values() if s.available]
    if len(states) != 1 or states[0].config.id != battery_id:
        return {}
    state = states[0]
    config = state.config
    floor = min(max(config.min_soc, data.forecast.rules.reserve_soc), config.max_soc)
    forecast = data.forecast.data
    result: dict[str, str | None] = {}
    modes = {"expected": forecast.plan_mode}
    if forecast.plan_mode != MODE_NOM:
        modes["nom"] = MODE_NOM
    for prefix, mode in modes.items():
        plan = forecast.plans.get(mode)
        if plan is None:
            continue
        empty, full = reach_times(plan.slots, state.soc, floor, config.max_soc)
        result[f"{prefix}_empty"] = empty.isoformat() if empty else None
        result[f"{prefix}_full"] = full.isoformat() if full else None
    return result


def _meter_info(hass: HomeAssistant, measurements: MeasurementInput) -> dict[str, Any]:
    """Which grid meter is used: brand/type, how it is read, its address."""
    if measurements.direct is not None:
        name = next(
            (
                c.name
                for c in find_direct_meters(hass)
                if c.source == measurements.source
                and c.address == measurements.direct.address
            ),
            SOURCE_NAMES.get(measurements.source, measurements.source),
        )
        return {
            "name": name,
            "direct": True,
            "address": measurements.direct.address,
        }
    sensors = {main for main, _ in measurements.grid_phases}
    meter = next(
        (c for c in find_meter_candidates(hass) if set(c.sensors.values()) == sensors),
        None,
    )
    return {
        "name": f"{meter.profile.label}" if meter else None,
        "direct": False,
        "address": meter.address if meter else None,
    }


def _protection(data: Any) -> dict[str, Any] | None:
    sim = data.simulator
    if sim is None:
        return None
    return {
        "relief": {f"L{i + 1}": round(w) for i, w in sim.relief_now.items()},
        "limited": [f"L{i + 1}" for i in sim.limited_phases],
        "peak_w": round(sim.peak_now),
        "peak_limit_w": data.forecast.peak_w,
    }


def _vs_none(forecast: Any) -> list[list[float]]:
    plan = forecast.data.plans.get(forecast.data.plan_mode)
    if plan is None or not plan.slots or plan.cost is None:
        return []
    start_soc = plan.slots[0].soc
    total = 0.0
    series = []
    for slot in plan.slots:
        total += slot_saving(slot, forecast.export_factor, forecast.cycle_cost) or 0.0
        stored = (slot.soc - start_soc) / 100 * plan.capacity_kwh * plan.value_per_kwh
        series.append([int(slot.start.timestamp() * 1000), round(total + stored, 4)])
    return series


def _prices_now(hass: HomeAssistant, data: Any) -> dict[str, Any] | None:
    """The current and the next power price, and what export earns now."""
    forecast = data.forecast.data
    if not forecast.prices:
        return None
    now = dt_util.utcnow()
    current = next((p for p in forecast.prices if p.start <= now < p.end), None)
    if current is None:
        return None
    upcoming = next(
        (
            p
            for p in forecast.prices
            if p.start >= current.end and round(p.price, 4) != round(current.price, 4)
        ),
        None,
    )
    plan = forecast.plans.get(forecast.plan_mode)
    slot = next(
        (s for s in (plan.slots if plan else []) if s.start <= now < s.end), None
    )
    return {
        "unit": forecast.price_unit,
        "currency": hass.config.currency,
        "now": current.price,
        "now_estimated": current.estimated,
        "until": current.end.isoformat(),
        "next": upcoming.price if upcoming else None,
        "next_start": upcoming.start.isoformat() if upcoming else None,
        "next_estimated": upcoming.estimated if upcoming else False,
        "export_now": slot.export_price if slot else None,
    }


def status(hass: HomeAssistant, entry: HomeBatteryAssistConfigEntry) -> dict[str, Any]:
    """Everything the panel needs besides live entity states."""
    data = entry.runtime_data
    registry = er.async_get(hass)
    forecast_data = data.forecast.data
    window = forecast_data.window
    return {
        "phases": data.measurements.phases,
        "meter": _meter_info(hass, data.measurements),
        "max_current": data.measurements.max_current,
        "phase_limit_a": round(
            phase_limit_w(data.measurements.max_current, data.forecast.phase_margin)
            / NOMINAL_VOLTAGE,
            1,
        ),
        "phase_margin": data.forecast.phase_margin,
        "has_pv": bool(data.measurements.pv_sensors),
        "has_pv_forecast": bool(data.forecast.pv_entries),
        "pv_forecast_now_w": data.forecast.data.pv_now_w,
        "has_excluded": bool(data.measurements.excluded_sensors),
        "entities": _entity_ids(registry, entry.entry_id, MAIN_KEYS),
        "batteries": [
            {
                "id": config.id,
                "name": config.name,
                "virtual": config.virtual,
                "capacity_kwh": config.capacity_kwh,
                "min_soc": config.min_soc,
                "max_soc": config.max_soc,
                "max_charge_w": config.max_charge_w,
                "max_discharge_w": config.max_discharge_w,
                "phase": config.phase,
                # Extra details from the battery's driver (temperature, cells, ...)
                "details": battery_telemetry(hass, config).as_dict(),
                "entities": _entity_ids(
                    registry, config.id, (d.key for d in BATTERY_SENSORS)
                ),
                **_expected_reach(data, config.id),
            }
            for config in data.batteries.configs
        ],
        "window": {
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
            "hours": round(window.hours, 1),
            "limited_by": window.limited_by.value,
        },
        "prices": _prices_now(hass, data),
        # What the phase protection, phase limits and peak shaving do now.
        "protection": _protection(data),
        # How far each forecast reaches (ISO end or None), for the indicators.
        "reach": {
            "max_end": (
                window.start + timedelta(days=data.forecast.max_days)
            ).isoformat(),
            "consumption_end": (
                forecast_data.consumption[-1].end.isoformat()
                if forecast_data.consumption
                else None
            ),
            "price_end": _iso(forecast_data.price_end),
            "pv_end": _iso(forecast_data.pv_end),
            "has_price": data.forecast.price_configured,
            "has_pv_forecast": bool(data.forecast.pv_entries),
        },
        "decisions": [
            {"time": d["time"], "category": d["category"], "message": d["message"]}
            for d in reversed(data.decisions.entries[-RECENT_DECISIONS:])
        ],
    }


def _loaded_entry(hass: HomeAssistant) -> HomeBatteryAssistConfigEntry | None:
    return next(
        (
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED
        ),
        None,
    )


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/status"})
@callback
def websocket_status(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the status of the (single) loaded HomeBatteryAssist entry."""
    if (entry := _loaded_entry(hass)) is None:
        connection.send_error(msg["id"], "not_loaded", f"{NAME} is not loaded")
        return
    connection.send_result(msg["id"], status(hass, entry))


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/history",
        vol.Optional("days", default=7): vol.All(int, vol.Range(min=1, max=28)),
    }
)
@callback
def websocket_history(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Consumption history for the dashboard: hourly series and day profile."""
    if (entry := _loaded_entry(hass)) is None:
        connection.send_error(msg["id"], "not_loaded", f"{NAME} is not loaded")
        return
    records = entry.runtime_data.history.records
    forecast = entry.runtime_data.forecast
    batteries = entry.runtime_data.batteries
    now = dt_util.utcnow()
    since = now - timedelta(days=msg["days"])
    connection.send_result(
        msg["id"],
        {
            "interval_minutes": entry.runtime_data.history.minutes,
            "days_covered": days_covered(records),
            "imported": sum(1 for r in records if r.get("source") == "import"),
            # [time ms, house consumption W, excluded devices W]
            "hourly": [
                [int(t.timestamp() * 1000), house, excluded]
                for t, house, excluded, _, _ in hourly_series(records, since)
            ],
            # Measured per hour over the requested days:
            # [time ms, house, excluded, PV, battery] (W)
            "past": [
                [int(t.timestamp() * 1000), house, excluded, pv, battery]
                for t, house, excluded, pv, battery in hourly_series(records, since)
            ],
            # PV forecast (corrected) within the planning window, average W per hour
            "pv_forecast": [
                [int(t.timestamp() * 1000), wh]
                for t, wh in sorted(forecast.data.pv_wh.items())
            ],
            "plan_mode": forecast.data.plan_mode,
            "plans": {
                mode: {
                    "strategy": plan.strategy,
                    "saving": round(plan.saving, 2)
                    if plan.saving is not None
                    else None,
                }
                for mode, plan in forecast.data.plans.items()
            },
            # Battery plan of the selected mode: [time ms, power W, SoC %, grid W]
            "battery_forecast": [
                [int(s.start.timestamp() * 1000), s.power_w, s.soc, s.grid_w]
                for s in forecast.data.battery
            ],
            # Capacity behind the plan's state of charge (real + virtual).
            "battery_capacity_kwh": round(
                sum(
                    s.config.capacity_kwh
                    for s in entry.runtime_data.batteries.states.values()
                    if s.soc is not None
                ),
                2,
            ),
            # Cumulative advantage of the selected plan over no battery, incl.
            # the value of the energy stored at that moment: [time ms, amount]
            "selected_vs_none": _vs_none(forecast),
            # Cumulative advantage of arbitrage over NOM: [time ms, amount]
            "arbitrage_vs_nom": [
                [int(t.timestamp() * 1000), value]
                for t, value in compare_modes(
                    forecast.data.plans,
                    (
                        forecast.data.plan_mode
                        if forecast.data.plan_mode in ARBITRAGE_MODES
                        else MODE_ARBITRAGE
                    ),
                    MODE_NOM,
                    forecast.export_factor,
                    forecast.cycle_cost,
                )
            ],
            # Realised value of all batteries so far, and the expected value
            # of the selected plan until the end of the planning window.
            "value": {
                "realized": round(
                    sum(s.get("value", 0.0) for s in batteries.stats.values()), 2
                ),
                "since": min(
                    (
                        s["value_since"]
                        for s in batteries.stats.values()
                        if "value_since" in s
                    ),
                    default=None,
                ),
                "expected": (
                    round(plan.saving, 2)
                    if (plan := forecast.data.plans.get(forecast.data.plan_mode))
                    and plan.saving is not None
                    else None
                ),
                # The selected mode compared with the other mode(s): expected
                # saving difference until the end of the window (+ = better).
                "expected_vs": {
                    mode: round(plan.saving - other.saving, 2)
                    for mode, other in forecast.data.plans.items()
                    if (plan := forecast.data.plans.get(forecast.data.plan_mode))
                    and mode != forecast.data.plan_mode
                    and plan.saving is not None
                    and other.saving is not None
                },
                # Expected saving of every mode compared with no battery.
                "by_mode": {
                    mode: round(other.saving, 2)
                    for mode, other in forecast.data.plans.items()
                    if other.saving is not None
                },
                "mode": forecast.data.plan_mode,
                "max_cycles": forecast.max_cycles,
                "time_slots": len(forecast.time_slots),
                "manual_w": forecast.manual_power,
                "until": forecast.data.window.end.isoformat(),
                "currency": hass.config.currency,
            },
            # State of charge in kWh: measured per battery (every quarter), and
            # the plan's total ahead.
            "soc": {
                "batteries": [
                    {
                        "name": c.name,
                        "virtual": c.virtual,
                        "capacity_kwh": c.capacity_kwh,
                        "points": [
                            [
                                int(dt_util.parse_datetime(t).timestamp() * 1000),
                                round(soc / 100 * c.capacity_kwh, 3),
                            ]
                            for t, soc in batteries.soc_log.get(c.id, [])
                            if t >= since.isoformat()
                        ],
                    }
                    for c in batteries.configs
                ],
            },
            "has_pv": bool(entry.runtime_data.measurements.pv_sensors),
            "has_battery": bool(entry.runtime_data.batteries.configs),
            "has_excluded": bool(entry.runtime_data.measurements.excluded_sensors),
            # Whole planning window: [time ms, expected W, before adjustments W]
            "forecast": [
                [int(s.start.timestamp() * 1000), s.power_w, s.base_w]
                for s in forecast.data.consumption
            ],
            # Last 24 h checked afterwards: [time ms, measured W, predicted W]
            # (predicted = the prediction with the shortest lead time).
            "verification": [
                [
                    int(dt_util.parse_datetime(r["start"]).timestamp() * 1000),
                    r["actual"],
                    next((r["pred"][b] for b in BUCKET_KEYS if b in r["pred"]), None),
                ]
                for r in forecast.accuracy.results["consumption"]
                if r["start"] >= since.isoformat()
            ],
            "accuracy": {
                kind: {
                    "mode": forecast.accuracy.mode(kind, now),
                    "lead_times": forecast.accuracy.summary(kind),
                }
                for kind in KINDS
            },
            "price_unit": forecast.data.price_unit,
            # The plan afterwards, per day: planned saving vs realised value.
            "plan_check": entry.runtime_data.plan_check.days(7),
            "profile": day_profile(records),
            "profile_weeks": week_profiles(records),
        },
    )
