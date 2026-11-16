"""Home batteries: configuration, live state and monitoring counters.

A battery is linked read-only through entities of its own integration (state
of charge and power sensors), so any brand works and the integration that owns
the battery is never disturbed. HomeBatteryAssist never controls a battery.
Battery power is normalised to: positive = charging, negative = discharging.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
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
    async_track_utc_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ...const import (
    CONF_CAPACITY,
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
    VALUE_BASIS,
)
from ..explain import DecisionLog
from .units import parse_float, state_to_watts

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SOC_LOG_RETENTION = timedelta(days=7)
SAVE_DELAY = 60  # seconds
# A real battery's activity (charging / discharging / idle) is explained once
# it has lasted this long, so short swings are not logged.
ACTIVITY_SETTLE = timedelta(minutes=5)
STARTUP_DELAY = timedelta(minutes=1)  # then tell what each battery is doing
ACTIVITY_THRESHOLD_W = 50.0  # |power| above this counts as charging/discharging


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
        return now + timedelta(hours=energy * 1000 / power)  # type: ignore[operator]


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
    return [
        BatteryConfig.from_subentry(subentry)
        for subentry in entry.subentries.values()
        if subentry.subentry_type in types
    ]


def _soc(state: State | None) -> float | None:
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    value = parse_float(state.state)
    if value is None or not 0 <= value <= 100:
        return None
    return value


def battery_power(hass: HomeAssistant, config: BatteryConfig) -> float | None:
    """Battery power in W, + charging / - discharging, or None if unknown."""
    watts = state_to_watts(hass.states.get(config.power_sensor))
    if watts is None:
        return None
    return -watts if config.power_sign == SIGN_DISCHARGING_POSITIVE else watts


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
        self.states: dict[str, BatteryState] = {
            c.id: BatteryState(c, None, None) for c in self.configs
        }
        self.stats: dict[str, BatteryStats] = {}
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.batteries"
        )
        self._last_power: dict[str, tuple[datetime, float]] = {}
        self._was_available: dict[str, bool] = {}
        self._listeners: list[Callable[[], None]] = []
        self._unsub: CALLBACK_TYPE | None = None
        self._unsub_log: CALLBACK_TYPE | None = None
        # Price (per kWh) right now, set by the setup (from the price forecast).
        self.price_now: Callable[[], float | None] = lambda: None
        # What exported energy earns right now (None = the import price).
        self.export_price_now: Callable[[], float | None] = lambda: None
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
        self._startup: dict[str, CALLBACK_TYPE] = {}  # the one message after start-up
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
        for config in self.configs:
            self.stats[config.id] = BatteryStats(
                charged_kwh=0.0, discharged_kwh=0.0, last_full_charge=None
            ) | stored.get(config.id, {})
            stats = self.stats[config.id]
            if stats.get("value_basis") != VALUE_BASIS:
                # Older counters (net metering, or without the energy for the
                # wear): start again.
                stats.pop("value", None)
                stats.pop("value_since", None)
                stats.pop("value_kwh", None)
                stats["value_basis"] = VALUE_BASIS
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
        for config in self.configs:
            if config.virtual:
                soc = self.stats[config.id].get("virtual_soc", config.initial_soc)
                self._update(config, now, BatteryState(config, soc, 0.0))
            else:
                self._update(config, now)

    async def async_stop(self) -> None:
        """Stop following and persist the counters."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self._unsub_log is not None:
            self._unsub_log()
            self._unsub_log = None
        for _activity, _began, cancel in self._pending.values():
            cancel()
        self._pending.clear()
        for cancel in self._startup.values():
            cancel()
        self._startup.clear()
        await self._store.async_save(self._data())

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
        last = self.stats[battery_id]["last_full_charge"]
        if last is None:
            return now
        return dt_util.parse_datetime(last) + timedelta(  # type: ignore[operator]
            days=config.full_charge_interval_days
        )

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
            and (previous.soc is None or previous.soc < FULL_CHARGE_SOC)
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

    def _count_energy(
        self, battery_id: str, when: datetime, power: float | None
    ) -> None:
        """Integrate the previous power value up to ``when`` (kWh counters)."""
        if (last := self._last_power.pop(battery_id, None)) is not None:
            since, last_power = last
            kwh = last_power * max((when - since).total_seconds(), 0.0) / 3_600_000
            stats = self.stats[battery_id]
            if kwh > 0:
                stats["charged_kwh"] = round(stats["charged_kwh"] + kwh, 4)
            elif kwh < 0:
                stats["discharged_kwh"] = round(stats["discharged_kwh"] - kwh, 4)
            # Realised value: what the grid would have cost without this
            # battery minus what it costs with it (no net metering).
            if kwh and (price := self.price_now()) is not None:
                hours = max((when - since).total_seconds(), 0.0) / 3600
                grid_kwh = self._grid_with_batteries(battery_id, last_power)
                stats.setdefault("value_since", when.isoformat())
                # Energy through the battery behind the value (for its wear).
                stats["value_kwh"] = round(stats.get("value_kwh", 0.0) + abs(kwh), 4)
                stats["value"] = round(
                    stats.get("value", 0.0)
                    + realised_value(
                        kwh,
                        None if grid_kwh is None else grid_kwh * hours / 1000,
                        price,
                        self.export_price_now(),
                    ),
                    5,
                )
        if power is not None:
            self._last_power[battery_id] = (when, power)

    def _grid_with_batteries(self, battery_id: str, last_power: float) -> float | None:
        """Grid power (W) with all batteries, the virtual ones included, while
        ``battery_id`` ran at ``last_power``."""
        grid = self.grid_now()
        if grid is None:
            return None
        for config in self.configs:
            if not config.virtual:
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

        @callback
        def _settled(_now: datetime) -> None:
            self._pending.pop(config.id, None)
            previous = self._activity[config.id]
            self._activity[config.id] = activity
            if previous != "idle" and activity == "idle":
                self._explain_stop(config, previous, began)
            elif activity != "idle":
                self._explain_start(config, activity, began)
            self._began[config.id] = self._period_start(config.id, began)

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
        if was is not None and was != available:
            self._decisions.async_log(
                "battery",
                "battery_restored" if available else "battery_unavailable",
                name=config.name,
            )
        if available or was is not None:
            self._was_available[config.id] = available

    @callback
    def _async_log_soc(self, now: datetime) -> None:
        """Remember every battery's state of charge (for the dashboard)."""
        cutoff = (now - SOC_LOG_RETENTION).isoformat()
        for battery_id, state in self.states.items():
            log = self.soc_log.setdefault(battery_id, [])
            if state.soc is not None:
                log.append([now.isoformat(), round(state.soc, 2)])
            self.soc_log[battery_id] = [e for e in log if e[0] >= cutoff]
        self._store.async_delay_save(self._data, SAVE_DELAY)

    def _data(self) -> dict[str, Any]:
        return {"stats": self.stats, "soc_log": self.soc_log}
