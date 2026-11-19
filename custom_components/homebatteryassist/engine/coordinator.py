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
from bisect import bisect_right
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
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
    CHARGE_SEQUENTIAL,
    CONF_BALANCE_INTERVAL,
    CONF_CHARGE_HYSTERESIS,
    CONF_CHARGE_ORDER,
    CONF_CONSUMPTION_FORECASTER,
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
    CONF_NIGHT_RESERVE_SOC,
    CONF_NOM_TARGET,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_PEAK_INCLUDE_EXCLUDED,
    CONF_PEAK_LIMIT,
    CONF_PEAK_RESERVE_SOC,
    CONF_PHASE_MARGIN,
    CONF_PHASES,
    CONF_PLAN_MODE,
    CONF_PLANNING_HORIZON,
    CONF_PRICE_EXTENSION,
    CONF_PRICE_FORECAST,
    CONF_PRICE_SOURCE,
    CONF_PV_CORRECTION,
    CONF_PV_CORRECTOR,
    CONF_PV_DEVIATION_W,
    CONF_PV_FORECAST,
    CONF_PV_MARGIN,
    CONF_REACT_AVERAGE,
    CONF_REACT_INTERVAL,
    CONF_REACT_JUMP,
    CONF_REACT_JUMP_W,
    CONF_RESERVE_SOC,
    CONF_SPIKE_BATTERY,
    CONF_SPIKE_HISTORY,
    CONF_SYSTEM_MAX_CHARGE,
    CONF_SYSTEM_MAX_DISCHARGE,
    CONF_TARIFF,
    CONF_TARIFF_ENERGY_TAX,
    CONF_TARIFF_SURCHARGE,
    CONF_TARIFF_VAT,
    CONF_TEMP_BAND,
    CONF_TEMP_DISCHARGE,
    CONF_TEMP_LIMIT,
    CONF_TEMP_MIN_POWER,
    CONF_WEATHER_API_KEY,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_LOCATION,
    CONF_WEATHER_SOURCE,
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
    DEFAULT_PV_DEVIATION_W,
    DEFAULT_PV_MARGIN,
    DEFAULT_REACT_INTERVAL,
    DEFAULT_REACT_JUMP_W,
    DEFAULT_TARIFF_VAT,
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
from .devices.batteries import telemetry as battery_telemetry
from .evaluation.forecast_accuracy import (
    FORECASTER_KIND,
    HEATING_KIND,
    KINDS,
    PV_CORRECTOR_KIND,
    ForecastAccuracy,
)
from .evaluation.price_surprise import PriceSurprise, PriceSurprises
from .evaluation.pv_corrections import BUILTIN as PV_CORRECTORS
from .evaluation.pv_corrections import (
    DEFAULT_PV_CORRECTOR,
    PvCorrectionInput,
    PvCorrector,
    apply_pv_correction,
)
from .evaluation.pv_corrections.lead_time import LeadTimeCorrector
from .explain import DecisionLog
from .explain.money import format_money
from .explain.plan_story import DAYS as STORY_DAYS
from .explain.plan_story import plan_story
from .forecast.consumption_forecast import (
    METHODS,
    ForecastSlot,
    forecast_consumption,
    raw_forecast,
)
from .forecast.forecasters import BUILTIN as FORECASTERS
from .forecast.forecasters import DEFAULT_FORECASTER, Forecaster
from .forecast.phase_shares import PhaseProfile
from .forecast.planning_window import HorizonLimit, PlanningWindow, planning_horizon
from .forecast.temperature_effect import (
    TemperatureEffect,
    TemperatureModel,
    fit_effect,
    slot_temperatures,
)
from .forecast.user_adjustments import AdjustmentStore
from .history.consumption_history import ConsumptionHistory
from .history.spikes import is_regular, regular_peak_hours, without_spikes
from .measure.battery_monitor import BatteryState
from .measure.heating_zones import heating_zones
from .planning.battery_plan import (
    DEFAULT_PLAN_MODE,
    MODE_MANUAL,
    MODE_NOM,
    MODE_TIME_SLOTS,
    PLAN_MODES,
    BatteryPlan,
    PlanRules,
    PlanSlot,
    night_starts,
    plan_batteries,
)
from .planning.full_charge import FullCharge, schedule_full_charges
from .planning.phase_limit import (
    PhaseDevice,
    cap_powers,
    max_power,
    phase_limit_w,
)
from .planning.planners import BUILTIN, Planner
from .planning.time_slots import WEEKDAYS, Target, TimeSlot, slot_target
from .sources.prices import (
    ROLE_EXPORT,
    ROLE_IMPORT,
    ROLE_MARKET,
    PriceData,
    split_key,
)
from .sources.prices.price_points import (
    MARKET_ATTRIBUTES,
    PricePoint,
    calibrate,
    merge_price_forecasts,
    parse_market_forecast,
    parse_price_forecast,
    per_kwh,
)
from .sources.pv_forecasts import PvForecastSource, async_read_pv_forecasts
from .sources.pv_forecasts.energy_dashboard_platform import PV_PERIOD
from .sources.tariffs import BUILTIN as TARIFFS
from .sources.tariffs import DEFAULT_TARIFF, Tariff, apply_tariff
from .sources.tariffs.as_price_source import SourceTariff
from .sources.weather import (
    DEFAULT_WEATHER_SOURCE,
    WeatherSettings,
    WeatherSource,
    checked_forecast,
    create_weather_source,
    valid_temperature,
)
from .units import state_to_celsius

_LOGGER = logging.getLogger(__name__)

PRICE_LOG_DAYS = timedelta(days=8)  # published prices kept for the chart

EVENT_FORECAST_UPDATED = f"{DOMAIN}_forecast_updated"
RETRY_INTERVAL = timedelta(minutes=1)
# Right after a start other integrations may not deliver yet: "no prices" /
# "no PV" is only told when it lasts longer than this.
STARTUP_GRACE = timedelta(minutes=5)


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
    # Slots (by start) of the night reserve: from the evening until sunrise.
    night: set[datetime] = field(default_factory=set)
    # What exported energy earns per period (after the tariff), as published.
    export_prices: list[PricePoint] = field(default_factory=list)

    @property
    def selected_plan(self) -> BatteryPlan | None:
        """The plan in use: the chosen mode's, or zero on the meter when the
        chosen own planner failed or is gone."""
        return self.plans.get(self.plan_mode) or self.plans.get(MODE_NOM)

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

    def night_at(self, when: datetime) -> bool:
        """Whether the night reserve holds at ``when``."""
        slot = self.consumption_at(when)
        return slot is not None and slot.start in self.night

    def pv_at(self, when: datetime) -> float | None:
        """The PV forecast (average W) of the hour holding ``when``."""
        for start, wh in self.pv_wh.items():
            if start <= when < start + timedelta(hours=1):
                return wh
        return None

    def consumption_at(self, when: datetime) -> ForecastSlot | None:
        """The forecast slot containing ``when``."""
        return next((s for s in self.consumption if s.start <= when < s.end), None)


def _pv_end(pv_wh: Mapping[datetime, float]) -> datetime | None:
    """Until when the PV forecast reaches: its last hour; when it leaves out
    the night (no hour between local midnight and 03:00 at all, e.g.
    Forecast.Solar), up to local midnight after its last hour."""
    if not pv_wh:
        return None
    last = max(pv_wh)
    if any(dt_util.as_local(k).hour < 3 for k in pv_wh):
        return last + PV_PERIOD
    return max(last + PV_PERIOD, _end_of_local_day(last))


def _end_of_local_day(when: datetime) -> datetime:
    """Local midnight after ``when`` (UTC)."""
    local = dt_util.as_local(when)
    midnight = dt_util.start_of_local_day(local.date() + timedelta(days=1))
    return dt_util.as_utc(midnight)


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
        forecasters: Mapping[str, Forecaster] | None = None,
        tariffs: Mapping[str, Tariff] | None = None,
        pv_sources: Mapping[str, PvForecastSource] | None = None,
        pv_correctors: Mapping[str, PvCorrector] | None = None,
        weather_sources: Mapping[str, type[WeatherSource]] | None = None,
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
        self.plan_fallback = False  # the chosen own planner failed or is gone
        # Consumption forecasters: own ones next to the built-in ones.
        self.forecasters: dict[str, Forecaster] = dict(forecasters or {})
        self.forecaster_key: str = entry.options.get(
            CONF_CONSUMPTION_FORECASTER, DEFAULT_FORECASTER
        )
        self.forecaster_fallback = False
        self._failed_forecasters: set[str] = set()
        # Tariff: what a kWh really costs and earns.
        self.tariffs: dict[str, Tariff] = dict(tariffs or {})
        self.tariff_key: str = entry.options.get(CONF_TARIFF, DEFAULT_TARIFF)
        self.tariff_fallback = False
        # The interceptor module (engine/control/interceptors), set at setup.
        self.interceptor: Any = None
        # Bare market prices (when the price source has them), for the
        # dashboard and tariffs that need them.
        self.market_prices: list[PricePoint] = []
        self._failed_tariffs: set[str] = set()
        # Own PV forecast sources (the built-in one reads the Energy platforms).
        self.pv_sources: dict[str, PvForecastSource] = dict(pv_sources or {})
        # PV correction: own ones next to the built-in ones.
        self.pv_correctors: dict[str, PvCorrector] = dict(pv_correctors or {})
        self.pv_corrector_key: str = entry.options.get(
            CONF_PV_CORRECTOR, DEFAULT_PV_CORRECTOR
        )
        self.pv_corrector_fallback = False
        self._failed_pv_correctors: set[str] = set()
        # Short peaks: random ones out of the average / not discharged for.
        self.spike_history: bool = entry.options.get(CONF_SPIKE_HISTORY, True)
        self.spike_battery: bool = entry.options.get(CONF_SPIKE_BATTERY, True)
        self.regular_peaks: set[tuple[int, int]] = set()
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
        # Solar clearly more / less than forecast now (virtual batteries, Why).
        self.pv_deviation_w: float = float(
            entry.options.get(CONF_PV_DEVIATION_W, DEFAULT_PV_DEVIATION_W)
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
        self.charge_order: str = opts.get(CONF_CHARGE_ORDER, CHARGE_SEQUENTIAL)
        self.temperature = {
            "limit": float(opts.get(CONF_TEMP_LIMIT, 40)),
            "band": float(opts.get(CONF_TEMP_BAND, 10)),
            "min": float(opts.get(CONF_TEMP_MIN_POWER, 40)) / 100,
            "discharge": bool(opts.get(CONF_TEMP_DISCHARGE, False)),
        }
        self.rules = PlanRules(
            reserve_soc=float(opts.get(CONF_RESERVE_SOC, 0)),
            night_reserve_soc=float(opts.get(CONF_NIGHT_RESERVE_SOC, 0)),
            peak_reserve_soc=float(opts.get(CONF_PEAK_RESERVE_SOC, 0)),
            max_charge_w=float(opts.get(CONF_SYSTEM_MAX_CHARGE, 0)),
            max_discharge_w=float(opts.get(CONF_SYSTEM_MAX_DISCHARGE, 0)),
            nom_target_w=float(opts.get(CONF_NOM_TARGET, 0)),
            min_discharge_price=opts.get(CONF_MIN_DISCHARGE_PRICE),
            max_charge_price=opts.get(CONF_MAX_CHARGE_PRICE),
            min_margin=float(opts.get(CONF_MIN_MARGIN, 0)),
            charge_hysteresis=float(opts.get(CONF_CHARGE_HYSTERESIS, 0)),
            charge_sequential=opts.get(CONF_CHARGE_ORDER, CHARGE_SEQUENTIAL)
            == CHARGE_SEQUENTIAL,
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
        # Recalculated by hand: tell the plan in *Why* even when unchanged.
        self.explain_next = False
        self._last_corrections: dict[str, str] = {}
        self.price_surprises = PriceSurprises()
        options = entry.options
        self.max_days: int = options.get(
            CONF_PLANNING_HORIZON, DEFAULT_PLANNING_HORIZON
        )
        self.price_entity: str | None = options.get(CONF_PRICE_FORECAST) or None
        # Optional: outdoor temperature (now and forecast) for the forecast.
        # The weather source module (none when not set up).
        self.weather_key: str = (
            options.get(CONF_WEATHER_SOURCE) or DEFAULT_WEATHER_SOURCE
        )
        self.weather: WeatherSource | None = create_weather_source(
            self.weather_key,
            dict(weather_sources or {}),
            WeatherSettings(
                entity_id=options.get(CONF_WEATHER_ENTITY) or None,
                api_key=options.get(CONF_WEATHER_API_KEY) or None,
                location=options.get(CONF_WEATHER_LOCATION) or None,
            ),
        )
        self.outdoor_sensor: str | None = options.get(CONF_OUTDOOR_TEMPERATURE) or None
        # Reaction on the meter (virtual batteries now, the control later).
        self.react_interval = timedelta(
            seconds=options.get(CONF_REACT_INTERVAL, DEFAULT_REACT_INTERVAL)
        )
        self.react_average: bool = options.get(CONF_REACT_AVERAGE, True)
        self.react_jump_w: float | None = (
            float(options.get(CONF_REACT_JUMP_W, DEFAULT_REACT_JUMP_W))
            if options.get(CONF_REACT_JUMP, True)
            else None
        )
        self.temperature_model: TemperatureEffect | None = None
        # heating/cooling devices with their own temperatures: zones
        self.zones = heating_zones(entry)
        self.temperatures: list[float | None] | None = None  # per slot
        # (slot start, forecast °C) for the dashboard
        self.temperature_slots: list[tuple[datetime, float | None]] = []
        # How far the outdoor temperature forecast reaches (end of its last hour).
        self.weather_end: datetime | None = None
        self._last_temperature: str | None = None
        # Price driver ("<driver>:<source>") or the price sensor field.
        self.price_source: str = options.get(CONF_PRICE_SOURCE, PRICE_SOURCE_SENSOR)
        if self.price_source != PRICE_SOURCE_SENSOR:
            self.price_entity = None
        self.price_extension: str = options.get(
            CONF_PRICE_EXTENSION, PRICE_EXTENSION_NONE
        )
        self.export_mode: str = options.get(CONF_EXPORT_MODE, DEFAULT_EXPORT_MODE)
        self._export_market_only = False
        self.export_entities: list[str] = list(options.get(CONF_EXPORT_ENTITIES) or [])
        if self.export_mode == EXPORT_MARKET and not self.export_entities:
            # The bare price from the price sensor itself (market attributes);
            # with a price driver: its market prices (see _read_export_prices).
            self.export_entities = [self.price_entity] if self.price_entity else []
            # Only its market attributes: an all-in price is no export price.
            self._export_market_only = True
        if self.export_mode == EXPORT_FACTOR:
            self.export_entities = []
        self.pv_entries: list[str] = list(options.get(CONF_PV_FORECAST) or [])
        self._last_limit: HorizonLimit | None = None
        self._started_at = dt_util.utcnow()
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
            stored = (await self._price_store.async_load() or {}).get("prices", {})
            self.price_log = {
                key: list(value)
                for key, value in (stored.items() if isinstance(stored, dict) else ())
                if isinstance(value, list | tuple)
                and len(value) == 3
                and isinstance(value[1], int | float)
                and dt_util.parse_datetime(str(key)) is not None
                and dt_util.parse_datetime(str(value[0])) is not None
            }

    def _log_prices(
        self,
        published: list[PricePoint],
        slots: list[Any],
        now: datetime,
        export_prices: Sequence[PricePoint] = (),
    ) -> None:
        """Remember published prices (and what export earned) for the chart."""
        export = _export_at(export_prices, slots)
        for point in published:
            key = point.start.isoformat()
            old = self.price_log.get(key)
            value = export(point.start)
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
            end_at = dt_util.parse_datetime(end)
            # Only periods that ended before the window (the current one comes
            # from the window's prices).
            if start is not None and end_at is not None and end_at <= window_start:
                rows.append([start, end_at, price, export, False])
        if data:
            export = _export_at(data.export_prices, data.battery)
            rows.extend(
                [p.start, p.end, p.price, export(p.start), p.estimated]
                for p in data.prices
            )
        return rows

    async def _async_update_data(self) -> ForecastData:
        now = dt_util.utcnow()
        await self._async_load_price_log()
        if self.spike_history or self.spike_battery:
            self.regular_peaks = regular_peak_hours(self.history.records, now)

        # 1. Inputs
        prices, price_unit = await self._async_read_prices(now)
        export_prices = await self._async_read_export_prices(now)
        pv_wh = await self._async_read_pv(now)
        price_end = prices[-1].end if prices else None
        self._explain_new_prices(prices)
        # A PV forecast often leaves out the night (sunrise..sunset only):
        # after its last daylight hour there is no sun, so it covers its last
        # day up to local midnight (else the window ends at sunset and the
        # evening peak is never planned).
        pv_end = _pv_end(pv_wh)
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
        accuracy.evaluate_consumption(self.forecast_records())
        accuracy.evaluate_pv(self.history.records)
        accuracy.evaluate_heating(self.history.records)
        accuracy.evaluate_prices(
            [(p.start, p.end, p.price) for p in prices if not p.estimated]
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
        # Published prices that differ strongly from the estimate the plan
        # used until now: say so (the plan changes noticeably).
        self._explain_price_surprises(
            self.price_surprises.check(
                [(p.start, p.end, p.price) for p in prices if not p.estimated], now
            )
        )
        self.price_surprises.remember(
            (p.start, p.end, p.price) for p in prices if p.estimated
        )
        pv_wh = self._correct_pv(
            {
                start: wh
                for start, wh in pv_wh.items()
                if window.overlaps(start, start + PV_PERIOD)
            },
            now,
        )
        if self.pv_entries:
            pv_now_w = pv_wh.get(hour)
        self.market_prices = await self._async_read_market(now)
        # What a kWh really costs and earns: the chosen tariff module.
        prices, export_prices = await self._async_apply_tariff(
            prices, export_prices, now, price_unit
        )

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
        step = timedelta(minutes=self.history.minutes)
        await self._async_read_temperature(window, step, now)
        chosen = self.forecasters.get(self.forecaster_key) or FORECASTERS.get(
            self.forecaster_key
        )
        try:
            consumption = forecast_consumption(
                self.forecast_records(),
                window,
                step,
                self.adjustments.items,
                now,
                lambda value, start: accuracy.correct("consumption", value, start, now),
                chosen,
                self.temperatures,
                self.temperature_model,
            )
            self.forecaster_fallback = chosen is None
        except Exception:  # an own forecaster module may fail in any way
            _LOGGER.exception("Consumption forecaster %s failed", self.forecaster_key)
            self._forecaster_failed(self.forecaster_key)
            self.forecaster_fallback = True
            consumption = forecast_consumption(
                self.forecast_records(),
                window,
                step,
                self.adjustments.items,
                now,
                lambda value, start: accuracy.correct("consumption", value, start, now),
                temperatures=self.temperatures,
                temperature=self.temperature_model,
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
        # Periodic full charges at the cheapest moment: part of every plan
        # (its final check adds them, so state of charge, grid and costs
        # count with them).
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
            together=self.charge_order,
            surplus=_surplus_fn(consumption, pv_plan),
        )
        forced = _forced_power(consumption, full_charges, now)
        forced_by = {
            start: {
                f.battery_id: round(w, 1)
                for f in full_charges
                if (w := _forced_power(consumption, [f], now).get(start, 0.0)) > 0
            }
            for start in forced
        }
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
                        forced=forced,
                        forced_by=forced_by,
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
        self.plan_fallback = selected is None and self.plan_mode not in PLAN_MODES
        if self.plan_fallback:
            # The chosen own planner is gone or failed: zero on the meter.
            selected = plans.get(MODE_NOM)
        battery = selected.slots if selected else []

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
            night_starts(consumption, pv_plan)
            if self.rules.night_reserve_soc
            else set(),
            export_prices,
        )
        self._explain_method(data)
        self._log_prices(
            [p for p in prices if not p.estimated], battery, now, export_prices
        )
        # The plan last: it is what *Last decision* should show after a cycle.
        self._explain_plan(data)

        # 5. Remember the raw consumption predictions, also of every
        # forecaster on its own (to compare them).
        accuracy.record(
            "consumption", [(s.start, s.end, s.raw) for s in consumption], now
        )
        self._record_forecasters(window, step, now)
        self._record_heating(window, step, now)
        self.hass.bus.async_fire(EVENT_FORECAST_UPDATED, summarise(data))
        return data

    def _record_forecasters(
        self, window: PlanningWindow, step: timedelta, now: datetime
    ) -> None:
        """Each forecaster's own prediction, for the comparison of accuracy."""
        records = self.forecast_records()
        for key, forecaster in (*FORECASTERS.items(), *self.forecasters.items()):
            try:
                slots = raw_forecast(
                    forecaster,
                    records,
                    window,
                    step,
                    now,
                    temperatures=self.temperatures,
                    temperature=self.temperature_model,
                )
            except Exception:
                _LOGGER.exception("Consumption forecaster %s failed", key)
                self._forecaster_failed(key)
                continue
            kind = f"{FORECASTER_KIND}{key}"
            self.accuracy.track(kind)
            self.accuracy.record(kind, [(a, b, v) for a, b, v, _m in slots], now)

    def _record_heating(
        self, window: PlanningWindow, step: timedelta, now: datetime
    ) -> None:
        """The heating/cooling power the temperature step expects per slot,
        to check it afterwards against the measured heating/cooling devices
        (only when they are measured apart, not for the whole house). The
        last slot ends with the window (it may be shorter than a step)."""
        model = self.temperature_model
        if (
            model is None
            or not model.active
            or getattr(model, "target", "zone") == "avg_w"
            or not self.temperature_slots
        ):
            return
        slots = [
            (start, min(start + step, window.end), demand)
            for start, temp in self.temperature_slots
            if (demand := model.demand(start, temp)) is not None
        ]
        if slots:
            self.accuracy.track(HEATING_KIND)
            self.accuracy.record(HEATING_KIND, slots, now)

    def forecast_records(self) -> list:
        """The history the forecasts learn from: without random short peaks
        when that is switched on (regular ones stay)."""
        if not self.spike_history:
            return self.history.records
        return without_spikes(self.history.records, self.regular_peaks)

    def spike_ignore_w(self, ignore_w: float, now: datetime) -> float:
        """The part of the consumption zero on the meter does not discharge
        for: a random short peak (when switched on; regular peaks are covered)."""
        if not self.spike_battery or is_regular(self.regular_peaks, now):
            return 0.0
        return ignore_w

    def _correct_pv(self, raw: dict[datetime, float], now: datetime) -> dict:
        """The PV forecast after the chosen PV correction module (when the
        learned correction is on); every correction is also recorded on its
        own, to compare them."""
        if not raw or self.pv_correction not in (
            PV_CORRECTION_AUTO,
            PV_CORRECTION_BOTH,
        ):
            return {start: round(wh, 1) for start, wh in raw.items()}
        accuracy = self.accuracy
        data = PvCorrectionInput(
            now,
            sorted(raw.items()),
            accuracy.pv_results(),
            lambda start: accuracy.lead_factor(start, now),
            accuracy.bucket_factors(now),
        )
        results: dict[str, list[float]] = {}
        for key, corrector in (*PV_CORRECTORS.items(), *self.pv_correctors.items()):
            try:
                results[key] = apply_pv_correction(corrector, data)
            except Exception:  # an own module may fail in any way
                _LOGGER.exception("PV correction %s failed", key)
                self._pv_corrector_failed(key)
                continue
            kind = f"{PV_CORRECTOR_KIND}{key}"
            accuracy.track(kind)
            accuracy.record(
                kind,
                [
                    (start, start + PV_PERIOD, wh)
                    for (start, _), wh in zip(data.slots, results[key], strict=True)
                ],
                now,
            )
        # A user's manual or switched off correction (action) is followed as
        # it is: the correction per lead time only.
        key = (
            self.pv_corrector_key
            if accuracy.mode("pv", now) == "learned"
            else LeadTimeCorrector.key
        )
        values = results.get(key)
        self.pv_corrector_fallback = values is None
        if values is None:
            values = results.get(LeadTimeCorrector.key) or [
                wh * data.lead_factor(start) for start, wh in data.slots
            ]
        return {
            start: round(wh, 1)
            for (start, _), wh in zip(data.slots, values, strict=True)
        }

    def _pv_corrector_failed(self, key: str) -> None:
        if key in self._failed_pv_correctors:
            return
        self._failed_pv_correctors.add(key)
        self._decisions.async_log(
            "forecast", "pv_corrector_failed", name=self.pv_corrector_name(key)
        )

    def pv_corrector_name(self, key: str) -> str:
        """Name of a PV correction for the user."""
        corrector = self.pv_correctors.get(key) or PV_CORRECTORS.get(key)
        return (corrector.name if corrector else "") or key

    def _forecaster_failed(self, key: str) -> None:
        if key in self._failed_forecasters:
            return
        self._failed_forecasters.add(key)
        forecaster = self.forecasters.get(key)
        self._decisions.async_log(
            "forecast",
            "forecaster_failed",
            name=(forecaster.name if forecaster else "") or key,
        )

    def forecaster_name(self, key: str) -> str:
        """Name of a consumption forecaster for the user."""
        forecaster = self.forecasters.get(key) or FORECASTERS.get(key)
        return (forecaster.name if forecaster else "") or key

    def tariff_name(self, key: str) -> str:
        """Name of a tariff for the user."""
        tariff = self.tariffs.get(key) or TARIFFS.get(key)
        return (tariff.name if tariff else "") or key

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
        celsius = state_to_celsius(temp)  # °F sensors converted
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
        surplus_at = _surplus_fn(consumption, pv)
        factor = self.export_factor

        def price(start: datetime, import_price: float, power: float) -> float:
            share = min(surplus_at(start) / power, 1.0) if power > 0 else 0.0
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

    async def _async_read_market(self, now: datetime) -> list[PricePoint]:
        """Bare market prices of the price source (driver with a market
        role), else the export prices when those are the bare market price."""
        driver, _source = split_key(self.price_source)
        offered = {s.key: s for s in (driver.find(self.hass) if driver else [])}
        source = offered.get(self.price_source)
        if source is not None and ROLE_MARKET in source.roles:
            data = await self._async_read_driver(self.price_source, ROLE_MARKET)
            return [p for p in data.points if p.end > now]
        if self.export_mode == EXPORT_MARKET:
            return await self._async_read_export_prices(now)
        return []

    async def _async_apply_tariff(
        self,
        prices: list[PricePoint],
        export_prices: list[PricePoint],
        now: datetime,
        unit: str | None,
    ) -> tuple[list[PricePoint], list[PricePoint]]:
        """Import and export prices after the chosen tariff (checked)."""
        tariff = self.tariffs.get(self.tariff_key) or TARIFFS.get(self.tariff_key)
        self.tariff_fallback = tariff is None
        tariff = tariff or TARIFFS[DEFAULT_TARIFF]
        if tariff.key == DEFAULT_TARIFF and isinstance(tariff, SourceTariff):
            return prices, export_prices
        market = self.market_prices if tariff.needs_market else []
        try:
            return apply_tariff(
                tariff,
                prices,
                export_prices,
                market,
                now,
                unit,
                self.export_factor,
                {
                    CONF_TARIFF_SURCHARGE: float(
                        self.config_entry.options.get(CONF_TARIFF_SURCHARGE, 0.0)
                    ),
                    CONF_TARIFF_ENERGY_TAX: float(
                        self.config_entry.options.get(CONF_TARIFF_ENERGY_TAX, 0.0)
                    ),
                    CONF_TARIFF_VAT: float(
                        self.config_entry.options.get(
                            CONF_TARIFF_VAT, DEFAULT_TARIFF_VAT
                        )
                    ),
                },
            )
        except Exception:  # an own tariff module may fail in any way
            _LOGGER.exception("Tariff %s failed", self.tariff_key)
            self.tariff_fallback = True
            if self.tariff_key not in self._failed_tariffs:
                self._failed_tariffs.add(self.tariff_key)
                self._decisions.async_log(
                    "planning",
                    "tariff_failed",
                    name=(tariff.name or self.tariff_key),
                )
            return prices, export_prices

    async def _async_read_driver(self, key: str, role: str) -> PriceData:
        driver, source = split_key(key)
        if driver is None:
            return PriceData([])
        try:
            data = await driver.async_read(self.hass, source, role)
        except Exception:  # an unverified source must not stop the whole cycle
            _LOGGER.exception("Price source %s (%s) failed", key, role)
            return PriceData([])
        return PriceData(*per_kwh(data.points, data.unit, self.hass.config.currency))

    async def _async_read_prices(
        self, now: datetime
    ) -> tuple[list[PricePoint], str | None]:
        """Import prices: price driver or sensor, plus an optional extension."""
        if self.price_source != PRICE_SOURCE_SENSOR:
            data = await self._async_read_driver(self.price_source, ROLE_IMPORT)
            prices, unit = data.points, data.unit
        elif self.price_entity:
            state = self.hass.states.get(self.price_entity)
            prices, unit = per_kwh(
                parse_price_forecast(state),
                state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) if state else None,
                self.hass.config.currency,
            )
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
        if self._export_market_only:
            # The price sensor itself: only real market attributes; without
            # them the export price is the import price x the export factor.
            def parse(state):
                return parse_price_forecast(state, MARKET_ATTRIBUTES)
        else:
            parse = (
                parse_market_forecast
                if self.export_mode == EXPORT_MARKET
                else parse_price_forecast
            )
        return [
            p
            for p in merge_price_forecasts(
                [
                    per_kwh(
                        parse(state),
                        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                        if state
                        else None,
                        self.hass.config.currency,
                    )[0]
                    for state in (self.hass.states.get(e) for e in self.export_entities)
                ]
            )
            if p.end > now
        ]

    async def _async_read_pv(self, now: datetime) -> dict[datetime, float]:
        if not self.pv_entries:
            return {}
        forecast = await async_read_pv_forecasts(
            self.hass, self.pv_entries, self.pv_sources
        )
        return {start: wh for start, wh in forecast.items() if start + PV_PERIOD > now}

    def _explain_corrections(self, now: datetime) -> None:
        """Explain when the correction of a forecast changes noticeably."""
        for kind in KINDS:
            mode = self.accuracy.mode(kind, now)
            stats = self.accuracy.stats(kind).get("6-24h")
            if stats is not None and not stats.samples:
                stats = None
            correction = self.accuracy.correction_for(kind, "6-24h", now)
            if (
                mode == "off"
                or (
                    kind == "pv"
                    and self.pv_correction
                    not in (PV_CORRECTION_AUTO, PV_CORRECTION_BOTH)
                )
                or correction is None
                or (mode == "learned" and (stats is None or stats.strength < 1))
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
                mode=f"@mode_{mode}",
                correction=text,
                samples=stats.samples if stats else 0,
            )

    def _explain_price_surprises(self, surprises: list[PriceSurprise]) -> None:
        """One message when published prices differ strongly from the
        estimates the plan used."""
        if not surprises:
            return
        biggest = surprises[0]
        currency, language = self.hass.config.currency, self.hass.config.language
        self._decisions.async_log(
            "forecast",
            "price_published_differs",
            count=len(surprises),
            start=biggest.start,
            end=biggest.end,
            estimate=_price(biggest.estimate, currency, language),
            published=_price(biggest.published, currency, language),
        )

    def _explain_full_charges(self, full_charges: list[FullCharge]) -> None:
        """Explain newly planned or moved full charges."""
        key = "|".join(f"{f.battery_id}@{f.start.isoformat()}" for f in full_charges)
        if key == self._last_full_charges:
            return
        self._last_full_charges = key
        now = dt_util.utcnow()
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
                price=_price(
                    charge.price, self.hass.config.currency, self.hass.config.language
                ),
                avg_price=_price(
                    charge.avg_price,
                    self.hass.config.currency,
                    self.hass.config.language,
                ),
            )

    def _explain_plan(self, data: ForecastData) -> None:
        """Explain the plan in plain language when it changes noticeably
        (always after a recalculation by hand)."""
        forced, self.explain_next = self.explain_next, False
        plan = data.selected_plan
        if plan is None or not plan.slots:
            return
        if data.battery:
            # Tell the plan as it is used: with the periodic full charges.
            plan = replace(plan, slots=data.battery)
        now = dt_util.utcnow()
        states = list(self.battery_states())
        reserve = self.rules.reserve_soc
        min_soc_reached = bool(states) and all(
            s.soc is not None and s.soc <= max(s.config.min_soc, reserve) + 0.5
            for s in states
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
            self.hass.config.currency,
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
        # The next charge that has not started yet (a running charge moves
        # its first slot every slot boundary; that is no new story).
        next_charge = next(
            (
                s.start
                for prev, s in zip(plan.slots, plan.slots[1:], strict=False)
                if s.start > now and s.power_w > 100 and prev.power_w <= 100
            ),
            None,
        )
        band = round((plan.saving or 0.0) / 0.25)  # saving in steps of 0.25
        key = f"{plan.mode}|{action}|{next_charge}|{band}"
        if key == self._last_plan and not forced:
            return
        self._last_plan = key
        self._decisions.async_log("planning", "battery_plan_story", text=text)

    def outdoor_temperature(self) -> float | None:
        """The outdoor temperature now (°C): the sensor, else the weather
        entity; None when neither is set up or known."""
        if self.outdoor_sensor:
            value = valid_temperature(
                state_to_celsius(self.hass.states.get(self.outdoor_sensor))
            )
            if value is not None:
                return value
        if self.weather is None:
            return None
        try:
            return valid_temperature(self.weather.temperature_now(self.hass))
        except Exception:  # an own weather source may fail in any way
            _LOGGER.exception("Weather source %s failed", self.weather_key)
            return None

    async def _async_read_temperature(
        self, window: PlanningWindow, step: timedelta, now: datetime
    ) -> None:
        """Learn the temperature effect and read the forecast per slot
        (only when a weather entity is set up)."""
        if self.weather is None:
            self.temperature_model = self.temperatures = None
            self.temperature_slots = []
            self.weather_end = None
            return
        self.temperature_model = fit_effect(
            self.forecast_records(), now, {z.zone_id: z.name for z in self.zones}
        )
        try:
            hourly = checked_forecast(await self.weather.async_forecast(self.hass))
        except Exception:  # a weather source may fail in any way
            _LOGGER.exception("Weather forecast of %s failed", self.weather.describe())
            hourly = {}
        self.weather_end = max(hourly) + timedelta(hours=1) if hourly else None
        slots = list(window.slots(step))
        self.temperatures = slot_temperatures(slots, hourly) if hourly else None
        self.temperature_slots = [
            (start, temp)
            for (start, _end), temp in zip(slots, self.temperatures or [], strict=False)
        ]
        self._explain_temperature(bool(hourly))

    def _explain_temperature(self, has_forecast: bool) -> None:
        """Tell what was learned about the temperature (when it changes
        noticeably): for the house, or per zone."""
        effect = self.temperature_model
        messages: list[tuple[str, dict[str, Any]]] = []
        if not has_forecast:
            messages.append(("temperature_no_forecast", {}))
        elif effect is None:
            messages.append(("temperature_learning", {}))
        elif not effect.active:
            messages.append(("temperature_no_effect", {"days": effect.days}))
        else:
            for model in effect.models:
                heat, cool = model.heat_w_per_deg > 0, model.cool_w_per_deg > 0
                key = (
                    "temperature_effect"
                    if heat and cool
                    else "temperature_effect_heat"
                    if heat
                    else "temperature_effect_cool"
                    if cool
                    else "temperature_no_effect"
                )
                params: dict[str, Any] = {
                    "heat": round(model.heat_w_per_deg / 10) * 10,
                    "cool": round(model.cool_w_per_deg / 10) * 10,
                    "days": model.days,
                    "base": _degrees(model.heating_point),
                }
                if model.name:
                    key = key.replace("temperature_", "temperature_zone_", 1)
                    params["name"] = model.name
                messages.append((key, params))
                if model.usual_indoor:
                    messages.append(self._room_message(model))
        gist = "|".join(
            f"{key}:{p.get('name')}:{p.get('heat')}:{p.get('cool')}:"
            f"{p.get('base')}:{p.get('day')}:{p.get('night')}:{p.get('days')}"
            for key, p in messages
        )
        if gist == self._last_temperature:
            return
        self._last_temperature = gist
        for key, params in messages:
            self._decisions.async_log("forecast", key, **params)

    def _room_message(self, model: TemperatureModel) -> tuple[str, dict[str, Any]]:
        """The learned room temperature: per day of the week when the days
        differ (e.g. working from home), else one value."""
        params: dict[str, Any] = {
            "name": model.name,
            "day": _degrees(model.room_temperature(day=True)),
            "night": _degrees(model.room_temperature(day=False)),
        }
        per_day = [
            _degrees(model.room_temperature(day=True, weekday=d)) for d in range(7)
        ]
        if max(per_day) - min(per_day) < 1:
            return "temperature_room", params
        lang = (self.hass.config.language or "en").split("-")[0].lower()
        names = STORY_DAYS.get(lang, STORY_DAYS["en"])
        params["days"] = " · ".join(f"{names[d]} {t}" for d, t in enumerate(per_day))
        return "temperature_room_days", params

    def _explain_method(self, data: ForecastData) -> None:
        """Explain on which history the consumption forecast is based."""
        method = data.consumption_method or "none"
        if method == self._last_method:
            return
        if self._last_method is None and method == "none":
            # The first cycle after a start may run before the history is
            # read: not worth a message (a real "none" follows the plan story).
            self._last_method = method
            return
        self._last_method = method
        days = round(
            sum(r["minutes"] * r["coverage"] for r in self.history.records) / 1440
        )
        if method in (*METHODS, "none"):
            self._decisions.async_log(
                "forecast", f"consumption_method_{method}", days=days
            )
            return
        forecaster = self.forecasters.get(self.forecaster_key) or FORECASTERS.get(
            self.forecaster_key
        )
        self._decisions.async_log(
            "forecast",
            "consumption_method_module",
            name=(forecaster.name if forecaster else "") or method,
            days=days,
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
        if window.limited_by in (HorizonLimit.NO_PRICE, HorizonLimit.NO_PV) and (
            not self.hass.is_running
            or dt_util.utcnow() - self._started_at < STARTUP_GRACE
        ):
            return  # starting up: the forecasts usually follow within a minute
        self._last_limit = window.limited_by
        self._decisions.async_log(
            "planning",
            f"horizon_{window.limited_by}",
            end=window.end,
            hours=round(window.hours),
            days=self.max_days,
            entity=self.price_entity or self.price_source,
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


def _export_at(
    export_prices: Sequence[PricePoint], slots: Sequence[Any]
) -> Callable[[datetime], float | None]:
    """What export earns at a moment: the export price period holding it
    (quarter prices stay quarters), else the plan slot holding it."""

    def at(when: datetime) -> float | None:
        for p in export_prices:
            if p.start <= when < p.end:
                return p.price
        for s in slots:
            if s.start <= when < s.end:
                return s.export_price
        return None

    return at


def _surplus_fn(
    consumption: list[ForecastSlot], pv: Mapping[datetime, float]
) -> Callable[[datetime], float]:
    """The expected solar surplus (W) at a moment: PV of its hour minus the
    consumption of its slot; nothing after the consumption forecast."""
    surplus: dict[datetime, float] = {}
    for slot in consumption:
        hour = slot.start.replace(minute=0, second=0, microsecond=0)
        surplus[slot.start] = max(pv.get(hour, 0.0) - slot.power_w, 0.0)
    starts = sorted(surplus)
    last_end = consumption[-1].end if consumption else None

    def surplus_at(start: datetime) -> float:
        if last_end is None or start >= last_end:
            return 0.0
        k = bisect_right(starts, start) - 1
        return surplus[starts[k]] if k >= 0 else 0.0

    return surplus_at


def _forced_power(
    consumption: list[ForecastSlot],
    full_charges: list[FullCharge],
    now: datetime | None = None,
) -> dict[datetime, float]:
    """The full charges as extra charge power per consumption slot start (W,
    averaged over the part of the slot they cover; the slot now only from
    now, as the plan counts it)."""
    forced: dict[datetime, float] = {}
    for slot in consumption:
        begin = max(slot.start, now) if now is not None else slot.start
        seconds = (slot.end - begin).total_seconds()
        if seconds <= 0:
            continue
        extra = sum(
            f.power_w
            * max((min(slot.end, f.end) - max(begin, f.start)).total_seconds(), 0.0)
            / seconds
            for f in full_charges
            if begin < f.end and slot.end > f.start
        )
        if extra > 0:
            forced[slot.start] = round(extra, 1)
    return forced


def _avg_price(
    slots: list[PlanSlot], *, charging: bool, threshold: float = 100.0
) -> float | None:
    """Energy weighted average price while the plan charges / discharges."""
    total = weight = 0.0
    for slot in slots:
        active = slot.power_w > threshold if charging else slot.power_w < -threshold
        if not active or slot.price is None:
            continue
        energy = abs(slot.power_w) * slot.duration_h
        total += slot.price * energy
        weight += energy
    return total / weight if weight else None


def _price(
    value: float | None, currency: str | None, language: str | None = None
) -> str:
    """A price per kWh (in the main currency) for a message."""
    return format_money(value, currency, language)


def _plan_efficiency(states: Iterable[BatteryState]) -> float:
    """Capacity weighted round-trip efficiency of the batteries."""
    usable = [s for s in states if s.soc is not None]
    capacity = sum(s.config.capacity_kwh for s in usable)
    if not capacity:
        return 1.0
    return sum(s.config.efficiency * s.config.capacity_kwh for s in usable) / capacity


def _degrees(value: float) -> int:
    """A temperature for a message: whole degrees."""
    return round(value)
