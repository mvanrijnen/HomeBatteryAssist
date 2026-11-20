"""Home batteries: configuration, live state and monitoring counters.

A battery is linked read-only through entities of its own integration (state
of charge and power sensors), so any brand works and the integration that owns
the battery is never disturbed. HomeBatteryAssist never controls a battery.
Battery power is normalised to: positive = charging, negative = discharging.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, NotRequired, TypedDict

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
    async_track_utc_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ...const import (
    BATTERY_METER_NONE,
    CONF_BATTERY_METER,
    CONF_BATTERY_METER_ADDRESS,
    CONF_CAPACITY,
    CONF_CYCLE_COST,
    CONF_EFFICIENCY,
    CONF_FULL_CHARGE_INTERVAL,
    CONF_INITIAL_SOC,
    CONF_LOSS_MAX,
    CONF_LOSS_MIN,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_PHASE,
    CONF_POWER_SENSOR,
    CONF_POWER_SIGN,
    CONF_SOC_SENSOR,
    CONF_TEMPERATURE_SENSOR,
    CONF_TWIN_OF,
    DEFAULT_CYCLE_COST,
    DEFAULT_EFFICIENCY,
    DEFAULT_FULL_CHARGE_INTERVAL,
    DEFAULT_INITIAL_SOC,
    DEFAULT_LOSS_MAX,
    DEFAULT_LOSS_MIN,
    DEFAULT_MAX_SOC,
    DEFAULT_MIN_SOC,
    DOMAIN,
    FULL_CHARGE_SOC,
    IDLE_THRESHOLD_W,
    PHASE_NONE,
    SIGN_CHARGING_POSITIVE,
    SIGN_DISCHARGING_POSITIVE,
    SUBENTRY_BATTERY,
    SUBENTRY_VIRTUAL_BATTERY,
    TWIN_NONE,
    VALUE_BASIS,
)
from ..explain import DecisionLog
from ..units import parse_float, state_to_watts

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SOC_LOG_RETENTION = timedelta(days=7)
# Measured round-trip efficiency: from the counters over (at most) this many
# days, once at least one full capacity was charged through the battery.
EFFICIENCY_DAYS = 30
EFFICIENCY_MIN_CYCLES = 1.0
EFFICIENCY_MAX_STORED_SHARE = 0.25  # |change of stored energy| / charged
SAVE_DELAY = 60  # seconds
# A real battery's activity (charging / discharging / idle) is explained once
# it has lasted this long, so short swings are not logged.
ACTIVITY_SETTLE = timedelta(minutes=5)
STARTUP_DELAY = timedelta(minutes=1)  # then tell what each battery is doing
ACTIVITY_THRESHOLD_W = 50.0  # |power| above this counts as charging/discharging
# A battery power sensor not reported anew for POWER_STALE while it shows at
# least BATTERY_STALE_W is frozen (its integration hangs): unknown, not a
# power that keeps being counted. Near 0 W it is left alone (an idle battery
# may not be reported anew).
POWER_STALE = timedelta(seconds=90)
BATTERY_STALE_W = 50.0
FROZEN_CHECK = timedelta(seconds=15)
# A sensor reported less often (a slow or cloud integration) gets longer:
# frozen only after FROZEN_GAPS times its longest recent report interval.
FROZEN_GAPS = 3
MAX_GAP_S = 600.0  # the longest report interval learned (s)
# Not frozen in the first minutes after a start (integrations reconnecting).
FROZEN_QUIET = timedelta(minutes=2)
GAPS_KEY = f"{DOMAIN}_power_report_gaps"  # hass.data: entity -> seconds
QUIET_KEY = f"{DOMAIN}_power_quiet_until"  # hass.data: datetime


def activity_of(power_w: float) -> str:
    """``charging`` / ``discharging`` / ``idle`` for a power (+ charging)."""
    if power_w > ACTIVITY_THRESHOLD_W:
        return "charging"
    if power_w < -ACTIVITY_THRESHOLD_W:
        return "discharging"
    return "idle"


def clock(when: datetime) -> str:
    """Local time as ``HH:MM`` today, else ``dd-mm HH:MM``."""
    local = dt_util.as_local(when)
    if local.date() == dt_util.now().date():
        return f"{local:%H:%M}"
    return f"{local:%d-%m %H:%M}"


def plan_comparison(actual: str, planned_w: float | None) -> str:
    """How a battery's activity compares with the plan right now: ``same``,
    ``charge`` / ``discharge`` / ``idle`` (what the plan said instead) or
    ``none`` (no plan)."""
    if planned_w is None:
        return "none"
    planned = activity_of(planned_w)
    if planned == actual:
        return "same"
    return {"charging": "charge", "discharging": "discharge"}.get(planned, "idle")


class BatteryStatus(StrEnum):
    """What the battery is doing."""

    CHARGING = "charging"
    DISCHARGING = "discharging"
    IDLE = "idle"


@dataclass(frozen=True, slots=True)
class BatteryConfig:
    """Static properties of one battery (from its subentry)."""

    id: str  # subentry id
    name: str
    soc_sensor: str
    power_sensor: str
    power_sign: str
    capacity_kwh: float
    max_charge_w: float
    max_discharge_w: float
    min_soc: float
    max_soc: float
    efficiency: float  # round trip, 0..1
    full_charge_interval_days: int  # 0 = no periodic full charge
    phase: str
    virtual: bool = False  # simulated what-if battery, no sensors
    temperature_sensor: str = ""  # optional, for derating the power
    initial_soc: float = DEFAULT_INITIAL_SOC
    loss_min: float = 0.0  # virtual: round-trip loss range (fraction)
    loss_max: float = 0.0
    # External meter on the battery's line (driver key, address): its power
    # (+ into the battery = charging) is used instead of the power sensor.
    meter_driver: str = ""
    meter_address: str = ""
    # Virtual: the real battery (subentry id) this one is the twin of.
    twin_of: str = ""

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> BatteryConfig:
        """Build from subentry data."""
        data: Mapping[str, Any] = subentry.data
        virtual = subentry.subentry_type == SUBENTRY_VIRTUAL_BATTERY
        loss_min = float(data.get(CONF_LOSS_MIN, DEFAULT_LOSS_MIN)) / 100
        loss_max = float(data.get(CONF_LOSS_MAX, DEFAULT_LOSS_MAX)) / 100
        efficiency = (
            1 - (loss_min + loss_max) / 2
            if virtual
            else float(data.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)) / 100
        )
        return cls(
            id=subentry.subentry_id,
            name=data[CONF_NAME],
            soc_sensor="" if virtual else data[CONF_SOC_SENSOR],
            power_sensor="" if virtual else data[CONF_POWER_SENSOR],
            power_sign=data.get(CONF_POWER_SIGN, SIGN_CHARGING_POSITIVE),
            capacity_kwh=float(data[CONF_CAPACITY]),
            max_charge_w=float(data[CONF_MAX_CHARGE_POWER]),
            max_discharge_w=float(data[CONF_MAX_DISCHARGE_POWER]),
            min_soc=float(data.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)),
            max_soc=float(data.get(CONF_MAX_SOC, DEFAULT_MAX_SOC)),
            efficiency=efficiency,
            full_charge_interval_days=int(
                data.get(CONF_FULL_CHARGE_INTERVAL, DEFAULT_FULL_CHARGE_INTERVAL)
            ),
            phase=data.get(CONF_PHASE, PHASE_NONE),
            virtual=virtual,
            temperature_sensor=data.get(CONF_TEMPERATURE_SENSOR) or "",
            initial_soc=float(data.get(CONF_INITIAL_SOC, DEFAULT_INITIAL_SOC)),
            loss_min=loss_min if virtual else 0.0,
            loss_max=loss_max if virtual else 0.0,
            meter_driver=(
                ""
                if virtual
                or data.get(CONF_BATTERY_METER, BATTERY_METER_NONE)
                == BATTERY_METER_NONE
                else data[CONF_BATTERY_METER]
            ),
            meter_address="" if virtual else data.get(CONF_BATTERY_METER_ADDRESS, ""),
            twin_of=(
                twin
                if virtual and (twin := data.get(CONF_TWIN_OF)) and twin != TWIN_NONE
                else ""
            ),
        )

    def as_twin_of(self, real: BatteryConfig) -> BatteryConfig:
        """This virtual battery as the twin of ``real``: its properties (the
        loss fixed at the real battery's round-trip efficiency)."""
        loss = 1 - real.efficiency
        return replace(
            self,
            capacity_kwh=real.capacity_kwh,
            max_charge_w=real.max_charge_w,
            max_discharge_w=real.max_discharge_w,
            min_soc=real.min_soc,
            max_soc=real.max_soc,
            efficiency=real.efficiency,
            full_charge_interval_days=real.full_charge_interval_days,
            phase=real.phase,
            temperature_sensor=real.temperature_sensor,
            loss_min=loss,
            loss_max=loss,
        )


@dataclass(frozen=True, slots=True)
class BatteryState:
    """Live values of one battery, derived quantities via the config."""

    config: BatteryConfig
    soc: float | None  # %
    power_w: float | None  # + charging / - discharging

    @property
    def available(self) -> bool:
        """True when both state of charge and power are known."""
        return self.soc is not None and self.power_w is not None

    @property
    def status(self) -> BatteryStatus | None:
        """Charging, discharging or idle."""
        if self.power_w is None:
            return None
        if self.power_w > IDLE_THRESHOLD_W:
            return BatteryStatus.CHARGING
        if self.power_w < -IDLE_THRESHOLD_W:
            return BatteryStatus.DISCHARGING
        return BatteryStatus.IDLE

    def _energy(self, from_soc: float, to_soc: float) -> float | None:
        if self.soc is None:
            return None
        return round(max(to_soc - from_soc, 0.0) * self.config.capacity_kwh / 100, 3)

    @property
    def stored_kwh(self) -> float | None:
        """Energy in the battery."""
        return self._energy(0.0, self.soc) if self.soc is not None else None

    @property
    def usable_kwh(self) -> float | None:
        """Energy that may be discharged (above the minimum state of charge)."""
        return (
            self._energy(self.config.min_soc, self.soc)
            if self.soc is not None
            else None
        )

    @property
    def room_kwh(self) -> float | None:
        """Energy that may still be charged (up to the maximum state of charge)."""
        return (
            self._energy(self.soc, self.config.max_soc)
            if self.soc is not None
            else None
        )

    def time_to_target(self, now: datetime) -> datetime | None:
        """When the battery is full (charging) or empty (discharging) at this power."""
        if self.status is BatteryStatus.CHARGING and self.room_kwh is not None:
            energy, power = self.room_kwh, self.power_w
        elif self.status is BatteryStatus.DISCHARGING and self.usable_kwh is not None:
            energy, power = self.usable_kwh, -self.power_w  # type: ignore[operator]
        else:
            return None
        when = now + timedelta(hours=energy * 1000 / power)  # type: ignore[operator]
        # To the minute: written every few seconds, a value in seconds would
        # be a new state (and recorder row) every time.
        return when.replace(second=0, microsecond=0)


def battery_configs(
    entry: ConfigEntry, *, include_virtual: bool = False
) -> list[BatteryConfig]:
    """Batteries configured as subentries (real; optionally also virtual ones).

    Virtual batteries never take part in measurements (house consumption).
    """
    types = (
        {SUBENTRY_BATTERY, SUBENTRY_VIRTUAL_BATTERY}
        if include_virtual
        else {SUBENTRY_BATTERY}
    )
    configs = [
        BatteryConfig.from_subentry(subentry)
        for subentry in entry.subentries.values()
        if subentry.subentry_type in types
    ]
    real = {c.id: c for c in configs if not c.virtual}
    return [
        c.as_twin_of(real[c.twin_of])
        if c.twin_of in real
        else replace(c, twin_of="")
        if c.virtual
        else c
        for c in configs
    ]


def twinned_ids(configs: list[BatteryConfig]) -> set[str]:
    """The real batteries that have a twin (left out of the plan)."""
    return {t for c in configs if c.virtual and (t := getattr(c, "twin_of", ""))}


def _soc(state: State | None) -> float | None:
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    value = parse_float(state.state)
    if value is None or not 0 <= value <= 100:
        return None
    return value


METERS_KEY = f"{DOMAIN}_battery_meters"  # hass.data: battery id -> DirectMeter


def battery_meter(hass: HomeAssistant, config: BatteryConfig) -> Any:
    """The running external meter of a battery, if it has one."""
    return hass.data.get(METERS_KEY, {}).get(config.id)


def battery_power(hass: HomeAssistant, config: BatteryConfig) -> float | None:
    """Battery power in W, + charging / - discharging, or None if unknown.

    From the battery's external meter when it has a value (+ into the battery),
    otherwise from the battery's power sensor.
    """
    meter = battery_meter(hass, config)
    if meter is not None and meter.available and meter.phase_w:
        return round(sum(meter.phase_w), 1)
    if power_frozen(hass, config):
        return None  # frozen at a real power: unknown, not counted on
    watts = state_to_watts(hass.states.get(config.power_sensor))
    if watts is None:
        return None
    return -watts if config.power_sign == SIGN_DISCHARGING_POSITIVE else watts


def power_frozen(
    hass: HomeAssistant, config: BatteryConfig, now: datetime | None = None
) -> bool:
    """The battery's power sensor is frozen at a real power (see
    ``POWER_STALE``); never with a working external meter or for a virtual
    battery."""
    if config.virtual or not config.power_sensor:
        return False
    meter = battery_meter(hass, config)
    if meter is not None and meter.available and meter.phase_w:
        return False
    state = hass.states.get(config.power_sensor)
    if state is None:
        return False
    watts = state_to_watts(state)
    if watts is None or abs(watts) < BATTERY_STALE_W:
        return False
    now = now or dt_util.utcnow()
    if (quiet := hass.data.get(QUIET_KEY)) is not None and now < quiet:
        return False
    gap = hass.data.get(GAPS_KEY, {}).get(config.power_sensor, 0.0)
    stale = max(POWER_STALE, timedelta(seconds=FROZEN_GAPS * gap))
    seen = getattr(state, "last_reported", None) or state.last_updated
    return now - seen > stale


def read_battery(hass: HomeAssistant, config: BatteryConfig) -> BatteryState:
    """Read the current state of a battery."""
    return BatteryState(
        config, _soc(hass.states.get(config.soc_sensor)), battery_power(hass, config)
    )


class BatteryStats(TypedDict):
    """Monitoring counters of one battery, persisted."""

    charged_kwh: float
    discharged_kwh: float
    last_full_charge: str | None  # ISO 8601, UTC
    virtual_soc: NotRequired[float]  # simulated state of charge (virtual batteries)
    value: NotRequired[float]  # realised value: + saved / - cost, in the price unit
    value_since: NotRequired[str]  # ISO 8601: when the value counter started
    value_kwh: NotRequired[float]  # energy through the battery behind the value
    value_basis: NotRequired[int]  # how the value is counted (VALUE_BASIS)
    twin_of: NotRequired[str]  # virtual: the real battery it started as twin of
    # The counters at the start of each local day (newest last), for "today"
    # and the measured efficiency: {"date", "charged", "discharged", "stored",
    # "value"}.
    days: NotRequired[list[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class MeasuredEfficiency:
    """Round-trip efficiency measured from the battery's own counters."""

    pct: float  # discharged + change of stored energy, per charged kWh
    days: int  # over how many days
    charged_kwh: float


def today_energy(stats: Mapping[str, Any]) -> tuple[float, float] | None:
    """Charged and discharged energy (kWh) since the start of the local day."""
    days = stats.get("days") or []
    if not days:
        return None
    start = days[-1]
    return (
        round(stats["charged_kwh"] - start["charged"], 3),
        round(stats["discharged_kwh"] - start["discharged"], 3),
    )


def value_after_wear(stats: Mapping[str, Any], cycle_cost: float) -> float:
    """Realised value so far after wear (``cycle_cost`` per kWh through the
    battery), as the plan and the plan check count it."""
    return stats.get("value", 0.0) - stats.get("value_kwh", 0.0) * cycle_cost


def today_value(stats: Mapping[str, Any], cycle_cost: float = 0.0) -> float | None:
    """Realised value since the start of the local day, after wear (None
    before the first day start that knew it)."""
    days = stats.get("days") or []
    if not days or "value" not in days[-1]:
        return None
    start = days[-1]
    if "value_kwh" in start:
        kwh = stats.get("value_kwh", 0.0) - start["value_kwh"]
    else:  # a day start from before the energy per day: today's counters
        kwh = (stats["charged_kwh"] - start["charged"]) + (
            stats["discharged_kwh"] - start["discharged"]
        )
    return round(stats.get("value", 0.0) - start["value"] - kwh * cycle_cost, 4)


def measured_efficiency(
    stats: Mapping[str, Any], stored_kwh: float | None, capacity_kwh: float
) -> MeasuredEfficiency | None:
    """Round trip from the counters: (discharged + stored now - stored then)
    / charged, from the oldest day start that knew the stored energy.

    Only when at least ``EFFICIENCY_MIN_CYCLES`` capacity was charged and the
    stored energy changed little against it, so the guess for what is still
    inside hardly matters. Measured at the battery's AC side, like its power.
    """
    if stored_kwh is None or capacity_kwh <= 0:
        return None
    start = next(
        (d for d in stats.get("days") or [] if d.get("stored") is not None), None
    )
    if start is None:
        return None
    charged = stats["charged_kwh"] - start["charged"]
    discharged = stats["discharged_kwh"] - start["discharged"]
    stored = stored_kwh - start["stored"]
    if charged < EFFICIENCY_MIN_CYCLES * capacity_kwh:
        return None
    if abs(stored) > EFFICIENCY_MAX_STORED_SHARE * charged:
        return None
    pct = (discharged + stored) / charged * 100
    if not 30 <= pct <= 100:
        return None  # counters or state of charge not trustworthy
    return MeasuredEfficiency(
        round(pct, 1), len(stats.get("days") or []), round(charged, 2)
    )


def realised_value(
    battery_kwh: float,
    grid_kwh: float | None,
    price: float,
    export_price: float | None,
) -> float:
    """What a battery saved over an interval, without net metering.

    ``battery_kwh``: + charged / - discharged. ``grid_kwh``: grid energy with
    the battery (+ import / - export). Imported energy costs ``price``,
    exported energy earns ``export_price`` (None = the import price). So
    charging from solar power that would have been exported costs only its
    export value, and discharging saves the import price only for energy the
    house would otherwise have bought. Without a grid measurement every kWh
    counts at the import price.
    """
    export = price if export_price is None else export_price
    if grid_kwh is None:
        return -battery_kwh * price

    def cost(kwh: float) -> float:
        return kwh * price if kwh >= 0 else kwh * export

    return cost(grid_kwh - battery_kwh) - cost(grid_kwh)


class BatteryInput:
    """Follows all batteries: live state, energy counters and full charges."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, decisions: DecisionLog
    ) -> None:
        """Initialize."""
        self.hass = hass
        self._decisions = decisions
        self.configs = battery_configs(entry, include_virtual=True)
        # Wear per kWh through a battery: the realised value counts after it.
        self.cycle_cost: float = entry.options.get(CONF_CYCLE_COST, DEFAULT_CYCLE_COST)
        self.states: dict[str, BatteryState] = {
            c.id: BatteryState(c, None, None) for c in self.configs
        }
        self.stats: dict[str, BatteryStats] = {}
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.batteries"
        )
        self._last_power: dict[str, tuple[datetime, float]] = {}
        # Integral of the measured grid power (Wh) and its last reading, so a
        # stretch is valued against the grid's average over that stretch.
        self._grid_wh = 0.0
        self._grid_last: tuple[datetime, float] | None = None
        self._grid_at_start: dict[str, float | None] = {}
        self._was_available: dict[str, bool] = {}
        self._listeners: list[Callable[[], None]] = []
        self._unsub: CALLBACK_TYPE | None = None
        self._unsub_frozen: CALLBACK_TYPE | None = None
        self._reported: dict[str, datetime] = {}  # power sensors' last report
        self._unsub_log: CALLBACK_TYPE | None = None
        # Price (per kWh) at a moment (default now), set by the setup (from
        # the price forecast).
        self.price_now: Callable[..., float | None] = lambda *_: None
        # What exported energy earns at a moment (None = the import price).
        self.export_price_now: Callable[..., float | None] = lambda *_: None
        # Measured grid power right now, W (+ import / - export), real
        # batteries included, virtual batteries not.
        self.grid_now: Callable[[], float | None] = lambda: None
        # Planned power of all batteries right now, W (+ charging), if any.
        self.planned_now: Callable[[], float | None] = lambda: None
        # battery id -> explained activity, and a pending change with its timer
        self._activity: dict[str, str] = {}
        self._pending: dict[str, tuple[str, datetime, CALLBACK_TYPE]] = {}
        # battery id -> start of the current period with the counters then
        self._began: dict[str, tuple[datetime, float, float]] = {}
        self._startup: dict[str, CALLBACK_TYPE] = {}
        self._meter_unsubs: list[CALLBACK_TYPE] = []  # the one message after start-up
        # When the current activity is expected to end and why
        # (``empty``/``full``/``pv_end``/``pv_covers``), if known.
        self.expected_until: Callable[[str, str], tuple[datetime, str] | None] = (
            lambda battery_id, activity: None
        )
        # battery id -> [[ISO time, state of charge %], ...] every quarter, 7 days
        self.soc_log: dict[str, list[list[Any]]] = {}

    async def async_start(self) -> None:
        """Load counters and start following the battery sensors."""
        data = await self._store.async_load() or {}
        stored = data.get("stats", {})
        self.soc_log = {
            c.id: data.get("soc_log", {}).get(c.id, []) for c in self.configs
        }
        self._unsub_log = async_track_utc_time_change(
            self.hass, self._async_log_soc, minute="/15", second=0
        )
        # A frozen power sensor sends no event: look every FROZEN_CHECK.
        self.hass.data[QUIET_KEY] = dt_util.utcnow() + FROZEN_QUIET
        self._unsub_frozen = async_track_time_interval(
            self.hass, self._async_check_frozen, FROZEN_CHECK
        )
        for config in self.configs:
            self.stats[config.id] = BatteryStats(
                charged_kwh=0.0, discharged_kwh=0.0, last_full_charge=None
            ) | stored.get(config.id, {})
            stats = self.stats[config.id]
            stats.setdefault("first_seen", dt_util.utcnow().isoformat())
            # A counter stored as null (a nan once) would break every update.
            for key in ("charged_kwh", "discharged_kwh", "value", "value_kwh"):
                number = stats.get(key)
                if key in stats and (
                    not isinstance(number, (int, float)) or not math.isfinite(number)
                ):
                    stats[key] = 0.0
            if stats.get("value_basis") != VALUE_BASIS:
                # Older counters (net metering, or without the energy for the
                # wear): start again.
                stats.pop("value", None)
                stats.pop("value_since", None)
                stats.pop("value_kwh", None)
                stats["value_basis"] = VALUE_BASIS
                for day in stats.get("days") or []:
                    # The counters start again: so does today's value.
                    day["value"] = 0.0
                    day["value_kwh"] = 0.0
            days = stats.get("days") or []
            if days and "value" not in days[-1]:
                # A day start from before the value per day: today counts
                # from now (the value and the energy for its wear).
                days[-1]["value"] = round(stats.get("value", 0.0), 5)
                days[-1]["value_kwh"] = round(stats.get("value_kwh", 0.0), 4)
        await self._async_start_meters()
        entity_ids = [
            e
            for c in self.configs
            if not c.virtual
            for e in (c.soc_sensor, c.power_sensor)
        ]
        if entity_ids:
            self._unsub = async_track_state_change_event(
                self.hass, entity_ids, self._async_state_changed
            )
        now = dt_util.utcnow()
        # Real batteries first: a new twin starts at its real battery's state
        # of charge.
        for config in sorted(self.configs, key=lambda c: c.virtual):
            if config.virtual:
                stats = self.stats[config.id]
                soc = stats.get("virtual_soc")
                # New, or just made the twin of (another) real battery: start
                # where the real battery is.
                if soc is None or stats.get("twin_of", "") != config.twin_of:
                    soc = self._twin_start(config) if config.twin_of else soc
                    stats["twin_of"] = config.twin_of
                if soc is None:
                    soc = config.initial_soc
                self._update(config, now, BatteryState(config, soc, 0.0))
            else:
                self._update(config, now)

    def _twin_start(self, config: BatteryConfig) -> float:
        """Where a virtual battery starts: its real battery's state of charge
        for a twin (when known), else its initial state of charge."""
        real = self.states.get(config.twin_of) if config.twin_of else None
        if real is not None and real.soc is not None:
            return real.soc
        return config.initial_soc

    def plan_states(self) -> list[BatteryState]:
        """The batteries HomeBatteryAssist plans for: all, except the real
        batteries that have a twin (the twin is planned in their place)."""
        twinned = twinned_ids(self.configs)
        return [s for s in self.states.values() if s.config.id not in twinned]

    def sync_twin(self, battery_id: str) -> float | None:
        """Set a twin to its real battery's state of charge now; the new
        state of charge, or None when it is not known (nothing changed)."""
        config = next(c for c in self.configs if c.id == battery_id)
        real = self.states.get(config.twin_of) if config.twin_of else None
        if real is None or real.soc is None:
            return None
        self.set_virtual(battery_id, dt_util.utcnow(), 0.0, real.soc)
        self._decisions.async_log(
            "battery",
            "twin_synced",
            name=config.name,
            real=real.config.name,
            soc=round(real.soc),
        )
        return real.soc

    def charge_headroom_w(self) -> float:
        """What the real batteries could still charge on top of their power
        now (W): max charge power minus the charge now, for those not full."""
        total = 0.0
        for config in self.configs:
            if config.virtual:
                continue
            state = self.states[config.id]
            if state.soc is None or state.soc >= config.max_soc:
                continue
            total += max(config.max_charge_w - max(state.power_w or 0.0, 0.0), 0.0)
        return total

    def grid_planned_w(self) -> float | None:
        """The grid (W, + import) as HomeBatteryAssist's batteries make it:
        measured, with the virtual batteries, without the real batteries
        that have a twin (the twin acts in their place)."""
        grid = self.grid_now()
        if grid is None:
            return None
        twinned = twinned_ids(self.configs)
        for config in self.configs:
            power = self.states[config.id].power_w or 0.0
            if config.virtual:
                grid += power
            elif config.id in twinned:
                grid -= power
        return grid

    def value_today(self, battery_id: str) -> float | None:
        """Realised value (currency) today after wear, by HomeBatteryAssist's
        own counters."""
        return today_value(self.stats[battery_id], self.cycle_cost)

    def value(self, battery_id: str) -> float:
        """Realised value (currency) since ``value_since``, after wear."""
        return value_after_wear(self.stats[battery_id], self.cycle_cost)

    async def async_save_now(self) -> None:
        """Count up to now and write the counters (Home Assistant stops)."""
        self.count_up_to(dt_util.utcnow())
        await self._store.async_save(self._data())

    async def async_stop(self) -> None:
        """Stop following and persist the counters."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self._unsub_log is not None:
            self._unsub_log()
            self._unsub_log = None
        if self._unsub_frozen is not None:
            self._unsub_frozen()
            self._unsub_frozen = None
        for _activity, _began, cancel in self._pending.values():
            cancel()
        self._pending.clear()
        for cancel in self._startup.values():
            cancel()
        self._startup.clear()
        await self._async_stop_meters()
        # Count the energy up to now (else the last stretch before a reload or
        # restart is lost).
        now = dt_util.utcnow()
        for config in self.configs:
            if not config.virtual:
                self._count_energy(config.id, now, self.states[config.id].power_w)
        await self._store.async_save(self._data())

    async def _async_start_meters(self) -> None:
        """Start the external meters of the batteries that have one."""
        from ..devices.meters import get_driver  # devices: a lower layer

        meters = self.hass.data.setdefault(METERS_KEY, {})
        for config in self.configs:
            if config.virtual or not config.meter_driver or not config.meter_address:
                continue
            driver = get_driver(config.meter_driver)
            if driver is None:
                _LOGGER.warning(
                    "Unknown meter %s for battery %s", config.meter_driver, config.name
                )
                continue
            meter = driver.create(self.hass, config.meter_address)
            meters[config.id] = meter
            self._meter_unsubs.append(
                meter.async_add_listener(lambda when, c=config: self._update(c, when))
            )
            await meter.async_start()

    async def _async_stop_meters(self) -> None:
        meters = self.hass.data.get(METERS_KEY, {})
        for unsub in self._meter_unsubs:
            unsub()
        self._meter_unsubs.clear()
        for config in self.configs:
            if (meter := meters.pop(config.id, None)) is not None:
                meter.cancel_stale()
                await meter.async_stop()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call ``listener`` whenever a battery changes."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def full_charge_due(self, battery_id: str, now: datetime) -> datetime | None:
        """When the next periodic full charge is due, if configured."""
        config = next(c for c in self.configs if c.id == battery_id)
        if config.full_charge_interval_days <= 0:
            return None
        last = self.stats[battery_id]["last_full_charge"] or self.stats[battery_id].get(
            "first_seen"
        )
        if last is None:
            return now
        return dt_util.parse_datetime(last) + timedelta(  # type: ignore[operator]
            days=config.full_charge_interval_days
        )

    def full_charge_since(self, battery_id: str) -> str | None:
        """Since when the full charge interval counts: the last full charge,
        else when HomeBatteryAssist first saw the battery (a new battery is
        not overdue from the first minute)."""
        stats = self.stats.get(battery_id, {})
        return stats.get("last_full_charge") or stats.get("first_seen")

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        for config in self.configs:
            if entity_id in (config.soc_sensor, config.power_sensor):
                self._update(config, event.time_fired)

    @callback
    def set_virtual(
        self, battery_id: str, when: datetime, power_w: float, soc: float
    ) -> None:
        """Update a virtual battery from the simulation."""
        config = next(c for c in self.configs if c.id == battery_id)
        self.stats[battery_id]["virtual_soc"] = soc
        self._update(config, when, BatteryState(config, soc, power_w))

    @callback
    def _async_check_frozen(self, now: datetime) -> None:
        """A battery whose power sensor froze at a real power: unknown now
        (``power_frozen``), so its counters stop and the checks see it; and
        back as soon as it is reported again (also with the same value,
        which fires no state change). Learns how often each sensor is
        reported, so a slow integration is not taken for frozen."""
        gaps: dict[str, float] = self.hass.data.setdefault(GAPS_KEY, {})
        for config in self.configs:
            if config.virtual or not config.power_sensor:
                continue
            state = self.hass.states.get(config.power_sensor)
            reported = (
                (getattr(state, "last_reported", None) or state.last_updated)
                if state is not None
                else None
            )
            previous = self._reported.get(config.id)
            watts = state_to_watts(state)
            if (
                reported is not None
                and previous is not None
                and reported > previous
                # Only while it shows a real power (an idle sensor reporting
                # only on change would learn hours), at most MAX_GAP.
                and watts is not None
                and abs(watts) >= BATTERY_STALE_W
            ):
                gap = min((reported - previous).total_seconds(), MAX_GAP_S)
                gaps[config.power_sensor] = max(
                    gap, gaps.get(config.power_sensor, 0) * 0.9
                )
            if reported is not None:
                self._reported[config.id] = reported
            known = self.states[config.id].power_w is not None
            frozen = power_frozen(self.hass, config, now)
            if (known and frozen) or (
                not known
                and not frozen
                and battery_power(self.hass, config) is not None
            ):
                self._update(config, now)

    def _update(
        self, config: BatteryConfig, when: datetime, state: BatteryState | None = None
    ) -> None:
        previous = self.states[config.id]
        state = state or read_battery(self.hass, config)
        self.states[config.id] = state

        self._count_energy(config.id, when, state.power_w)
        if (
            state.soc is not None
            and state.soc >= FULL_CHARGE_SOC
            # Only a rise to full counts: not the first value after start-up
            # or after the sensor was unavailable.
            and previous.soc is not None
            and previous.soc < FULL_CHARGE_SOC
        ):
            self.stats[config.id]["last_full_charge"] = when.isoformat()
            self._decisions.async_log(
                "battery", "battery_full_charge", name=config.name
            )
        self._explain_availability(config, state.available)
        if not config.virtual:
            self._follow_activity(config, state.power_w)

        self._store.async_delay_save(self._data, SAVE_DELAY)
        for listener in list(self._listeners):
            listener()

    def _roll_day(self, battery_id: str, when: datetime) -> None:
        """Remember the counters at the start of a new local day."""
        stats = self.stats[battery_id]
        day = dt_util.as_local(when).date().isoformat()
        days = stats.setdefault("days", [])
        if days and days[-1]["date"] >= day:
            return  # this day (or a late event of the day before)
        stored = self.states[battery_id].stored_kwh
        days.append(
            {
                "date": day,
                "charged": stats["charged_kwh"],
                "discharged": stats["discharged_kwh"],
                "stored": None if stored is None else round(stored, 3),
                "value": round(stats.get("value", 0.0), 5),
                "value_kwh": round(stats.get("value_kwh", 0.0), 4),
            }
        )
        del days[:-EFFICIENCY_DAYS]

    def today(self, battery_id: str) -> tuple[float, float] | None:
        """Charged and discharged energy (kWh) today, by HomeBatteryAssist's
        own counters."""
        return today_energy(self.stats[battery_id])

    def efficiency(self, battery_id: str) -> MeasuredEfficiency | None:
        """Measured round-trip efficiency of a real battery, if known yet."""
        state = self.states[battery_id]
        if state.config.virtual:
            return None  # simulated: it is what is configured
        return measured_efficiency(
            self.stats[battery_id], state.stored_kwh, state.config.capacity_kwh
        )

    def _count_energy(
        self, battery_id: str, when: datetime, power: float | None
    ) -> None:
        """Integrate the previous power value up to ``when`` (kWh counters)."""
        last = self._last_power.get(battery_id)
        if last is not None and when < last[0]:
            return  # a late, older event: counted already
        if (last := self._last_power.pop(battery_id, None)) is not None:
            since, last_power = last
            kwh = last_power * max((when - since).total_seconds(), 0.0) / 3_600_000
            stats = self.stats[battery_id]
            if kwh > 0:
                # Unrounded: rounded on every short stretch (a meter every
                # second) the counters would run off, or not move at all.
                stats["charged_kwh"] = stats["charged_kwh"] + kwh
            elif kwh < 0:
                stats["discharged_kwh"] = stats["discharged_kwh"] - kwh
            # Realised value: what the grid would have cost without this
            # battery minus what it costs with it (no net metering).
            # The prices of the stretch itself (its middle): a stretch that
            # ends on a quarter boundary is not valued at the next quarter.
            middle = since + (when - since) / 2
            price = self.price_now(middle) if kwh else None
            if kwh and price is None:
                price = self.price_now(when)  # the middle's period already gone
            if kwh and price is not None:
                hours = max((when - since).total_seconds(), 0.0) / 3600
                start_wh = self._grid_at_start.get(battery_id)
                end_wh = self._grid_integral(when)
                grid_avg = (
                    (end_wh - start_wh) / hours
                    if start_wh is not None and end_wh is not None and hours > 0
                    else None
                )
                grid_kwh = self._grid_with_batteries(battery_id, last_power, grid_avg)
                stats.setdefault("value_since", when.isoformat())
                # Energy through the battery behind the value (for its wear).
                stats["value_kwh"] = stats.get("value_kwh", 0.0) + abs(kwh)
                export = (
                    self.export_price_now(middle)
                    if self.export_price_now(middle) is not None
                    else self.export_price_now(when)
                )
                grid_e = None if grid_kwh is None else grid_kwh * hours / 1000
                group_w = sum(self._group_powers(battery_id, last_power).values())
                if (
                    grid_e is not None
                    and abs(group_w) > abs(last_power) + 1e-6
                    and group_w * last_power > 0
                ):
                    # Several batteries the same way: valued together (the
                    # grid crosses zero only with all of them), this one its
                    # share by power; apart, the values would not add up.
                    joint = realised_value(
                        group_w * hours / 1000, grid_e, price, export
                    )
                    value = joint * last_power / group_w
                else:
                    value = realised_value(kwh, grid_e, price, export)
                stats["value"] = stats.get("value", 0.0) + value
        self._roll_day(battery_id, when)
        if power is not None:
            self._last_power[battery_id] = (when, power)
            self._grid_at_start[battery_id] = self._grid_integral(when)

    def note_grid(self, when: datetime, grid_w: float | None) -> None:
        """A new grid reading (W, None = unknown): integrated over time."""
        if self._grid_last is not None:
            since, value = self._grid_last
            self._grid_wh += value * max((when - since).total_seconds(), 0.0) / 3600
        self._grid_last = None if grid_w is None else (when, grid_w)
        if grid_w is None:
            # A gap: stretches across it are valued against the reading at
            # their end instead.
            self._grid_at_start = dict.fromkeys(self._grid_at_start)

    def _grid_integral(self, when: datetime) -> float | None:
        if self._grid_last is None:
            return None
        since, value = self._grid_last
        return self._grid_wh + value * max((when - since).total_seconds(), 0.0) / 3600

    def _group_powers(self, battery_id: str, last_power: float) -> dict[str, float]:
        """The powers (W) of the batteries valued together with ``battery_id``:
        the real ones (all in the measured grid), or the virtual ones (the
        simulated grid); ``battery_id`` at ``last_power``."""
        virtual = next(c for c in self.configs if c.id == battery_id).virtual
        out: dict[str, float] = {}
        for config in self.configs:
            if config.virtual != virtual:
                continue
            if config.id == battery_id:
                out[config.id] = last_power
            elif (power := self.states[config.id].power_w) is not None:
                out[config.id] = power
        return out

    def _grid_with_batteries(
        self, battery_id: str, last_power: float, grid_avg: float | None = None
    ) -> float | None:
        """Grid power (W) with all batteries, the virtual ones included, while
        ``battery_id`` ran at ``last_power``.

        A real battery counts the grid as measured: what it really did is
        never valued against a simulation (the virtual batteries are a
        what-if). A virtual battery counts it with the other virtual ones and
        without the real batteries that have a twin (the twin acts in their
        place).
        """
        grid = grid_avg if grid_avg is not None else self.grid_now()
        if grid is None:
            return None
        if not next(c for c in self.configs if c.id == battery_id).virtual:
            return grid
        twinned = twinned_ids(self.configs)
        for config in self.configs:
            if not config.virtual:
                if config.id in twinned:
                    grid -= self.states[config.id].power_w or 0.0
                continue
            if config.id == battery_id:
                grid += last_power
            else:
                grid += self.states[config.id].power_w or 0.0
        return grid

    def _follow_activity(self, config: BatteryConfig, power: float | None) -> None:
        """Explain what a real battery does (its own control) as periods: when a
        change has lasted ``ACTIVITY_SETTLE``, since when, with what and until
        when it is expected to go on; when it stops, the period it ran. After
        start-up, what it is doing is told once (``STARTUP_DELAY`` later, when
        the meter and the plan are there)."""
        if power is None:
            return
        activity = activity_of(power)
        if config.id not in self._activity:
            self._activity[config.id] = activity
            self._began[config.id] = self._period_start(config.id, dt_util.utcnow())

            @callback
            def _told(_now: datetime) -> None:
                self._startup.pop(config.id, None)
                if config.id not in self._pending:
                    self._explain_now(config)

            self._startup[config.id] = async_call_later(self.hass, STARTUP_DELAY, _told)
            return
        pending = self._pending.get(config.id)
        if pending is not None and pending[0] == activity:
            return
        if pending is not None:
            pending[2]()
            del self._pending[config.id]
        if activity == self._activity[config.id]:
            return
        began = dt_util.utcnow()
        # The counters when it began (not 5 minutes later when it settles).
        start = self._period_start(config.id, began)

        @callback
        def _settled(_now: datetime) -> None:
            self._pending.pop(config.id, None)
            previous = self._activity[config.id]
            self._activity[config.id] = activity
            if previous != "idle" and activity == "idle":
                self._explain_stop(config, previous, began)
            elif activity != "idle":
                self._explain_start(config, activity, began)
            self._began[config.id] = start

        self._pending[config.id] = (
            activity,
            began,
            async_call_later(self.hass, ACTIVITY_SETTLE, _settled),
        )

    def _period_start(
        self, battery_id: str, when: datetime
    ) -> tuple[datetime, float, float]:
        stats = self.stats[battery_id]
        return when, stats["charged_kwh"], stats["discharged_kwh"]

    def _explain_now(self, config: BatteryConfig) -> None:
        """What a real battery is doing right now (once after start-up)."""
        activity = self._activity.get(config.id)
        if activity is None:
            return
        if activity != "idle":
            self._explain_start(config, activity, None)
            return
        grid = self.grid_now()
        if grid is None:
            idle = "none"
        elif grid > ACTIVITY_THRESHOLD_W:
            idle = "grid"
        elif grid < -ACTIVITY_THRESHOLD_W:
            idle = "export"
        else:
            idle = "pv"
        state = self.states[config.id]
        why = "none"
        if state.soc is not None and state.soc >= config.max_soc - 1:
            why = "full"
        elif state.soc is not None and state.soc <= config.min_soc + 1:
            why = "empty"
        expected = self.expected_until(config.id, "idle")
        until, until_why = expected if expected else (None, "none")
        self._decisions.async_log(
            "battery",
            "battery_now_idle",
            name=config.name,
            why=f"@now_{why}",
            idle=f"@now_idle_{idle}",
            until="@until_none" if until is None else f"@until_{until_why}",
            time=clock(until) if until else "",
            plan=f"@plan_{plan_comparison('idle', self.planned_now())}",
        )

    def _explain_start(
        self, config: BatteryConfig, activity: str, began: datetime | None
    ) -> None:
        """A real battery started charging / discharging at ``began`` (None:
        it is doing so now, right after start-up)."""
        grid = self.grid_now()
        if activity == "charging":
            power = self.states[config.id].power_w or 0.0
            if grid is None or grid <= ACTIVITY_THRESHOLD_W:
                extra = "@src_pv"
            elif grid >= power - ACTIVITY_THRESHOLD_W:
                extra = "@src_grid"
            else:
                extra = "@src_mixed"
        else:
            exporting = grid is not None and grid < -ACTIVITY_THRESHOLD_W
            extra = "@also_export" if exporting else "@none"
        expected = self.expected_until(config.id, activity)
        until, why = expected if expected else (None, "none")
        planned = self.planned_now()
        self._decisions.async_log(
            "battery",
            f"battery_{activity}" if began else f"battery_now_{activity}",
            name=config.name,
            since=clock(began) if began else "",
            extra=extra,
            until="@until_none" if until is None else f"@until_{why}",
            time=clock(until) if until else "",
            plan=f"@plan_{plan_comparison(activity, planned)}",
        )

    def _explain_stop(
        self, config: BatteryConfig, previous: str, ended: datetime
    ) -> None:
        start, charged, discharged = self._began.get(
            config.id, self._period_start(config.id, ended)
        )
        stats = self.stats[config.id]
        kwh = (
            stats["charged_kwh"] - charged
            if previous == "charging"
            else stats["discharged_kwh"] - discharged
        )
        state = self.states[config.id]
        why = "none"
        if state.soc is not None and state.soc >= config.max_soc - 1:
            why = "full"
        elif state.soc is not None and state.soc <= config.min_soc + 1:
            why = "empty"
        # What the house runs on now that the battery is idle.
        grid = self.grid_now()
        if grid is None:
            idle = "none"
        elif grid > ACTIVITY_THRESHOLD_W:
            idle = "grid"
        elif grid < -ACTIVITY_THRESHOLD_W:
            idle = "export"
        else:
            idle = "pv"
        expected = self.expected_until(config.id, "idle")
        until, until_why = expected if expected else (None, "none")
        self._decisions.async_log(
            "battery",
            f"battery_stopped_{previous}",
            name=config.name,
            start=clock(start),
            end=clock(ended),
            energy=f"{kwh:.1f} kWh",
            why=f"@stop_{why}",
            idle=f"@idle_{idle}",
            until="@until_none" if until is None else f"@until_{until_why}",
            time=clock(until) if until else "",
            plan=f"@plan_{plan_comparison('idle', self.planned_now())}",
        )

    def _explain_availability(self, config: BatteryConfig, available: bool) -> None:
        """Explain losing / regaining a battery (not the first state at start-up)."""
        was = self._was_available.get(config.id)
        if not available and power_frozen(self.hass, config):
            return  # told by the measurement (battery_stale), not twice
        if was is not None and was != available:
            self._decisions.async_log(
                "battery",
                "battery_restored" if available else "battery_unavailable",
                name=config.name,
            )
        if available or was is not None:
            self._was_available[config.id] = available

    def count_up_to(self, now: datetime) -> None:
        """Count the real batteries' energy up to ``now`` at their last power
        (their sensors may not have changed since): the plan check reads
        counters that are up to date, not one update behind. Virtual
        batteries are counted every round by their simulator."""
        for config in self.configs:
            if config.virtual or config.id not in self._last_power:
                continue
            if power_frozen(self.hass, config, now):
                # Frozen: stop counting its last power (counters, value) and
                # tell everyone reading it (command check, plan) it is unknown.
                self._update(config, now)
                continue
            self._count_energy(config.id, now, self._last_power[config.id][1])
        self._store.async_delay_save(self._data, SAVE_DELAY)

    @callback
    def _async_log_soc(self, now: datetime) -> None:
        """Remember every battery's state of charge (for the dashboard), and
        count the real batteries' energy up to now: a battery whose sensors
        do not change (idle overnight, or a constant power) still starts the
        new day at midnight and has every quarter valued at its own price."""
        before = {
            c.id: (self.stats[c.id].get("days") or [{}])[-1].get("date")
            for c in self.configs
        }
        self.count_up_to(now)
        new_day = False
        for config in self.configs:
            # Also a battery without a power reading (or a virtual one that
            # did not move) starts the new day: *today* back to 0.
            self._roll_day(config.id, now)
            new_day |= self.stats[config.id]["days"][-1]["date"] != before[config.id]
        if new_day:
            for listener in list(self._listeners):
                listener()
        cutoff = (now - SOC_LOG_RETENTION).isoformat()
        for battery_id, state in self.states.items():
            log = self.soc_log.setdefault(battery_id, [])
            if state.soc is not None:
                log.append([now.isoformat(), round(state.soc, 2)])
            self.soc_log[battery_id] = [e for e in log if e[0] >= cutoff]
        # Written every quarter: the delayed save of every update keeps moving
        # (a battery changes every few seconds), so it would only be written
        # when Home Assistant stops cleanly.
        self.hass.async_create_task(self._store.async_save(self._data()))

    def _data(self) -> dict[str, Any]:
        return {"stats": self.stats, "soc_log": self.soc_log}
