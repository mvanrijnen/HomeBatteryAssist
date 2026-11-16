"""Periodic forecast cycle.

Every cycle runs in a fixed order:

1. read the forecast inputs (prices, PV) from other integrations;
2. determine the planning window: how far ahead we can calculate;
3. check earlier predictions against what really happened (consumption, PV,
   prices) and update the running accuracy;
4. calculate everything else only within the window, with the learned (or
   user-set) corrections: prices, PV and the house consumption forecast;
5. remember the raw predictions, to check them later.

Refreshes every configured forecast interval (5/15/30/60 min, default 15), on
the recalculate action/button, and when the price sensor changes
(new day-ahead prices). Changes of what limits the window are explained in the
decision log.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_BALANCE_INTERVAL,
    CONF_CHARGE_HYSTERESIS,
    CONF_CYCLE_COST,
    CONF_EXPORT_ENTITIES,
    CONF_EXPORT_FACTOR,
    CONF_EXPORT_MODE,
    CONF_FORECAST_INTERVAL,
    CONF_FULL_CHARGE_DAY,
    CONF_FULL_CHARGE_SOLAR,
    CONF_FULL_CHARGE_WINDOW,
    CONF_MANUAL_POWER,
    CONF_MAX_CHARGE_PRICE,
    CONF_MAX_CURRENT,
    CONF_MAX_CYCLES,
    CONF_MIN_BATTERY_POWER,
    CONF_MIN_DISCHARGE_PRICE,
    CONF_MIN_MARGIN,
    CONF_NOM_TARGET,
    CONF_PEAK_INCLUDE_EXCLUDED,
    CONF_PEAK_LIMIT,
    CONF_PHASE_MARGIN,
    CONF_PHASES,
    CONF_PLAN_MODE,
    CONF_PLANNING_HORIZON,
    CONF_PRICE_EXTENSION,
    CONF_PRICE_FORECAST,
    CONF_PRICE_SOURCE,
    CONF_PV_CORRECTION,
    CONF_PV_FORECAST,
    CONF_PV_MARGIN,
    CONF_RESERVE_SOC,
    CONF_SYSTEM_MAX_CHARGE,
    CONF_SYSTEM_MAX_DISCHARGE,
    CONF_TEMP_BAND,
    CONF_TEMP_DISCHARGE,
    CONF_TEMP_LIMIT,
    CONF_TEMP_MIN_POWER,
    DEFAULT_BALANCE_INTERVAL,
    DEFAULT_CYCLE_COST,
    DEFAULT_EXPORT_FACTOR,
    DEFAULT_EXPORT_MODE,
    DEFAULT_FORECAST_INTERVAL,
    DEFAULT_FULL_CHARGE_WINDOW,
    DEFAULT_MANUAL_POWER,
    DEFAULT_MAX_CYCLES,
    DEFAULT_MIN_BATTERY_POWER,
    DEFAULT_PEAK_LIMIT,
    DEFAULT_PHASE_MARGIN,
    DEFAULT_PLANNING_HORIZON,
    DEFAULT_PV_MARGIN,
    DOMAIN,
    EXPORT_FACTOR,
    EXPORT_MARKET,
    EXPORT_SENSOR,
    PRICE_EXTENSION_NONE,
    PRICE_SOURCE_SENSOR,
    PV_CORRECTION_AUTO,
    PV_CORRECTION_BOTH,
    PV_CORRECTION_FIXED,
    SUBENTRY_TIME_SLOT,
)
from ..explain import DecisionLog
from ..explain.plan_story import plan_story
from ..history.consumption import ConsumptionHistory
from ..inputs.batteries import BatteryState
from ..inputs.battery_drivers import telemetry as battery_telemetry
from ..inputs.price_drivers import (
    ROLE_EXPORT,
    ROLE_IMPORT,
    ROLE_MARKET,
    PriceData,
    split_key,
)
from ..inputs.prices import (
    PricePoint,
    calibrate,
    merge_price_forecasts,
    parse_market_forecast,
    parse_price_forecast,
)
from ..inputs.solar import PV_PERIOD, async_get_pv_forecast
from ..planning.battery_plan import (
    DEFAULT_PLAN_MODE,
    MODE_MANUAL,
    MODE_NOM,
    MODE_TIME_SLOTS,
    PLAN_MODES,
    BatteryPlan,
    PlanRules,
    PlanSlot,
    plan_batteries,
)
from ..planning.full_charge import FullCharge, schedule_full_charges
from ..planning.phase_limit import (
    PhaseDevice,
    cap_powers,
    max_power,
    phase_limit_w,
)
from ..planning.planners import BUILTIN, Planner
from ..planning.schedule import WEEKDAYS, Target, TimeSlot, slot_target
from .accuracy import KINDS, ForecastAccuracy
from .adjustments import AdjustmentStore
from .consumption import ForecastSlot, forecast_consumption
from .horizon import HorizonLimit, PlanningWindow, planning_horizon
from .phases import PhaseProfile

_LOGGER = logging.getLogger(__name__)

PRICE_LOG_DAYS = timedelta(days=8)  # published prices kept for the chart

EVENT_FORECAST_UPDATED = f"{DOMAIN}_forecast_updated"
RETRY_INTERVAL = timedelta(minutes=1)


@dataclass(slots=True)
class ForecastData:
    """Result of one forecast cycle; all series are limited to ``window``."""

    window: PlanningWindow
    prices: list[PricePoint] = field(default_factory=list)
    price_unit: str | None = None
    pv_wh: dict[datetime, float] = field(default_factory=dict)  # per hour start
    # How far the inputs reach (may be beyond the window).
    price_end: datetime | None = None
    pv_end: datetime | None = None
    # Expected PV production in the current hour (average W), if forecast.
    pv_now_w: float | None = None
    # Expected house consumption per slot (history interval) within the window.
    consumption: list[ForecastSlot] = field(default_factory=list)
    # Battery plan (advice) of the selected mode per slot, and all plans.
    battery: list[PlanSlot] = field(default_factory=list)
    plans: dict[str, BatteryPlan] = field(default_factory=dict)
    plan_mode: str = DEFAULT_PLAN_MODE
    # Planned (forced) full charges, earliest first.
    full_charges: list[FullCharge] = field(default_factory=list)

    def full_charge_now(self, battery_id: str, when: datetime) -> FullCharge | None:
        """The full charge of ``battery_id`` running at ``when``, if any."""
        return next(
            (
                f
                for f in self.full_charges
                if f.battery_id == battery_id and f.active(when)
            ),
            None,
        )

    @property
    def consumption_method(self) -> str | None:
        """Most used forecast method in the window."""
        methods = Counter(slot.method for slot in self.consumption)
        return methods.most_common(1)[0][0] if methods else None

    def consumption_at(self, when: datetime) -> ForecastSlot | None:
        """The forecast slot containing ``when``."""
        return next((s for s in self.consumption if s.start <= when < s.end), None)


class ForecastCoordinator(DataUpdateCoordinator[ForecastData]):
    """Collects price and PV forecasts and determines the planning horizon."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        decisions: DecisionLog,
        history: ConsumptionHistory,
        adjustments: AdjustmentStore,
        accuracy: ForecastAccuracy,
        battery_states: Callable[[], Iterable[BatteryState]] = lambda: (),
        planners: Mapping[str, Planner] | None = None,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} forecasts",
            update_interval=timedelta(
                minutes=entry.options.get(
                    CONF_FORECAST_INTERVAL, DEFAULT_FORECAST_INTERVAL
                )
            ),
        )
        self._interval = self.update_interval
        self._decisions = decisions
        self.history = history
        self.adjustments = adjustments
        self.accuracy = accuracy
        self.battery_states = battery_states
        self.plan_mode: str = entry.options.get(CONF_PLAN_MODE, DEFAULT_PLAN_MODE)
        # Own planner modules (key custom_<key>), next to the built-in modes.
        self.planners: dict[str, Planner] = dict(planners or {})
        self._failed_planners: set[str] = set()
        self.export_factor: float = entry.options.get(
            CONF_EXPORT_FACTOR, DEFAULT_EXPORT_FACTOR
        )
        self.cycle_cost: float = entry.options.get(CONF_CYCLE_COST, DEFAULT_CYCLE_COST)
        self.max_cycles: float = entry.options.get(CONF_MAX_CYCLES, DEFAULT_MAX_CYCLES)
        self.pv_correction: str = entry.options.get(
            CONF_PV_CORRECTION, PV_CORRECTION_BOTH
        )
        self.pv_margin: float = (
            entry.options.get(CONF_PV_MARGIN, DEFAULT_PV_MARGIN)
            if self.pv_correction in (PV_CORRECTION_FIXED, PV_CORRECTION_BOTH)
            else 0
        )
        self.peak_w: float = entry.options.get(CONF_PEAK_LIMIT, DEFAULT_PEAK_LIMIT)
        self.peak_include_excluded: bool = entry.options.get(
            CONF_PEAK_INCLUDE_EXCLUDED, True
        )
        opts = entry.options
        self.full_charge_day: int | None = (
            WEEKDAYS.index(opts[CONF_FULL_CHARGE_DAY])
            if opts.get(CONF_FULL_CHARGE_DAY) in WEEKDAYS
            else None
        )
        self.full_charge_solar: bool = opts.get(CONF_FULL_CHARGE_SOLAR, True)
        self.temperature = {
            "limit": float(opts.get(CONF_TEMP_LIMIT, 40)),
            "band": float(opts.get(CONF_TEMP_BAND, 10)),
            "min": float(opts.get(CONF_TEMP_MIN_POWER, 40)) / 100,
            "discharge": bool(opts.get(CONF_TEMP_DISCHARGE, False)),
        }
        self.rules = PlanRules(
            reserve_soc=float(opts.get(CONF_RESERVE_SOC, 0)),
            max_charge_w=float(opts.get(CONF_SYSTEM_MAX_CHARGE, 0)),
            max_discharge_w=float(opts.get(CONF_SYSTEM_MAX_DISCHARGE, 0)),
            nom_target_w=float(opts.get(CONF_NOM_TARGET, 0)),
            min_discharge_price=opts.get(CONF_MIN_DISCHARGE_PRICE),
            max_charge_price=opts.get(CONF_MAX_CHARGE_PRICE),
            min_margin=float(opts.get(CONF_MIN_MARGIN, 0)),
            charge_hysteresis=float(opts.get(CONF_CHARGE_HYSTERESIS, 0)),
        )
        self.manual_power: float = entry.options.get(
            CONF_MANUAL_POWER, DEFAULT_MANUAL_POWER
        )
        self.time_slots = [
            TimeSlot.from_data(sub.data)
            for sub in entry.subentries.values()
            if sub.subentry_type == SUBENTRY_TIME_SLOT
        ]
        self.phase_margin: float = entry.options.get(
            CONF_PHASE_MARGIN, DEFAULT_PHASE_MARGIN
        )
        self.min_battery_power: float = entry.options.get(
            CONF_MIN_BATTERY_POWER, DEFAULT_MIN_BATTERY_POWER
        )
        self.full_charge_window: int = entry.options.get(
            CONF_FULL_CHARGE_WINDOW, DEFAULT_FULL_CHARGE_WINDOW
        )
        # battery id -> ISO time of its last full charge (set by __init__)
        self.last_full: Callable[[str], str | None] = lambda battery_id: None
        self._last_full_charges: str | None = None
        self.balance_interval = timedelta(
            minutes=entry.options.get(CONF_BALANCE_INTERVAL, DEFAULT_BALANCE_INTERVAL)
        )
        self._last_plan: str | None = None
        self._last_method: str | None = None
        self._last_corrections: dict[str, str] = {}
        options = entry.options
        self.max_days: int = options.get(
            CONF_PLANNING_HORIZON, DEFAULT_PLANNING_HORIZON
        )
        self.price_entity: str | None = options.get(CONF_PRICE_FORECAST) or None
        # Price driver ("<driver>:<source>") or the price sensor field.
        self.price_source: str = options.get(CONF_PRICE_SOURCE, PRICE_SOURCE_SENSOR)
        if self.price_source != PRICE_SOURCE_SENSOR:
            self.price_entity = None
        self.price_extension: str = options.get(
            CONF_PRICE_EXTENSION, PRICE_EXTENSION_NONE
        )
        self.export_mode: str = options.get(CONF_EXPORT_MODE, DEFAULT_EXPORT_MODE)
        self.export_entities: list[str] = list(options.get(CONF_EXPORT_ENTITIES) or [])
        if self.export_mode == EXPORT_MARKET and not self.export_entities:
            # The bare price from the price sensor itself (market attributes);
            # with a price driver: its market prices (see _read_export_prices).
            self.export_entities = [self.price_entity] if self.price_entity else []
        if self.export_mode == EXPORT_FACTOR:
            self.export_entities = []
        self.pv_entries: list[str] = list(options.get(CONF_PV_FORECAST) or [])
        self._last_limit: HorizonLimit | None = None
        self._price_store: Store[dict[str, Any]] | None = None
        # period start (ISO) -> [end, import price, export price]
        self.price_log: dict[str, list[Any]] = {}
        self._last_price_end: datetime | None = None
        self.phase_profile: PhaseProfile | None = None

    async def _async_load_price_log(self) -> None:
        if self._price_store is None:
            self._price_store = Store(
                self.hass,
                1,
                f"{DOMAIN}.{self.config_entry.entry_id}.prices",
            )
            self.price_log = (await self._price_store.async_load() or {}).get(
                "prices", {}
            )

    def _log_prices(
        self, published: list[PricePoint], slots: list[Any], now: datetime
    ) -> None:
        """Remember published prices (and what export earned) for the chart."""
        export = {s.start: s.export_price for s in slots}
        for point in published:
            key = point.start.isoformat()
            old = self.price_log.get(key)
            value = export.get(point.start)
            if value is None and old is not None:
                value = old[2]
            self.price_log[key] = [point.end.isoformat(), point.price, value]
        cutoff = (now - PRICE_LOG_DAYS).isoformat()
        self.price_log = {k: v for k, v in self.price_log.items() if k >= cutoff}
        if self._price_store is not None:
            self._price_store.async_delay_save(lambda: {"prices": self.price_log}, 60)

    async def async_save_price_log(self) -> None:
        """Write the price log now (on unload, before a reload reads it)."""
        if self._price_store is not None:
            await self._price_store.async_save({"prices": self.price_log})

    def price_series(self, now: datetime) -> list[list[Any]]:
        """Prices for the chart: published ones from the log before the plan
        window, then the window's prices (published or forecast).
        Rows: [start, end, import price, export price, estimated]."""
        data = self.data
        window_start = data.window.start if data else now
        rows: list[list[Any]] = []
        for key, (end, price, export) in sorted(self.price_log.items()):
            start = dt_util.parse_datetime(key)
            if start is not None and start < window_start:
                rows.append([start, dt_util.parse_datetime(end), price, export, False])
        if data:
            export = {s.start: s.export_price for s in data.battery}
            rows.extend(
                [p.start, p.end, p.price, export.get(p.start), p.estimated]
                for p in data.prices
            )
        return rows

    async def _async_update_data(self) -> ForecastData:
        now = dt_util.utcnow()
        await self._async_load_price_log()

        # 1. Inputs
        prices, price_unit = await self._async_read_prices(now)
        export_prices = await self._async_read_export_prices(now)
        pv_wh = await self._async_read_pv(now)
        price_end = prices[-1].end if prices else None
        self._explain_new_prices(prices)
        pv_end = max(pv_wh) + PV_PERIOD if pv_wh else None
        hour = now.replace(minute=0, second=0, microsecond=0)
        pv_now_w = pv_wh.get(hour) if self.pv_entries else None

        # 2. How far ahead can we calculate?
        window = planning_horizon(
            now,
            self.max_days,
            price_end,
            pv_end,
            price_configured=self.price_configured,
            pv_configured=bool(self.pv_entries),
        )
        self._explain_window(window)
        # A configured forecast without data (e.g. its integration is still
        # starting): retry every minute instead of waiting a whole interval.
        self.update_interval = (
            RETRY_INTERVAL
            if window.limited_by in (HorizonLimit.NO_PRICE, HorizonLimit.NO_PV)
            else self._interval
        )

        # 3. Check earlier predictions; update the running accuracy.
        accuracy = self.accuracy
        accuracy.evaluate_consumption(self.history.records)
        accuracy.evaluate_pv(self.history.records)
        accuracy.evaluate_prices(
            {p.start.isoformat(): p.price for p in prices if not p.estimated}
        )
        accuracy.prune(now)
        accuracy.refresh_stats(now)
        self._explain_corrections(now)

        # 5 (inputs). Remember the raw predictions of prices and PV.
        accuracy.record(
            "price", [(p.start, p.end, p.price) for p in prices if p.estimated], now
        )
        accuracy.record(
            "pv", [(start, start + PV_PERIOD, wh) for start, wh in pv_wh.items()], now
        )

        published = [p for p in prices if not p.estimated]
        # 4. Everything else only within the window, corrected.
        prices = [
            PricePoint(
                p.start,
                p.end,
                round(accuracy.correct("price", p.price, p.start, now), 5),
                p.estimated,
            )
            if p.estimated
            else p
            for p in prices
            if window.overlaps(p.start, p.end)
        ]
        pv_wh = {
            start: round(
                accuracy.correct("pv", wh, start, now)
                if self.pv_correction in (PV_CORRECTION_AUTO, PV_CORRECTION_BOTH)
                else wh,
                1,
            )
            for start, wh in pv_wh.items()
            if window.overlaps(start, start + PV_PERIOD)
        }
        if self.pv_entries:
            pv_now_w = pv_wh.get(hour)

        _LOGGER.debug(
            "Inputs: prices until %s, PV until %s -> window %s - %s (%.1f h, %s); "
            "%d price points and %d PV hours in window",
            price_end,
            pv_end,
            window.start,
            window.end,
            window.hours,
            window.limited_by,
            len(prices),
            len(pv_wh),
        )
        self.adjustments.prune(now)
        consumption = forecast_consumption(
            self.history.records,
            window,
            timedelta(minutes=self.history.minutes),
            self.adjustments.items,
            now,
            lambda value, start: accuracy.correct("consumption", value, start, now),
        )
        # 6. Battery plans (advice) for every mode, off the event loop, within
        # the phase limits of the grid connection.
        states = list(self.battery_states())
        # Plans count on less PV than forecast (safety margin against optimistic
        # forecasts): more is charged from the grid where needed.
        pv_plan = {
            start: wh * (1 - self.pv_margin / 100) for start, wh in pv_wh.items()
        }
        limits = self._phase_limits(states, consumption, pv_plan)
        plans: dict[str, BatteryPlan] = {}
        derated = [self._derated(s) for s in states]
        for mode in (*PLAN_MODES, *self.planners):
            planner = self.planners.get(mode) or BUILTIN.get(mode)
            try:
                plan = await self.hass.async_add_executor_job(
                    lambda m=mode, p=planner: plan_batteries(
                        derated,
                        consumption,
                        pv_plan,
                        prices,
                        mode=m,
                        export_factor=self.export_factor,
                        cycle_cost=self.cycle_cost,
                        limits=limits,
                        export_prices=export_prices,
                        max_cycles_per_day=self.max_cycles,
                        peak_w=self.peak_w,
                        target=self._target(m),
                        rules=self.rules,
                        planner=p,
                        now=now,
                    )
                )
            except Exception:  # an own planner module may fail in any way
                _LOGGER.exception("Planner %s failed", mode)
                if mode not in self._failed_planners:
                    self._failed_planners.add(mode)
                    self._decisions.async_log(
                        "planning", "planner_failed", name=self.planner_name(mode)
                    )
                continue
            self._failed_planners.discard(mode)
            if plan is not None:
                plans[mode] = plan
        selected = plans.get(self.plan_mode)
        if selected is None and self.plan_mode not in PLAN_MODES:
            # The chosen own planner is gone or failed: zero on the meter.
            selected = plans.get(MODE_NOM)
        battery = selected.slots if selected else []

        # 7. Periodic full charges at the cheapest moment, added to the plan.
        full_charges = schedule_full_charges(
            states,
            {
                c.id: dt_util.parse_datetime(last)
                if (last := self.last_full(c.id))
                else None
                for c in (s.config for s in states)
            },
            prices,
            self.full_charge_window,
            now,
            fits=self._fits_connection(states, consumption, pv_plan),
            preferred_day=self.full_charge_day,
            slot_price=(
                self._solar_price(consumption, pv_plan, export_prices)
                if self.full_charge_solar
                else None
            ),
        )
        battery = _with_full_charges(battery, full_charges)
        self._explain_full_charges(full_charges)
        data = ForecastData(
            window,
            prices,
            price_unit,
            pv_wh,
            price_end,
            pv_end,
            pv_now_w,
            consumption,
            battery,
            plans,
            self.plan_mode,
            full_charges,
        )
        self._explain_plan(data)
        self._explain_method(data)
        self._log_prices(published, battery, now)

        # 5. Remember the raw consumption predictions.
        accuracy.record(
            "consumption", [(s.start, s.end, s.raw) for s in consumption], now
        )
        self.hass.bus.async_fire(EVENT_FORECAST_UPDATED, summarise(data))
        return data

    def planner_name(self, mode: str) -> str:
        """Name of a plan mode / planner for the user."""
        planner = self.planners.get(mode)
        return planner.name or mode if planner is not None else mode

    def _phase_limits(
        self,
        states: list[BatteryState],
        consumption: list[ForecastSlot],
        pv_wh: dict[datetime, float],
    ) -> dict[datetime, tuple[float, float]]:
        """Most charge/discharge power per slot without overloading a phase."""
        phases = self.config_entry.data[CONF_PHASES]
        limit = phase_limit_w(
            self.config_entry.data[CONF_MAX_CURRENT], self.phase_margin
        )
        devices = [
            PhaseDevice.from_config(s.config, phases)
            for s in states
            if s.soc is not None and s.config.capacity_kwh > 0
        ]
        if not devices:
            return {}
        self.phase_profile = PhaseProfile(self.history.records, phases)
        return {
            start: (
                max_power(devices, loads, limit, charging=True),
                max_power(devices, loads, limit, charging=False),
            )
            for start, loads in self.phase_profile.loads(consumption, pv_wh).items()
        }

    def _derated(self, state: BatteryState) -> Any:
        """The battery with its power reduced when it is warm (temperature
        sensor); other batteries as they are."""
        sensor = state.config.temperature_sensor
        temp = self.hass.states.get(sensor) if sensor else None
        try:
            celsius = float(temp.state) if temp else None
        except ValueError:
            celsius = None
        if celsius is None:
            # No own sensor: the battery's driver may know the temperature.
            celsius = battery_telemetry(self.hass, state.config).temperature_c
        t = self.temperature
        if celsius is None or celsius <= t["limit"] or t["band"] <= 0:
            return state
        factor = max(t["min"], 1 - (celsius - t["limit"]) / t["band"] * (1 - t["min"]))
        return SimpleNamespace(
            soc=state.soc,
            config=state.config,
            charge_factor=factor,
            discharge_factor=factor if t["discharge"] else 1.0,
        )

    def _solar_price(
        self,
        consumption: list[ForecastSlot],
        pv: dict[datetime, float],
        export_prices: list[PricePoint],
    ) -> Callable[[datetime, float, float], float]:
        """Charging with solar surplus costs what exporting it would have earned."""
        surplus: dict[datetime, float] = {}
        for slot in consumption:
            hour = slot.start.replace(minute=0, second=0, microsecond=0)
            surplus[slot.start] = max(pv.get(hour, 0.0) - slot.power_w, 0.0)
        factor = self.export_factor

        def price(start: datetime, import_price: float, power: float) -> float:
            share = min(surplus.get(start, 0.0) / power, 1.0) if power > 0 else 0.0
            export = next(
                (p.price for p in export_prices if p.start <= start < p.end),
                import_price * factor,
            )
            return share * export + (1 - share) * import_price

        return price

    def _target(self, mode: str) -> Callable[[datetime], Target | None] | None:
        """The fixed actions of the manual and time slot modes."""
        if mode == MODE_MANUAL:
            manual = Target(self.manual_power, None, "manual")
            return lambda _when: manual
        if mode == MODE_TIME_SLOTS:
            slots = self.time_slots
            return lambda when: slot_target(slots, when)
        return None

    def _fits_connection(
        self,
        states: list[BatteryState],
        consumption: list[ForecastSlot],
        pv_wh: dict[datetime, float],
    ) -> Callable[[datetime, Mapping[str, float]], bool]:
        """Whether batteries charging together stay within the phase limits."""
        phases = self.config_entry.data[CONF_PHASES]
        limit = phase_limit_w(
            self.config_entry.data[CONF_MAX_CURRENT], self.phase_margin
        )
        devices = [PhaseDevice.from_config(s.config, phases) for s in states]
        profile = self.phase_profile or PhaseProfile(self.history.records, phases)
        loads = profile.loads(consumption, pv_wh)
        starts = sorted(loads)

        def fits(when: datetime, powers: Mapping[str, float]) -> bool:
            start = next((s for s in reversed(starts) if s <= when), None)
            load = loads[start] if start is not None else [0.0] * phases
            capped, _ = cap_powers(powers, devices, load, limit)
            return all(abs(capped[k] - v) < 1 for k, v in powers.items())

        return fits

    def summary(self) -> dict[str, Any]:
        """Short description of the latest result (action response, event)."""
        return summarise(self.data)

    @property
    def price_configured(self) -> bool:
        """A price source (driver or sensor) is set."""
        return self.price_source != PRICE_SOURCE_SENSOR or bool(self.price_entity)

    @property
    def price_watch(self) -> list[str]:
        """Entities whose updates mean new prices (recalculate right away)."""
        entities = [e for e in (self.price_entity, *self.export_entities) if e]
        for key in (self.price_source, self.price_extension):
            driver, source = split_key(key)
            if driver is not None:
                entities += driver.watch(self.hass, source)
        return list(dict.fromkeys(entities))

    async def _async_read_driver(self, key: str, role: str) -> PriceData:
        driver, source = split_key(key)
        if driver is None:
            return PriceData([])
        return await driver.async_read(self.hass, source, role)

    async def _async_read_prices(
        self, now: datetime
    ) -> tuple[list[PricePoint], str | None]:
        """Import prices: price driver or sensor, plus an optional extension."""
        if self.price_source != PRICE_SOURCE_SENSOR:
            data = await self._async_read_driver(self.price_source, ROLE_IMPORT)
            prices, unit = data.points, data.unit
        elif self.price_entity:
            state = self.hass.states.get(self.price_entity)
            prices = parse_price_forecast(state)
            unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) if state else None
        else:
            return [], None
        if self.price_extension != PRICE_EXTENSION_NONE:
            # A longer forecast after the source's own prices; always estimated.
            # A market-only forecast is first put on the level of the real prices.
            driver, _source = split_key(self.price_extension)
            offered = {
                s.key: s for s in (driver.find(self.hass) if driver else [])
            }.get(self.price_extension)
            market_only = offered is not None and ROLE_IMPORT not in offered.roles
            extra = await self._async_read_driver(
                self.price_extension, ROLE_MARKET if market_only else ROLE_IMPORT
            )
            points = (
                calibrate(extra.points, prices)
                if market_only
                else [replace(p, estimated=True) for p in extra.points]
            )
            prices = merge_price_forecasts([prices, points])
        return [p for p in prices if p.end > now], unit

    async def _async_read_export_prices(self, now: datetime) -> list[PricePoint]:
        """What exported energy earns, from the export price sensor(s) or the
        price driver; empty means the import price x the export factor."""
        driver, _source = split_key(self.price_source)
        if driver is not None and not self.export_entities:
            role = {EXPORT_MARKET: ROLE_MARKET, EXPORT_SENSOR: ROLE_EXPORT}.get(
                self.export_mode
            )
            sources = {
                s.id: s for s in driver.find(self.hass) if s.key == self.price_source
            }
            if role and any(role in s.roles for s in sources.values()):
                data = await self._async_read_driver(self.price_source, role)
                return [p for p in data.points if p.end > now]
        if not self.export_entities:
            return []
        parse = (
            parse_market_forecast
            if self.export_mode == EXPORT_MARKET
            else parse_price_forecast
        )
        return [
            p
            for p in merge_price_forecasts(
                [parse(self.hass.states.get(e)) for e in self.export_entities]
            )
            if p.end > now
        ]

    async def _async_read_pv(self, now: datetime) -> dict[datetime, float]:
        if not self.pv_entries:
            return {}
        forecast = await async_get_pv_forecast(self.hass, self.pv_entries)
        return {start: wh for start, wh in forecast.items() if start + PV_PERIOD > now}

    def _explain_corrections(self, now: datetime) -> None:
        """Explain when the correction of a forecast changes noticeably."""
        for kind in KINDS:
            mode = self.accuracy.mode(kind, now)
            stats = self.accuracy.headline(kind)
            correction = self.accuracy.correction_for(kind, "6-24h", now)
            if (
                mode == "off"
                or correction is None
                or stats is None
                or (mode == "learned" and stats.strength < 1)
            ):
                text = "none"
            elif kind == "pv":
                text = f"x{correction:.2f}"
            elif kind == "price":
                text = f"{correction:+.3f}"
            else:
                text = f"{round(correction / 10) * 10:+.0f} W"
            if self._last_corrections.get(kind) == text:
                continue
            first = kind not in self._last_corrections
            self._last_corrections[kind] = text
            if first and text == "none":
                continue  # nothing to explain at start-up
            self._decisions.async_log(
                "forecast",
                f"correction_{kind}" if text != "none" else "correction_none",
                kind=kind,
                mode=mode,
                correction=text,
                samples=stats.samples if stats else 0,
            )

    def _explain_full_charges(self, full_charges: list[FullCharge]) -> None:
        """Explain newly planned or moved full charges."""
        key = "|".join(f"{f.battery_id}@{f.start.isoformat()}" for f in full_charges)
        if key == self._last_full_charges:
            return
        self._last_full_charges = key
        now = dt_util.utcnow()
        unit = self.data.price_unit if self.data else ""
        for charge in full_charges:
            overdue = charge.deadline <= now
            self._decisions.async_log(
                "planning",
                "full_charge_overdue" if overdue else "full_charge_planned",
                days=self.full_charge_window,
                name=charge.name,
                start=charge.start,
                end=charge.end,
                deadline=charge.deadline,
                last=charge.last_full
                or (
                    "nooit"
                    if (self.hass.config.language or "").startswith("nl")
                    else "never"
                ),
                price=_price(charge.price, unit, self.hass.config.language),
                avg_price=_price(charge.avg_price, unit, self.hass.config.language),
            )

    def _explain_plan(self, data: ForecastData) -> None:
        """Explain the plan in plain language when it changes noticeably."""
        plan = data.plans.get(data.plan_mode)
        if plan is None or not plan.slots:
            return
        now = dt_util.utcnow()
        states = list(self.battery_states())
        min_soc_reached = bool(states) and all(
            s.soc is not None and s.soc <= s.config.min_soc + 0.5 for s in states
        )
        text = plan_story(
            plan,
            {m: p for m, p in data.plans.items() if m != data.plan_mode},
            now,
            self.hass.config.language,
            _plan_efficiency(states),
            self.cycle_cost,
            min_soc_reached,
            self.config_entry.data[CONF_MAX_CURRENT],
            [(f.start, f.end, f.name) for f in data.full_charges],
        )
        # Log when the gist changes (not for every small change in numbers).
        current = next((s for s in plan.slots if s.start <= now < s.end), None)
        action = (
            "charge"
            if current and current.power_w > 100
            else "discharge"
            if current and current.power_w < -100
            else "idle"
        )
        first_charge = next((s.start for s in plan.slots if s.power_w > 100), None)
        key = f"{plan.mode}|{action}|{first_charge}|{_money(plan.saving)}"
        if key == self._last_plan:
            return
        self._last_plan = key
        self._decisions.async_log("planning", "battery_plan_story", text=text)

    def _explain_method(self, data: ForecastData) -> None:
        """Explain on which history the consumption forecast is based."""
        method = data.consumption_method or "none"
        if method == self._last_method:
            return
        self._last_method = method
        self._decisions.async_log(
            "forecast",
            f"consumption_method_{method}",
            days=round(
                sum(r["minutes"] * r["coverage"] for r in self.history.records) / 1440
            ),
        )

    def _explain_new_prices(self, prices: list[PricePoint]) -> None:
        """Tell when new published prices arrive (e.g. tomorrow's)."""
        published = [p for p in prices if not p.estimated]
        end = published[-1].end if published else None
        previous, self._last_price_end = self._last_price_end, end
        if previous is None or end is None or end - previous < timedelta(hours=6):
            return
        self._decisions.async_log(
            "planning",
            "prices_updated",
            end=end,
            hours=round((end - previous).total_seconds() / 3600),
        )

    def _explain_window(self, window: PlanningWindow) -> None:
        """Log in the decision log when the limiting factor changes."""
        if window.limited_by == self._last_limit:
            return
        self._last_limit = window.limited_by
        self._decisions.async_log(
            "planning",
            f"horizon_{window.limited_by}",
            end=window.end,
            hours=round(window.hours),
            days=self.max_days,
            entity=self.price_entity or "",
        )


def summarise(data: ForecastData) -> dict[str, Any]:
    """JSON-friendly summary of a forecast cycle."""
    window = data.window
    return {
        "window_start": window.start.isoformat(),
        "window_end": window.end.isoformat(),
        "hours_ahead": round(window.hours, 1),
        "limited_by": window.limited_by.value,
        "price_points": len(data.prices),
        "price_points_estimated": sum(p.estimated for p in data.prices),
        "pv_hours": len(data.pv_wh),
        "consumption_slots": len(data.consumption),
        "consumption_kwh": round(
            sum(
                s.power_w * (s.end - s.start).total_seconds() / 3_600_000
                for s in data.consumption
            ),
            2,
        ),
        "consumption_method": data.consumption_method,
    }


def _money(value: float | None) -> str:
    """Rounded to 0.10 so small changes do not flood the decision log."""
    return "-" if value is None else f"{round(value, 1):.2f}"


DAYS = {
    "nl": ("ma", "di", "wo", "do", "vr", "za", "zo"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}


def _periods(
    slots: list[PlanSlot],
    *,
    charging: bool,
    threshold: float = 100.0,
    language: str | None = None,
) -> str:
    """Up to three periods (local time) in which the plan charges / discharges."""
    periods: list[tuple[datetime, datetime]] = []
    for slot in slots:
        active = slot.power_w > threshold if charging else slot.power_w < -threshold
        if not active:
            continue
        if periods and periods[-1][1] == slot.start:
            periods[-1] = (periods[-1][0], slot.end)
        else:
            periods.append((slot.start, slot.end))
    days = DAYS["nl" if (language or "").startswith("nl") else "en"]

    def fmt(start: datetime, end: datetime) -> str:
        a, b = dt_util.as_local(start), dt_util.as_local(end)
        return f"{days[a.weekday()]} {a:%H:%M}-{b:%H:%M}"

    text = ", ".join(fmt(a, b) for a, b in periods[:3])
    return text + (" ..." if len(periods) > 3 else "") if text else "-"


def _with_full_charges(
    slots: list[PlanSlot], full_charges: list[FullCharge]
) -> list[PlanSlot]:
    """Add the forced full charges to the plan (extra charge power and grid)."""
    if not full_charges:
        return slots
    result = []
    for slot in slots:
        extra = sum(
            f.power_w
            * (min(slot.end, f.end) - max(slot.start, f.start)).total_seconds()
            / (slot.end - slot.start).total_seconds()
            for f in full_charges
            if slot.start < f.end and slot.end > f.start
        )
        if extra:
            # When the plan charges anyway, the batteries that charge fully are
            # part of that power: count the larger of the two, not both.
            power = (
                max(slot.power_w, extra) if slot.power_w > 0 else slot.power_w + extra
            )
            slot = replace(
                slot,
                power_w=round(power, 1),
                grid_w=round(slot.grid_w + power - slot.power_w, 1),
            )
        result.append(slot)
    return result


def _avg_price(
    slots: list[PlanSlot], *, charging: bool, threshold: float = 100.0
) -> float | None:
    """Energy weighted average price while the plan charges / discharges."""
    total = weight = 0.0
    for slot in slots:
        active = slot.power_w > threshold if charging else slot.power_w < -threshold
        if not active or slot.price is None:
            continue
        energy = abs(slot.power_w) * (slot.end - slot.start).total_seconds()
        total += slot.price * energy
        weight += energy
    return total / weight if weight else None


def _price(value: float | None, unit: str | None, language: str | None = None) -> str:
    if value is None:
        return "-"
    if (language or "").startswith("nl"):
        return f"€ {value:.2f}".replace(".", ",")
    return (
        f"€ {value:.2f}"
        if (unit or "").startswith("€")
        else f"{value:.3f} {unit or ''}".strip()
    )


def _plan_efficiency(states: Iterable[BatteryState]) -> float:
    """Capacity weighted round-trip efficiency of the batteries."""
    usable = [s for s in states if s.soc is not None]
    capacity = sum(s.config.capacity_kwh for s in usable)
    if not capacity:
        return 1.0
    return sum(s.config.efficiency * s.config.capacity_kwh for s in usable) / capacity
