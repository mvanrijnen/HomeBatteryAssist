"""Live measurements and the resulting house consumption.

house consumption = grid (sum of phases) + PV production - excluded loads
                    - battery power (+ charging / - discharging)

Grid power per phase is either one signed sensor (positive = import, negative =
export) or an import sensor minus an optional separate export (return) sensor.
PV sources and excluded loads are taken as absolute values; battery power is
normalised by ``batteries.battery_power``. The result is never below 0 W.

Instead of grid sensors, the grid power per phase can come from a meter that
is read directly about once a second (``direct.py``: HomeWizard P1 API, SMA
Speedwire). Listeners can then ask to be called at most every
``ENTITY_INTERVAL`` (entities), so the recorder does not store a state per
second; the history still gets every value.

Every new consumption value also goes through the chosen spike filter
(``spike_filters/``, when short peaks are switched on): ``spike`` says which
part is a short peak now, ``take_spike_wh`` the energy of peaks that ended.
``nom_balance`` turns a flow into what zero on the meter asks of the batteries
(never discharging for excluded devices or an ignored peak).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.sun import is_up
from homeassistant.util import dt as dt_util

from ...const import (
    CONF_DEVICE_PHASE_SENSORS,
    CONF_MAX_CURRENT,
    CONF_METER_ADDRESS,
    CONF_METER_SOURCE,
    CONF_PHASE,
    CONF_PHASE_CURRENT_SENSORS,
    CONF_PHASE_VOLTAGE_SENSORS,
    CONF_PHASES,
    CONF_PV_ADDRESS,
    CONF_PV_DRIVER,
    CONF_PV_POSSIBLE_SENSOR,
    CONF_SENSOR,
    NOMINAL_VOLTAGE,
    PHASE_NONE,
    PV_DRIVER_SENSOR,
    SUBENTRY_EXCLUDED_LOAD,
    SUBENTRY_HEATING_COOLING,
    SUBENTRY_PV_SOURCE,
    phase_index,
    phase_return_sensor_keys,
    phase_sensor_keys,
)
from ..devices.meters import get_driver as get_meter_driver
from ..devices.meters.discovery import (
    DIRECT_SOURCES,
    SOURCE_SENSORS,
    SOURCE_SPEEDWIRE,
    DirectMeter,
    create_meter,
)
from ..devices.meters.sma import SpeedwireMeter
from ..explain import DecisionLog
from ..units import state_to_watts
from .battery_monitor import (
    battery_configs,
    battery_meter,
    battery_power,
    direct_link,
    power_frozen,
)
from .spike_filters import SpikeFilter, SpikeState, checked

_LOGGER = logging.getLogger(__name__)
# No message about missing measurements this long after a (re)start.
STARTUP_QUIET = timedelta(minutes=2)
# PV without a value counts as unknown (not 0 W) only when it gave at least
# PV_SEEN_W within PV_GONE before (it dropped out while producing).
PV_SEEN_W = 20.0
PV_GONE = timedelta(minutes=30)

type MeasurementListener = Callable[[datetime, float | None], None]

ENTITY_INTERVAL = timedelta(seconds=10)  # entities with a direct meter
# A grid sensor that keeps its value but is not reported anew (its
# integration hangs) is frozen: after GRID_STALE it counts as unknown, so
# nothing acts on an old phase load. Checked every STALE_CHECK.
GRID_STALE = timedelta(seconds=90)
STALE_CHECK = timedelta(seconds=15)


# Current and voltage sensors in another unit than A / V.
_UNIT_FACTORS = {"mA": 0.001, "kA": 1000.0, "mV": 0.001, "kV": 1000.0, "µV": 1e-6}


@dataclass(frozen=True, slots=True)
class PowerFlow:
    """All power flows at one moment, in W.

    grid: net over all phases, + import / - export. battery: + charging /
    - discharging. pv, excluded and house are never negative.
    """

    grid_w: float
    pv_w: float
    excluded_w: float
    battery_w: float
    house_w: float
    phase_w: tuple[float, ...]  # net grid power per phase, + import / - export
    # House consumption and PV production per phase (devices without a phase
    # spread evenly), to learn how the consumption is spread over the phases.
    phase_house_w: tuple[float, ...] = ()
    phase_pv_w: tuple[float, ...] = ()
    heating_w: float | None = 0.0  # heating/cooling (part of house_w); None unknown
    # Per phase, when the meter sends them (else ()): measured current (A),
    # voltage (V) and power factor.
    phase_a: tuple[float, ...] = ()
    phase_v: tuple[float, ...] = ()
    phase_pf: tuple[float, ...] = ()
    # What the PV sources could produce now (W), when a source has a sensor
    # for it and produced less (curtailed); None = as measured.
    pv_possible_w: float | None = None

    @property
    def pv_potential_w(self) -> float:
        """PV as the sun gave it: the possible power where known, else measured."""
        return self.pv_possible_w if self.pv_possible_w is not None else self.pv_w

    @property
    def pv_curtailed_w(self) -> float:
        """PV held back now by the inverters (possible - measured)."""
        return max(self.pv_potential_w - self.pv_w, 0.0)

    def phase_amps(self, index: int) -> float:
        """The current on a phase (A), as precise as known: measured; else
        power / (measured voltage x power factor); else power / 230 V."""
        power = abs(self.phase_w[index])
        if index < len(self.phase_a):
            return abs(self.phase_a[index])  # some meters sign it with the power
        if index < len(self.phase_v) and self.phase_v[index] > 100:
            factor = self.phase_pf[index] if index < len(self.phase_pf) else 1.0
            factor = factor if 0.1 <= factor <= 1.0 else 1.0
            return power / (self.phase_v[index] * factor)
        return power / NOMINAL_VOLTAGE

    @property
    def phase_load_w(self) -> tuple[float, ...]:
        """Grid power per phase as far as the fuse is concerned: the current
        (``phase_amps``) at nominal voltage, with the sign of the power, so
        it compares with the limit (max current x 230 V x (1 - margin))."""
        return tuple(
            math.copysign(self.phase_amps(i) * NOMINAL_VOLTAGE, p)
            for i, p in enumerate(self.phase_w)
        )

    @property
    def import_w(self) -> float:
        """Power taken from the grid."""
        return max(self.grid_w, 0.0)

    @property
    def export_w(self) -> float:
        """Power returned to the grid."""
        return max(-self.grid_w, 0.0)

    def phase_current(self, index: int) -> float:
        """Current on a phase in A (see ``phase_amps``)."""
        return self.phase_amps(index)


class MeasurementInput:
    """Tracks the source sensors and computes the house consumption."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, decisions: DecisionLog
    ) -> None:
        """Initialize from the config entry and its subentries."""
        self.hass = hass
        self._decisions = decisions
        phases = entry.data[CONF_PHASES]
        self.phases: int = phases
        self.max_current: int = entry.data[CONF_MAX_CURRENT]
        self.source: str = entry.data.get(CONF_METER_SOURCE, SOURCE_SENSORS)
        self.direct: DirectMeter | None = (
            create_meter(hass, self.source, entry.data[CONF_METER_ADDRESS])
            if self.source in DIRECT_SOURCES
            else None
        )
        # (import or signed sensor, optional return sensor) per phase
        self.grid_phases: list[tuple[str, str | None]] = (
            []
            if self.direct
            else [
                (entry.data[key], entry.data.get(return_key) or None)
                for key, return_key in zip(
                    phase_sensor_keys(phases),
                    phase_return_sensor_keys(phases),
                    strict=True,
                )
            ]
        )
        # Optional current (A) and voltage (V) sensors per phase.
        self.current_sensors = [
            entry.data.get(k) or None for k in CONF_PHASE_CURRENT_SENSORS[:phases]
        ]
        self.voltage_sensors = [
            entry.data.get(k) or None for k in CONF_PHASE_VOLTAGE_SENSORS[:phases]
        ]
        self._unsub_direct: CALLBACK_TYPE | None = None
        self._unsub_stale: CALLBACK_TYPE | None = None
        self.stale: list[str] = []  # grid sensors frozen now
        self.pv_sources = _subentry_devices(entry, SUBENTRY_PV_SOURCE)
        self.excluded_loads = _subentry_devices(entry, SUBENTRY_EXCLUDED_LOAD)
        # PV sources read directly by a meter driver (e.g. a kWh meter)
        self.pv_meters: list[tuple[DirectMeter, str]] = []
        for driver_key, address, phase in _pv_meters(entry):
            if (driver := get_meter_driver(driver_key)) is not None:
                self.pv_meters.append((driver.create(hass, address), phase))
        self._store_serials(hass, entry)
        self.pv_sensors = [sensor for sensor, _, _ in self.pv_sources]
        # Per PV source (subentry order): its sensor, or the index of its
        # directly read meter.
        self._pv_order: list[tuple[str, int]] = []
        meter = 0
        for device, driver, address in _subentry_devices_all(entry, SUBENTRY_PV_SOURCE):
            if driver == PV_DRIVER_SENSOR:
                self._pv_order.append((device[0], -1))
            elif address and get_meter_driver(driver) is not None:
                self._pv_order.append(("", meter))
                meter += 1
            else:
                self._pv_order.append(("", -1))
        # (measured sensor, possible sensor) of PV sources with a sensor for
        # what they could produce now.
        self.pv_possible = [
            (sub.data.get(CONF_SENSOR) or "", sub.data[CONF_PV_POSSIBLE_SENSOR])
            for sub in entry.subentries.values()
            if sub.subentry_type == SUBENTRY_PV_SOURCE
            and sub.data.get(CONF_PV_POSSIBLE_SENSOR)
            and sub.data.get(CONF_PV_DRIVER, PV_DRIVER_SENSOR) == PV_DRIVER_SENSOR
        ]
        self.excluded_sensors = [sensor for sensor, _, _ in self.excluded_loads]
        # Heating/cooling: part of the house, measured apart for the forecast.
        self.heating_sensors = [
            sensor
            for sensor, _, _ in _subentry_devices(entry, SUBENTRY_HEATING_COOLING)
        ]
        # per-phase sensors also trigger a recalculation
        self._phase_device_sensors = [
            s
            for _, _, sensors in (*self.pv_sources, *self.excluded_loads)
            for s in sensors
            if s
        ]
        self.batteries = battery_configs(entry)

        self.power: float | None = None
        self.flow: PowerFlow | None = None
        # The flows as the meter sees them (grid, phases, PV), also while a
        # battery or excluded device is unknown (the house is then): for the
        # grid connection's sensors. None while the grid is unknown.
        self.meter_flow: PowerFlow | None = None
        self.missing: list[str] = []  # grid sensors without a valid value
        self._was_available: bool | None = None
        # Sensors of other integrations are often still starting in the first
        # minutes after a (re)start: a gap then is no message.
        self._quiet_until = dt_util.utcnow() + STARTUP_QUIET
        # When each PV source last gave power (for a PV value that drops out).
        self._pv_seen: dict[str, datetime] = {}
        self._listeners: list[MeasurementListener] = []
        self._pending: dict[int, CALLBACK_TYPE] = {}
        self._unsub: CALLBACK_TYPE | None = None
        # Short peaks: the chosen spike filter (None = off) and what it says.
        self.spike_filter: SpikeFilter | None = None
        self.spike = SpikeState()
        self.spike_wh_pending = 0.0

    def _store_serials(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """SMA meters set up by IP address (before serials): their serial,
        once seen, replaces the address in the setting (reconfigurable)."""
        if isinstance(self.direct, SpeedwireMeter) and self.direct.serial is None:
            self.direct.on_serial = _serial_setter(hass, entry, CONF_METER_ADDRESS)
        for subentry in entry.subentries.values():
            if (
                subentry.subentry_type != SUBENTRY_PV_SOURCE
                or subentry.data.get(CONF_PV_DRIVER) != SOURCE_SPEEDWIRE
            ):
                continue
            address = str(subentry.data.get(CONF_PV_ADDRESS) or "")
            for meter, _phase in self.pv_meters:
                if (
                    isinstance(meter, SpeedwireMeter)
                    and meter.serial is None
                    and meter.address == address
                ):
                    meter.on_serial = _serial_setter(
                        hass, entry, CONF_PV_ADDRESS, subentry
                    )

    @property
    def source_entity_ids(self) -> list[str]:
        """All sensors the calculation depends on."""
        grid = [e for pair in self.grid_phases for e in pair if e is not None]
        batteries = [b.power_sensor for b in self.batteries if b.power_sensor]
        return [
            *grid,
            *self.pv_sensors,
            *(possible for _, possible in self.pv_possible),
            *self.excluded_sensors,
            *self.heating_sensors,
            *self._phase_device_sensors,
            *batteries,
        ]

    @callback
    def async_start(self) -> None:
        """Start following the source sensors."""
        self._unsub = async_track_state_change_event(
            self.hass, self.source_entity_ids, self._async_state_changed
        )
        _LOGGER.debug("Following %s", self.source_entity_ids)
        if self.direct is not None:
            self._unsub_direct = self.direct.async_add_listener(self._update)
        self._unsub_pv = [m.async_add_listener(self._update) for m, _ in self.pv_meters]
        # Batteries read by an external meter: update with its values too.
        self._unsub_pv += [
            meter.async_add_listener(self._update)
            for b in self.batteries
            if (meter := battery_meter(self.hass, b)) is not None
        ]
        # Batteries read over their own connection: update with each reading.
        self._unsub_pv += [
            link.async_add_listener(self._update)
            for b in self.batteries
            if (link := direct_link(self.hass, b)) is not None
        ]
        if self.grid_phases or any(b.power_sensor for b in self.batteries):
            self._unsub_stale = async_track_time_interval(
                self.hass, self._async_check_stale, STALE_CHECK
            )
        self._update(dt_util.utcnow())

    @callback
    def _async_check_stale(self, now: datetime) -> None:
        """A frozen grid sensor sends no event: recalculate when one froze,
        or when it is reported again with the same value."""
        frozen = bool(self._stale_grid(now))
        if frozen != bool(self.stale) or (frozen and self.flow is not None):
            self._update(now)

    def _stale_grid(self, now: datetime) -> list[str]:
        """The grid sensors of each phase whose newest report is older than
        GRID_STALE, and the battery power sensors frozen at a real power
        (``BATTERY_STALE_W``; not when read by an external meter). Not in the
        first minutes after a start."""
        if now < self._quiet_until:
            return []
        frozen: list[str] = []
        for pair in self.grid_phases:
            sensors = [e for e in pair if e is not None]
            seen = [t for e in sensors if (t := self._reported(e)) is not None]
            if seen and now - max(seen) > GRID_STALE:
                frozen += sensors
        frozen += [
            b.power_sensor for b in self.batteries if power_frozen(self.hass, b, now)
        ]
        return frozen

    def _reported(self, entity_id: str) -> datetime | None:
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        return getattr(state, "last_reported", None) or state.last_updated

    async def async_start_meter(self) -> None:
        """Start reading the direct meters (grid and PV, if any)."""
        if self.direct is not None:
            await self.direct.async_start()
        for meter, _ in self.pv_meters:
            await meter.async_start()

    @callback
    def async_stop(self) -> None:
        """Stop following the source sensors."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self._unsub_direct is not None:
            self._unsub_direct()
            self._unsub_direct = None
        if self._unsub_stale is not None:
            self._unsub_stale()
            self._unsub_stale = None
        for unsub in getattr(self, "_unsub_pv", []):
            unsub()
        self._unsub_pv = []
        for cancel in self._pending.values():
            cancel()
        self._pending.clear()

    async def async_stop_meter(self) -> None:
        """Stop reading the direct meters (if any)."""
        if self.direct is not None:
            self.direct.cancel_stale()
            await self.direct.async_stop()
        for meter, _ in self.pv_meters:
            meter.cancel_stale()
            await meter.async_stop()

    @callback
    def async_add_listener(
        self, listener: MeasurementListener, *, entity: bool = False
    ) -> CALLBACK_TYPE:
        """Call ``listener(time, power)`` whenever the house consumption changes.

        ``entity``: with a direct meter, at most every ``ENTITY_INTERVAL``
        (and once more with the latest value after a quiet period).
        """
        if entity and self.direct is not None:
            listener = self._throttled(listener)
        elif entity:
            listener = self._coalesced(listener)
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _coalesced(self, listener: MeasurementListener) -> MeasurementListener:
        """Grid sensors per phase change one by one in the same round of the
        event loop (one update of their integration): the entities get one
        call with the result, not one per sensor (in-between states, each
        written and recorded)."""
        pending = [False]

        @callback
        def run() -> None:
            pending[0] = False
            listener(dt_util.utcnow(), self.power)

        @callback
        def call(when: datetime, power: float | None) -> None:
            if pending[0]:
                return
            pending[0] = True
            self.hass.loop.call_soon(run)

        return call

    def _throttled(self, listener: MeasurementListener) -> MeasurementListener:
        key = id(listener)
        last: list[datetime | None] = [None]

        @callback
        def call(when: datetime, power: float | None) -> None:
            if key in self._pending:
                return  # a delayed call follows anyway
            if last[0] is None or when - last[0] >= ENTITY_INTERVAL:
                last[0] = when
                listener(when, power)
                return

            @callback
            def later(_now: datetime) -> None:
                self._pending.pop(key, None)
                last[0] = dt_util.utcnow()
                listener(last[0], self.power)

            delay = (ENTITY_INTERVAL - (when - last[0])).total_seconds()
            self._pending[key] = async_call_later(self.hass, delay, later)

        return call

    def calculate(self) -> tuple[PowerFlow | None, list[str]]:
        """Compute all power flows and the grid sensors without a value.

        Unknown if any grid measurement is unknown or frozen, a battery's
        power is unknown or frozen at a real power, an excluded device has no
        value, or PV drops out while it was producing; sensors that do not
        exist at all count as 0 W.
        """
        phase_w: list[float] = []
        phase_a: tuple[float, ...] = ()
        phase_v: tuple[float, ...] = ()
        phase_pf: tuple[float, ...] = ()
        missing: list[str] = []
        if self.direct is not None:
            if self.direct.available and self.direct.phase_w:
                phase_w = list(self.direct.phase_w[: self.phases])
                if self.direct.phase_a:
                    phase_a = tuple(self.direct.phase_a[: self.phases])
                if self.direct.phase_v:
                    phase_v = tuple(self.direct.phase_v[: self.phases])
                if self.direct.phase_pf:
                    phase_pf = tuple(self.direct.phase_pf[: self.phases])
            else:
                missing.append(f"{self.direct.label} {self.direct.address}")
        for main, ret in self.grid_phases:
            value = self._watts(main)
            returned = self._watts(ret) if ret is not None else 0.0
            if value is None:
                missing.append(main)
            if returned is None:
                missing.append(ret)  # type: ignore[arg-type]
            if value is not None and returned is not None:
                phase_w.append(round(value - abs(returned), 1))
        self.stale = self._stale_grid(dt_util.utcnow())
        # Only a frozen grid sensor blanks the grid flow; a frozen battery
        # power sensor makes the house unknown below (battery_power is None
        # then), the grid connection's sensors stay.
        battery_sensors = {b.power_sensor for b in self.batteries}
        missing += [
            e for e in self.stale if e not in missing and e not in battery_sensors
        ]
        if missing:
            self.meter_flow = None
            return None, missing
        if not self.direct:
            phase_a = (
                self._per_phase(self.current_sensors, len(phase_w), signed=True) or ()
            )
            phase_v = self._per_phase(self.voltage_sensors, len(phase_w)) or ()
        grid = round(sum(phase_w), 1)
        pv = round(
            self._sum_abs(self.pv_sensors)
            + sum(
                abs(sum(m.phase_w))
                for m, _ in self.pv_meters
                if m.available and m.phase_w
            ),
            1,
        )
        # A battery or an excluded device without a value makes the house
        # unknown (as the grid does): counting it as 0 W would record a 2 kW
        # discharge or an 11 kW EV charge as house consumption.
        # (A sensor that does not exist at all counts as 0 W, as before.)
        unknown = [
            e
            for e in self.excluded_sensors
            if self.hass.states.get(e) is not None and self._watts(e) is None
        ]
        powers = [battery_power(self.hass, b) for b in self.batteries]
        unknown += [
            b.power_sensor or b.name
            for b, power in zip(self.batteries, powers, strict=True)
            if power is None
            and (
                direct_link(self.hass, b) is not None
                or self.hass.states.get(b.power_sensor) is not None
            )
        ]
        # PV that drops out while it was producing is not 0 W (an inverter's
        # wifi dropping would record its PV as no house use). An inverter
        # that is unavailable at night, or still asleep after sunrise, is
        # 0 W: only one that gave power in the last PV_GONE counts as unknown.
        now = dt_util.utcnow()
        for e in self.pv_sensors:
            value = self._watts(e)
            if value is not None and abs(value) >= PV_SEEN_W:
                self._pv_seen[e] = now
        for m, _ in self.pv_meters:
            if m.available and m.phase_w and abs(sum(m.phase_w)) >= PV_SEEN_W:
                self._pv_seen[f"{m.label} {m.address}"] = now

        producing = self._pv_producing
        unknown += [
            e
            for e in self.pv_sensors
            if self.hass.states.get(e) is not None
            and self._watts(e) is None
            and producing(e)
        ]
        unknown += [
            f"{m.label} {m.address}"
            for m, _ in self.pv_meters
            if not m.available and producing(f"{m.label} {m.address}")
        ]
        excluded = round(self._sum_abs(self.excluded_sensors), 1)
        battery = round(sum(p or 0.0 for p in powers), 1)
        house = max(round(grid + pv - excluded - battery, 1), 0.0)
        count = len(phase_w)
        phase_pv = [0.0] * count
        phase_house = list(phase_w)

        def add(target: list[float], phase: str, value: float) -> None:
            index = phase_index(phase, count)
            for i in range(count) if index is None else (index,):
                target[i] += value / (count if index is None else 1)

        def per_phase(
            sensor: str, phase: str, sensors: tuple[str | None, ...]
        ) -> list[tuple[str, float]]:
            """(phase, W) parts of a device: measured per phase, or its total."""
            if count > 1 and any(sensors):
                return [
                    (f"l{i + 1}", abs(self._watts(s) or 0.0))
                    for i, s in enumerate(sensors[:count])
                    if s
                ]
            return [(phase, abs(self._watts(sensor) or 0.0))]

        for sensor, phase, sensors in self.pv_sources:
            for part, value in per_phase(sensor, phase, sensors):
                add(phase_pv, part, value)
                add(phase_house, part, value)
        for meter, phase in self.pv_meters:
            if not meter.available or not meter.phase_w:
                continue
            values = meter.phase_w
            if count > 1 and len(values) == count:
                parts = [(f"l{i + 1}", abs(v)) for i, v in enumerate(values)]
            else:
                parts = [(phase, abs(sum(values)))]
            for part, value in parts:
                add(phase_pv, part, value)
                add(phase_house, part, value)
        for sensor, phase, sensors in self.excluded_loads:
            for part, value in per_phase(sensor, phase, sensors):
                add(phase_house, part, -value)
        for b in self.batteries:
            add(phase_house, b.phase, -(battery_power(self.hass, b) or 0.0))
        flow = PowerFlow(
            grid,
            pv,
            excluded,
            battery,
            house,
            tuple(phase_w),
            tuple(round(v, 1) for v in phase_house),
            tuple(round(v, 1) for v in phase_pv),
            # Unknown when one of them has no value (not 0 W heating: the
            # temperature step learns from it).
            None
            if any(
                self.hass.states.get(e) is not None and self._watts(e) is None
                for e in self.heating_sensors
            )
            else round(self._sum_abs(self.heating_sensors), 1),
            phase_a,
            phase_v,
            phase_pf,
            self._pv_possible(pv),
        )
        self.meter_flow = flow
        # A battery, an excluded device or producing PV unknown: the house
        # (and everything from it) is unknown; the meter's side stays.
        return (None, unknown) if unknown else (flow, [])

    def _pv_possible(self, pv: float) -> float | None:
        """PV as it could be now: the measured PV plus, per source with a
        possible-power sensor, what it held back; None when nothing was."""
        held = 0.0
        for measured, possible in self.pv_possible:
            could = self._watts(possible)
            now = self._watts(measured) if measured else None
            if could is not None and now is not None:
                held += max(abs(could) - abs(now), 0.0)
        return round(pv + held, 1) if held > 0 else None

    def _per_phase(
        self, sensors: list[str | None], count: int, signed: bool = False
    ) -> tuple[float, ...] | None:
        """Every phase's value of these sensors (A or V), or None when one is
        missing or unknown. ``signed`` (current): a sensor that signs the
        current with the power (negative while exporting) counts its size."""
        if len(sensors) != count or not all(sensors):
            return None
        values = []
        for sensor in sensors:
            state = self.hass.states.get(sensor)  # type: ignore[arg-type]
            try:
                value = float(state.state) if state else math.nan
            except ValueError:
                return None
            unit = state.attributes.get("unit_of_measurement") if state else None
            value *= _UNIT_FACTORS.get(str(unit).strip() if unit else "", 1.0)
            if signed:
                value = abs(value)
            if not math.isfinite(value) or value < 0:
                return None
            values.append(value)
        return tuple(values)

    def _watts(self, entity_id: str) -> float | None:
        return state_to_watts(self.hass.states.get(entity_id))

    def pv_per_source(self) -> list[float | None]:
        """The PV power now (W) of each PV source, in subentry order (None:
        unknown)."""
        result: list[float | None] = []
        for sensor, meter in self._pv_order:
            if meter >= 0:
                if meter < len(self.pv_meters):
                    reader = self.pv_meters[meter][0]
                    result.append(
                        abs(sum(reader.phase_w))
                        if reader.available and reader.phase_w
                        else None
                    )
                else:
                    result.append(None)
            elif sensor:
                value = self._watts(sensor)
                result.append(None if value is None else abs(value))
            else:
                result.append(None)
        return result

    @property
    def has_pv(self) -> bool:
        """PV is measured (sensors or meters read directly)."""
        return bool(self.pv_sensors or self.pv_meters)

    def _pv_producing(self, key: str) -> bool:
        """A PV source gave power in the last PV_GONE (without a value now it
        is unknown, not 0 W)."""
        seen = self._pv_seen.get(key)
        return (
            seen is not None and dt_util.utcnow() - seen <= PV_GONE and is_up(self.hass)
        )

    @property
    def pv_known(self) -> bool:
        """The PV is known now, as the house consumption counts it: a source
        without a value is 0 W (asleep, at night) unless it was producing
        just before (unknown PV is not 0 W measured)."""
        return all(
            self._watts(e) is not None
            or self.hass.states.get(e) is None
            or not self._pv_producing(e)
            for e in self.pv_sensors
        ) and all(
            meter.available or not self._pv_producing(f"{meter.label} {meter.address}")
            for meter, _ in self.pv_meters
        )

    def _sum_abs(self, entity_ids: list[str]) -> float:
        values = (self._watts(e) for e in entity_ids)
        return sum(abs(v) for v in values if v is not None)

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        self._update(event.time_fired)

    @callback
    def _update(self, when: datetime) -> None:
        self.flow, self.missing = self.calculate()
        self.power = self.flow.house_w if self.flow else None
        self._run_spike_filter(when)
        self._explain_availability()
        for listener in list(self._listeners):
            listener(when, self.power)

    def _run_spike_filter(self, when: datetime) -> None:
        """Let the spike filter see the new consumption (when one is set)."""
        spike_filter = self.spike_filter
        if spike_filter is None:
            return
        try:
            state = spike_filter.update(when, self.power)
        except Exception:  # an own module may fail in any way
            _LOGGER.exception("Spike filter %s failed", spike_filter.key)
            self.spike_filter = None
            self.spike = SpikeState()
            self._decisions.async_log(
                "measurement",
                "spike_filter_failed",
                name=spike_filter.name or spike_filter.key,
            )
            return
        self.spike = checked(state, self.power)
        self.spike_wh_pending += self.spike.ended_wh

    def take_spike_wh(self) -> float:
        """Energy of peaks that ended since the last call (for the history)."""
        wh, self.spike_wh_pending = self.spike_wh_pending, 0.0
        return wh

    def _explain_availability(self) -> None:
        """Record why the consumption became unknown, or that it is back.

        The first state after start-up is not logged: source sensors are often
        still starting then.
        """
        available = self.power is not None
        if not available and dt_util.utcnow() < self._quiet_until:
            # Starting up: as if it was never known.
            self._was_available = None
            return
        if self._was_available is not None and available != self._was_available:
            if available:
                self._decisions.async_log("measurement", "consumption_restored")
            elif self.stale:
                self._decisions.async_log(
                    "measurement",
                    # A battery's power sensor, or the grid's.
                    "battery_stale"
                    if all(
                        e in {b.power_sensor for b in self.batteries}
                        for e in self.stale
                    )
                    else "grid_stale",
                    sensors=", ".join(self.stale),
                    seconds=round(GRID_STALE.total_seconds()),
                )
            else:
                self._decisions.async_log(
                    "measurement",
                    "consumption_unavailable",
                    sensors=", ".join(self.missing),
                )
        if available or self._was_available is not None:
            self._was_available = available


def _subentry_devices(
    entry: ConfigEntry, subentry_type: str
) -> list[tuple[str, str, tuple[str | None, ...]]]:
    """Devices measured by sensors (directly read PV meters: ``_pv_meters``)."""
    return [
        device
        for device, driver, _ in _subentry_devices_all(entry, subentry_type)
        if driver == PV_DRIVER_SENSOR
    ]


def _serial_setter(
    hass: HomeAssistant, entry: ConfigEntry, key: str, subentry: Any = None
) -> Callable[[int], None]:
    """Store a learned SMA serial in place of the IP address setting."""

    @callback
    def store(serial: int) -> None:
        if subentry is not None:
            hass.config_entries.async_update_subentry(
                entry, subentry, data={**subentry.data, key: str(serial)}
            )
        else:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, key: str(serial)}
            )

    return store


def _pv_meters(entry: ConfigEntry) -> list[tuple[str, str, str]]:
    """(driver, address, phase) of PV sources read directly by a meter driver."""
    return [
        (driver, address, device[1])
        for device, driver, address in _subentry_devices_all(entry, SUBENTRY_PV_SOURCE)
        if driver != PV_DRIVER_SENSOR and address
    ]


def _subentry_devices_all(
    entry: ConfigEntry, subentry_type: str
) -> list[tuple[tuple[str, str, tuple[str | None, ...]], str, str]]:
    """(sensor, phase, per-phase sensors) of every subentry of the type.

    A device on one phase has ``phase`` l1-l3; a 3-phase device has phase
    "none" (spread evenly) or, more precisely, a sensor per phase.
    """
    return [
        (
            (
                subentry.data.get(CONF_SENSOR) or "",
                subentry.data.get(CONF_PHASE, PHASE_NONE),
                tuple(
                    subentry.data.get(key) or None for key in CONF_DEVICE_PHASE_SENSORS
                ),
            ),
            subentry.data.get(CONF_PV_DRIVER, PV_DRIVER_SENSOR),
            subentry.data.get(CONF_PV_ADDRESS, ""),
        )
        for subentry in entry.subentries.values()
        if subentry.subentry_type == subentry_type
    ]


def nom_balance(flow: PowerFlow, target_w: float, ignore_w: float = 0.0) -> float:
    """What zero on the meter asks of the batteries now (W, + charge /
    - discharge), around the grid target ``target_w``.

    A surplus on the grid is charged. A shortage is discharged, but never for
    excluded devices (e.g. an EV charger: the grid supplies them) nor for
    ``ignore_w`` (a short peak the spike filter recognised).
    """
    need = flow.grid_w - target_w
    if need <= 0:
        return -need
    return -max(need - flow.excluded_w - max(ignore_w, 0.0), 0.0)


def planned_discharge(
    planned_w: float, flow: PowerFlow, planned_grid_w: float, cover: bool = False
) -> float:
    """A planned discharge (W, < 0) as far as it is needed now.

    The plan sized the discharge to the *forecast* need. When the house uses
    less now (or the sun shines), discharging the planned power would push
    battery energy into the grid. So a discharge goes no further than the
    grid the plan expected for this slot (``planned_grid_w``: 0 or more = no
    export; less = an export the plan chose), never for excluded devices
    (``nom_balance``). ``cover``: the house uses more than forecast and
    using the batteries pays at this price (``covers``): the real need is
    covered, also above the planned power. A charge (>= 0) is returned as it
    is.
    """
    if planned_w >= 0:
        return planned_w
    need = min(nom_balance(flow, min(planned_grid_w, 0.0)), 0.0)
    return need if cover else max(planned_w, need)


def covers(slot: Any) -> bool:
    """A plan slot that discharges for the house (no export) at a price at
    which using the batteries pays (``use_above``, the plan's own threshold):
    a larger need than forecast is covered too."""
    price = getattr(slot, "price", None)
    use_above = getattr(slot, "use_above", None)
    return (
        getattr(slot, "power_w", 0.0) < 0
        and getattr(slot, "grid_w", 0.0) >= -1.0
        and price is not None
        and use_above is not None
        and price >= use_above
    )


# Solar power clearly more or less than forecast: a difference of at least
# this much (default; option ``pv_deviation_w``), and less than this share of
# the larger of the two.
MIN_SURPLUS_W = 300.0
SURPLUS_SHARE = 0.5


def solar_surplus_w(flow: PowerFlow) -> float:
    """What is left over of the solar power now: PV - house - excluded."""
    return flow.pv_w - flow.house_w - flow.excluded_w


def unexpected_surplus(
    surplus_w: float, expected_w: float, threshold_w: float = MIN_SURPLUS_W
) -> bool:
    """A surplus the forecast did not see coming."""
    return surplus_w >= threshold_w and max(expected_w, 0.0) < SURPLUS_SHARE * surplus_w


def unexpected_shortage(
    surplus_w: float, expected_w: float, threshold_w: float = MIN_SURPLUS_W
) -> bool:
    """A forecast surplus that is not there (clouds, or the house uses more)."""
    return (
        expected_w >= threshold_w and max(surplus_w, 0.0) < SURPLUS_SHARE * expected_w
    )


# A plan that charges at least the forecast surplus minus this stores it all.
STORES_ALL_W = 50.0


def plan_balance(
    planned_w: float,
    surplus_w: float,
    expected_w: float,
    threshold_w: float = MIN_SURPLUS_W,
) -> float:
    """What a plan per slot asks of the batteries now (W, + charge), with the
    real solar surplus instead of the forecast one.

    The plan counted on ``expected_w`` of surplus (forecast for this hour).

    - Less sun: the part of a planned charge that was to come from the sun
      is only charged as far as the surplus is really there, however small
      the shortage: the grid never fills in for the missing sun (a planned
      grid charge goes on).
    - Unexpectedly more (``unexpected_surplus``): charged as well, never so
      much that the grid supplies it — but only when the plan stores the
      forecast surplus itself. A plan that exports it chose to (storing does
      not pay then: the export price is worth more than the energy later),
      so the extra is exported too.

    A plan that discharges now is followed as it is.
    """
    if planned_w < 0:
        return planned_w
    surplus = max(surplus_w, 0.0)
    expected = max(expected_w, 0.0)
    from_sun = min(planned_w, expected)
    if surplus < from_sun:
        return planned_w - from_sun + surplus
    if (
        unexpected_surplus(surplus_w, expected_w, threshold_w)
        and planned_w >= expected - STORES_ALL_W
    ):
        extra = surplus - expected
        return min(planned_w + extra, max(planned_w, surplus))
    return planned_w
