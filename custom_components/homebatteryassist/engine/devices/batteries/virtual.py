"""Live simulation of virtual batteries (what-if).

Every ``STEP`` the simulator lets each virtual battery act according to the
selected plan mode, using the real measurements:

- ``nom``: absorb the real surplus / cover the real shortage measured on the
  grid right now (after the real batteries);
- the other modes (arbitrage, time slots, manual): follow the battery plan of
  the current slot, for the virtual batteries' share of the planned capacity;
  an unexpected solar surplus (``plan_balance``) is stored on top; when the
  sun falls short, the part of a planned charge that was to come from it is
  only charged as far as it is really there.

The total is spread over the virtual batteries with
``planning.distribution.distribute`` (minimum power per battery).

Then the phase limits of the grid connection, on the phase power measured
right now (``planning.phase_limit``):

- phase protection: when a phase is over its limit by itself, the virtual
  batteries on that phase take load off it (discharge on too much import,
  charge on too much export), whatever the plan wanted;
- a virtual battery may never push a phase over its limit (it charges or
  discharges less).

Besides the regular step, a step is taken as soon as a measurement shows an
overloaded phase (at most every ``REACT_INTERVAL``), so the simulation reacts
within seconds like real control would.

Within the battery's power and state-of-charge limits. The round-trip loss is
drawn at random per step between the battery's ``loss_min`` and ``loss_max``
(split evenly over charging and discharging), like a real battery whose losses
vary with power, temperature and state of charge. Results go to the
battery input, so a virtual battery has the same sensors as a real one. Virtual
batteries are included in the battery plan (what-if), never in the house
consumption.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from ....const import NOMINAL_VOLTAGE
from ...control.interceptors import (
    BatteryProposal,
    InterceptInput,
    PriceSlot,
    create_interceptor,
    run_interceptor,
)
from ...control.pd_controller import (
    CONTROL_DIRECT,
    CONTROL_PD,
    PdController,
    PdSettings,
)
from ...coordinator import ForecastCoordinator
from ...explain import DecisionLog
from ...measure.battery_monitor import BatteryConfig, BatteryInput, twinned_ids
from ...measure.house_measurement import (
    MeasurementInput,
    nom_balance,
    plan_balance,
    planned_discharge,
    solar_surplus_w,
)
from ...planning.battery_distribution import Candidate, Distributor, one_direction
from ...planning.battery_plan import MODE_NOM
from ...planning.phase_limit import (
    PhaseDevice,
    PhaseLoad,
    active_relief_loads,
    cap_powers,
    overloaded,
    phase_limit_w,
    relieve,
    shave_peak,
)
from ...units import state_to_celsius
from .control_quality import ControlQuality
from .response import BatteryResponse

_LOGGER = logging.getLogger(__name__)

# The round is a setting (react_interval_s, default 5 s); this is the fallback.
STEP = timedelta(seconds=5)
MAX_STEP = timedelta(minutes=5)  # longer gaps (restart) are not simulated
LIMIT_CLEAR_AFTER = timedelta(minutes=5)  # no phase limit this long: log it
INTERCEPT_HORIZON = timedelta(hours=8)  # coming slots an interceptor sees
RELIEF_END_AFTER = timedelta(minutes=1)  # phase back under the limit this long
REACT_INTERVAL = timedelta(seconds=2)  # fastest extra step on an overload
# The grid voltage stays within 230 V +/- 10 % (EN 50160): the range of the
# active current where the voltage is not measured.
VOLTAGE_MIN = 207.0
VOLTAGE_MAX = 253.0
# Closer to its minimum / maximum (%) is at it: a rest too small to give or
# take in a round would keep the battery counted as usable forever.
SOC_SNAP = 0.001


def limit_power(
    config: BatteryConfig,
    soc: float,
    target_w: float,
    hours: float,
    efficiency: float | None = None,
) -> tuple[float, float]:
    """Clamp ``target_w`` to the battery limits; return (power, new SoC %).

    ``efficiency``: round-trip efficiency for this step (default: the config's).
    """
    eff = math.sqrt(efficiency if efficiency is not None else config.efficiency)
    wh_per_pct = config.capacity_kwh * 10
    if target_w > 0:
        room = max(config.max_soc - soc, 0.0) * wh_per_pct
        power = min(target_w, config.max_charge_w, room / (hours * eff) if hours else 0)
        soc += power * hours * eff / wh_per_pct
        if config.max_soc - SOC_SNAP < soc < config.max_soc:
            soc = config.max_soc  # full: no rest too small to ever charge
    elif target_w < 0:
        available = max(soc - config.min_soc, 0.0) * wh_per_pct
        power = -min(
            -target_w, config.max_discharge_w, available * eff / hours if hours else 0
        )
        soc += power * hours / eff / wh_per_pct
        if config.min_soc < soc < config.min_soc + SOC_SNAP:
            soc = config.min_soc  # empty: no rest too small to ever give
    else:
        power = 0.0
    # The state of charge unrounded: rounded every 5 s round it would drift
    # (or never move at a low power).
    return round(power, 1) + 0.0, min(max(soc, 0.0), 100.0)


def without_batteries(flow: Any, batteries: list[tuple[int | None, float]]) -> Any:
    """The power flow as it would be without these batteries ((phase index
    or None = spread, power W + charging)): grid and phases less their power.
    The current of a changed phase is recomputed with its measured reactive
    part."""
    batteries = [(i, w) for i, w in batteries if w]
    if not batteries:
        return flow
    phases = len(flow.phase_w)
    phase_w = list(flow.phase_w)
    for index, power in batteries:
        for i in range(phases) if index is None else (index,):
            if i < phases:
                phase_w[i] -= power / (phases if index is None else 1)
    total = sum(w for _i, w in batteries)
    # The measured current of a changed phase: its reactive part stays (the
    # battery only changes the active power), so I = hypot(P, Q) / V; an
    # untouched phase keeps its measured current.
    phase_a: tuple[float, ...] = ()
    measured = tuple(flow.phase_a or ())
    if len(measured) == phases:
        volts = tuple(getattr(flow, "phase_v", ()) or ())
        amps = []
        for i in range(phases):
            if phase_w[i] == flow.phase_w[i]:
                amps.append(measured[i])
                continue
            v = volts[i] if len(volts) == phases and volts[i] else NOMINAL_VOLTAGE
            # A current in whole amps can be up to half an amp more: the
            # reactive part from the most it can be, and rounded up, so the
            # result is never below the real current.
            amp = abs(measured[i])
            amp += 0.5 if amp == round(amp) else 0.0
            q = math.sqrt(max((amp * v) ** 2 - flow.phase_w[i] ** 2, 0.0))
            amps.append(math.ceil(math.hypot(phase_w[i], q) / v * 100) / 100)
        phase_a = tuple(amps)
    return replace(
        flow,
        grid_w=flow.grid_w - total,
        battery_w=flow.battery_w - total,
        phase_w=tuple(phase_w),
        phase_a=phase_a,
    )


def _active_loads(flow: Any) -> list[float]:
    """The active power per phase in the terms of ``phase_load_w`` (nominal
    current as power), signed. Only where the reactive part is really known:
    a measured voltage, or a power factor without a measured current; else
    the load itself (a voltage below 230 V must not look like reactive
    power)."""
    volts = tuple(getattr(flow, "phase_v", ()) or ())
    amps = tuple(getattr(flow, "phase_a", ()) or ())
    pfs = tuple(getattr(flow, "phase_pf", ()) or ())
    loads = flow.phase_load_w
    return [
        p * NOMINAL_VOLTAGE / volts[i]
        if i < len(volts) and volts[i] > 100
        else p
        if i >= len(amps) and i < len(pfs) and pfs[i]
        else loads[i]
        for i, p in enumerate(flow.phase_w)
    ]


def phase_loads(flow: Any) -> list[PhaseLoad]:
    """The load per phase for the final phase check, as the worst case of
    what the measurement says (``PhaseLoad``, current terms: current x 230 V).

    - A measured current in whole amps (many meters round it) can be up to
      half an amp more.
    - The active power in current terms is power x 230 / measured voltage;
      without a measured voltage, but with a measured current, the voltage
      can be anything from 207 to 253 V, so the active power is a range
      (never more than the current).
    - Without a measured current: power / (voltage x power factor), with
      the measured voltage or else 207 V (the lowest allowed), and the
      power factor when the meter sends one (also a low one: then the
      current is mostly reactive), else 1. Without current and power
      factor the reactive part cannot be known (only the phase margin
      covers it).
    """
    volts = tuple(getattr(flow, "phase_v", ()) or ())
    amps = tuple(getattr(flow, "phase_a", ()) or ())
    pfs = tuple(getattr(flow, "phase_pf", ()) or ())
    out = []
    for i, power in enumerate(flow.phase_w):
        volt = volts[i] if i < len(volts) and volts[i] > 100 else None
        if i < len(amps):
            amp = abs(amps[i])
            if amp == round(amp):
                amp += 0.5  # whole amps: up to half an amp more
            current = amp * NOMINAL_VOLTAGE
            if volt:
                low = high = power * NOMINAL_VOLTAGE / volt
            else:
                small = abs(power) * NOMINAL_VOLTAGE / VOLTAGE_MAX
                big = min(abs(power) * NOMINAL_VOLTAGE / VOLTAGE_MIN, current)
                low, high = sorted(
                    (math.copysign(small, power), math.copysign(max(big, small), power))
                )
        else:
            pf = abs(pfs[i]) if i < len(pfs) else 1.0
            pf = pf if 0 < pf <= 1 else 1.0
            active = abs(power) * NOMINAL_VOLTAGE / (volt or VOLTAGE_MIN)
            current = active / pf
            if volt:
                low = high = math.copysign(active, power)
            else:
                low, high = sorted(
                    (
                        math.copysign(
                            abs(power) * NOMINAL_VOLTAGE / VOLTAGE_MAX, power
                        ),
                        math.copysign(active, power),
                    )
                )
        out.append(PhaseLoad(current, low, high))
    return out


def random_efficiency(config: BatteryConfig) -> float:
    """Round-trip efficiency for one step: a random loss within the range."""
    return 1 - random.uniform(config.loss_min, config.loss_max)


def system_limited(powers: dict[str, float], rules: Any) -> dict[str, float]:
    """All batteries together within the system's max charge and discharge
    power (0 = no limit), each scaled by the same factor."""
    out = dict(powers)
    for sign, cap in ((1.0, rules.max_charge_w), (-1.0, rules.max_discharge_w)):
        if cap <= 0:
            continue
        total = sum(p for p in out.values() if p * sign > 0) * sign
        if total > cap:
            factor = cap / total
            out = {k: (p * factor if p * sign > 0 else p) for k, p in out.items()}
    return out


class VirtualBatterySimulator:
    """Steps all virtual batteries forward in time."""

    def __init__(
        self,
        hass: HomeAssistant,
        batteries: BatteryInput,
        measurements: MeasurementInput,
        forecast: ForecastCoordinator,
        decisions: DecisionLog,
    ) -> None:
        """Initialize."""
        self._over_seen: set[int] = set()  # phases overloaded at the last check
        self._peak_seen = False
        self.hass = hass
        self._decisions = decisions
        self._distributor = Distributor(forecast.balance_interval)
        self._batteries = batteries
        self._measurements = measurements
        self._forecast = forecast
        self._last: datetime | None = None
        self._full_w = 0.0  # virtual batteries charging fully now (W)
        self._unsub: CALLBACK_TYPE | None = None
        self.limited_phases: list[int] = []  # phases that limit right now
        self._limit_logged = False
        self._limit_seen: datetime | None = None
        self._unsub_measured: CALLBACK_TYPE | None = None
        # phase index -> {"start", "seen", "wh", "names"} while relieving it
        self.relief: dict[int, dict[str, Any]] = {}
        self._peak: dict[str, Any] | None = None  # running peak shaving
        # For the dashboard: what the protections do right now.
        self.relief_now: dict[int, float] = {}  # phase index -> W taken off
        self.peak_now: float = 0.0  # W shaved off the total
        self._full: set[str] = set()  # batteries waiting for the hysteresis
        # Grid values since the last round: (time, grid W, excluded W), for
        # the average over the round; the grid at the last round, for jumps.
        # (time, grid W, excluded W, ignored spike W) since the last round
        self._samples: list[tuple[datetime, float, float, float]] = []
        # The ignored spike averaged over the round (as the grid), the start
        # of the round (the previous round), and whether protection or the
        # interceptor set a battery's power last round.
        self._round_ignore: float | None = None
        self._round_start: datetime | None = None
        self._protected_last = False
        self._step_grid: float | None = None
        self._meter_lost = False  # grid unknown: batteries held
        self._twin_lost = False  # a twinned real battery unknown: held
        # No message while the meter starts up after a (re)start.
        self._quiet_until = dt_util.utcnow() + timedelta(minutes=2)
        # The interceptor (the user's last say) and what it did lately.
        self.intercepted: list[tuple[str, str, float, str]] = []
        self._intercept_gist = ""
        self._intercept_failed = False
        # How well zero on the meter holds the grid (sensor control_quality).
        self.quality = ControlQuality()
        self._quality_round: float | None = None  # power of a free round
        # Zero on the meter by PD control (else direct), and the simulated
        # reaction of each battery to a new power.
        # Direct = the same loop at full gain: with a battery that reacts at
        # once it gives exactly what the grid asks (as before).
        self._direct = getattr(forecast, "nom_control", CONTROL_DIRECT) != CONTROL_PD
        self._pd = PdController(
            PdSettings(kp=1.0, kd=0.0, max_step_w=0, hysteresis_w=0)
            if self._direct
            else forecast.pd_settings
        )
        # Last NOM command per battery (W), and whether this round's total
        # could be placed as zero on the meter wanted (control quality).
        self._commands: dict[str, float] = {}
        self._nom_free = False
        self._nom_total = 0.0
        self._responses: dict[str, BatteryResponse] = {}
        # The batteries protecting a phase / the peak this round, also those
        # already doing it without a change (the interceptor must not undo it).
        self._relief_helpers: set[str] = set()
        self._peak_helpers: set[str] = set()

    def _flow(self) -> Any:
        """The grid as the virtual batteries see it: measured, without the
        real batteries that have a twin (the twin acts in their place)."""
        flow = self._measurements.flow
        if flow is None:
            return None
        twinned = twinned_ids(self._batteries.configs)
        if not twinned:
            return flow
        if any(self._batteries.states[i].power_w is None for i in twinned):
            return None  # the grid without the real battery is not known now
        phases = max(len(flow.phase_w), 1)
        return without_batteries(
            flow,
            [
                (
                    PhaseDevice.from_config(c, phases).phase,
                    self._batteries.states[c.id].power_w or 0.0,
                )
                for c in self._batteries.configs
                if c.id in twinned
            ],
        )

    @property
    def virtual(self) -> list[BatteryConfig]:
        """The virtual batteries."""
        return [c for c in self._batteries.configs if c.virtual]

    @callback
    def async_start(self) -> None:
        """Simulate every ``STEP``."""
        if not self.virtual:
            return
        self._last = dt_util.utcnow()
        self._unsub = async_track_time_interval(
            self.hass,
            self._async_step,
            getattr(self._forecast, "react_interval", None) or STEP,
        )
        self._unsub_measured = self._measurements.async_add_listener(
            self._async_measured
        )

    @callback
    def async_stop(self) -> None:
        """Stop simulating."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self._unsub_measured is not None:
            self._unsub_measured()
            self._unsub_measured = None

    @callback
    def _async_step(self, now: datetime) -> None:
        self.step(now)

    @callback
    def _async_measured(self, when: datetime, _power: float | None) -> None:
        """Keep the grid values of the round; react at once when a phase is
        overloaded (or the virtual batteries on it would overload it), above
        the peak limit, or (when switched on) on a large jump of the grid."""
        flow = self._flow()
        if flow is not None:
            spike = getattr(self._measurements, "spike", None)
            self._samples.append(
                (when, flow.grid_w, flow.excluded_w, getattr(spike, "ignore_w", 0.0))
            )
        if self._last is None or when - self._last < REACT_INTERVAL:
            return
        if flow is None or not flow.phase_w:
            return
        jump = self._forecast.react_jump_w
        if (
            jump
            and self._step_grid is not None
            and abs(flow.grid_w - self._step_grid) >= jump
        ):
            # Follow the new level at once, not the average with before it.
            self._samples = self._samples[-1:]
            self.step(when)
            return
        phases = len(flow.phase_w)
        with_virtual = list(flow.phase_load_w)
        for config in self.virtual:
            power = self._batteries.states[config.id].power_w or 0.0
            index = PhaseDevice.from_config(config, phases).phase
            for i in range(phases) if index is None else (index,):
                with_virtual[i] += power / (phases if index is None else 1)
        peak = self._forecast.peak_w
        grid = (
            flow.grid_w
            + sum(self._batteries.states[c.id].power_w or 0.0 for c in self.virtual)
            - (0.0 if self._forecast.peak_include_excluded else flow.excluded_w)
        )
        over = set(overloaded(with_virtual, self._limit_w())) | set(
            overloaded(flow.phase_load_w, self._limit_w())
        )
        # A new overload (or a peak) at once; one that lasts is handled by
        # the normal rounds (else every measurement starts a round and the
        # averaging of zero on the meter is lost).
        new = bool(over - self._over_seen)
        self._over_seen = over
        if new or (peak > 0 and grid > peak and not self._peak_seen):
            self.step(when)
        self._peak_seen = peak > 0 and grid > peak

    def _nominal_devices(
        self, flow: Any, phases: int, worst: bool = False
    ) -> tuple[list[PhaseDevice], dict[str, float]]:
        """The batteries for the phase checks in current terms: the phase
        limit and load are current x 230 V, so a battery's power counts as
        power x 230 / (measured voltage of its phase(s)); ``factor`` per
        battery, to convert back after. For the relief: the mean voltage of
        a spread battery's phases, 230 V where none is measured. ``worst``
        (the final check): the lowest voltage, the most current per W (a
        spread battery: its lowest phase; unmeasured: 207 V, the lowest
        allowed)."""
        voltages = getattr(flow, "phase_v", ()) or ()
        devices: list[PhaseDevice] = []
        factor: dict[str, float] = {}
        for config in self.virtual:
            device = PhaseDevice.from_config(config, phases)
            used = (
                [voltages[device.phase]]
                if device.phase is not None and device.phase < len(voltages)
                else list(voltages[:phases])
            )
            used = [v for v in used if v > 100]
            if worst:
                # Every phase it is on measured, else the lowest allowed.
                on = 1 if device.phase is not None else phases
                volt = min(used) if used and len(used) >= on else VOLTAGE_MIN
                if device.phase is not None and device.phase >= len(voltages):
                    volt = VOLTAGE_MIN
            else:
                volt = sum(used) / len(used) if used else NOMINAL_VOLTAGE
            f = NOMINAL_VOLTAGE / volt
            factor[config.id] = f
            devices.append(
                replace(
                    device,
                    max_charge_w=device.max_charge_w * f,
                    max_discharge_w=device.max_discharge_w * f,
                )
            )
        return devices, factor

    def _hold_without_meter(self, wanted: dict[str, float]) -> dict[str, float]:
        """Without a known grid measurement (meter gone for 10 s, a grid
        sensor unknown) the phase load is unknown: nothing is done (with
        control: the batteries go back to their own control). Told once."""
        if self._measurements.flow is not None:
            if self._meter_lost:
                self._meter_lost = False
                self._decisions.async_log("battery", "meter_back_resume")
            # The meter is there, but a real battery with a twin is unknown:
            # the grid without it is unknown (``_flow``), nothing is done.
            batteries = getattr(self, "_batteries", None)
            configs = getattr(batteries, "configs", [])
            twinned = twinned_ids(configs)
            unknown = [
                c.name
                for c in configs
                if c.id in twinned and batteries.states[c.id].power_w is None
            ]
            if unknown:
                if not getattr(self, "_twin_lost", False):
                    self._twin_lost = True
                    self._decisions.async_log(
                        "battery", "twin_real_unknown_hold", names=", ".join(unknown)
                    )
                return dict.fromkeys(wanted, 0.0)
            if getattr(self, "_twin_lost", False):
                self._twin_lost = False
                self._decisions.async_log("battery", "twin_real_back_resume")
            return wanted
        if not self._meter_lost and dt_util.utcnow() >= self._quiet_until:
            self._meter_lost = True
            self._decisions.async_log("battery", "meter_lost_hold")
        return dict.fromkeys(wanted, 0.0)

    def _round_flow(self, now: datetime):
        """The grid as zero on the meter sees it: the average over the round
        (when switched on, time-weighted), else the last value."""
        self._round_ignore = None
        flow = self._flow()
        interval = getattr(self._forecast, "react_interval", None) or STEP
        # From the previous round (an extra round soon after it does not
        # count again what that round already acted on), at most a round.
        start = now - interval
        if self._round_start is not None and self._round_start > start:
            start = self._round_start
        # The sample that was in force at the start of the round counts from
        # that start (else the beginning of the round is missing).
        older = [s for s in self._samples if s[0] < start]
        samples = [s for s in self._samples if s[0] >= start]
        if older:
            samples.insert(0, (start, *older[-1][1:]))
        if flow is None or not getattr(self._forecast, "react_average", True):
            return flow
        if len(samples) < 2:
            return flow
        grid = excluded = ignored = seconds = 0.0
        for (t1, g, x, i), (t2, *_rest) in zip(
            samples, [*samples[1:], (now, 0.0, 0.0, 0.0)], strict=True
        ):
            span = max((t2 - t1).total_seconds(), 0.0)
            grid += g * span
            excluded += x * span
            ignored += i * span
            seconds += span
        if seconds <= 0:
            return flow
        # The ignored spike over the same time as the grid (a peak that just
        # ended is still in the average: so is its ignored part).
        self._round_ignore = ignored / seconds
        return replace(flow, grid_w=grid / seconds, excluded_w=excluded / seconds)

    def _reserve_floor(self, now: datetime, *, peak: bool = True) -> float:
        """Lowest state of charge for the normal targets: the reserve, the
        night reserve at night, the peak reserve (below it only peak shaving
        discharges, in its own step; ``peak=False`` leaves it out)."""
        rules = self._forecast.rules
        data = self._forecast.data
        return max(
            rules.reserve_soc,
            rules.night_reserve_soc if data is not None and data.night_at(now) else 0.0,
            rules.peak_reserve_soc if peak and self._forecast.peak_w > 0 else 0.0,
        )

    def _intercept(
        self,
        wanted: dict[str, float],
        socs: dict[str, float],
        full: dict[str, Any],
        reasons: dict[str, str],
        now: datetime,
    ) -> dict[str, float]:
        """Run the chosen interceptor on the proposal; explain changes."""
        interceptor = getattr(
            self._forecast, "interceptor", None
        ) or create_interceptor(None, {})
        data = self._forecast.data
        flow = self._flow()
        plan = data.selected_plan if data is not None else None
        horizon = now + INTERCEPT_HORIZON
        proposals = []
        for config in self.virtual:
            state = self._batteries.states[config.id]
            temperature = (
                state_to_celsius(self.hass.states.get(config.temperature_sensor))
                if config.temperature_sensor
                else None
            )
            proposals.append(
                BatteryProposal(
                    id=config.id,
                    name=config.name,
                    phase=config.phase,
                    soc=socs[config.id],
                    power_w=state.power_w,
                    temperature_c=temperature,
                    capacity_kwh=config.capacity_kwh,
                    max_charge_w=config.max_charge_w,
                    max_discharge_w=config.max_discharge_w,
                    min_soc=config.min_soc,
                    # Held by the charge hysteresis: full for now (a
                    # redistribution must not charge it).
                    max_soc=min(socs[config.id], config.max_soc)
                    if config.id in self._full
                    else config.max_soc,
                    virtual=config.virtual,
                    full_charge=bool(full[config.id]),
                    proposed_w=wanted[config.id],
                    reason=reasons[config.id],
                    floor_soc=min(
                        max(
                            config.min_soc,
                            self._reserve_floor(
                                now, peak=reasons[config.id] != "peak_shaving"
                            ),
                        ),
                        config.max_soc,
                    ),
                )
            )
        outcome = run_interceptor(
            interceptor,
            InterceptInput(
                now=now,
                mode=data.plan_mode if data is not None else MODE_NOM,
                batteries=proposals,
                grid_w=flow.grid_w if flow else None,
                phase_w=tuple(flow.phase_w) if flow else (),
                phase_limit_w=self._limit_w(),
                house_w=flow.house_w if flow else None,
                pv_w=flow.pv_w if flow else None,
                excluded_w=flow.excluded_w if flow else None,
                spike_w=self._measurements.spike.ignore_w,
                slots=[
                    PriceSlot(s.start, s.end, s.price, s.export_price, s.power_w)
                    for s in (plan.slots if plan else [])
                    if s.end > now and s.start < horizon
                ],
            ),
        )
        self._explain_intercept(interceptor, outcome)
        return outcome.powers

    def _explain_intercept(self, interceptor: Any, outcome: Any) -> None:
        """Why: once when the interceptor fails, and when what it changes
        changes (not every second)."""
        name = interceptor.name or interceptor.key
        if outcome.failed and not self._intercept_failed:
            self._decisions.async_log("battery", "interceptor_failed", name=name)
        self._intercept_failed = outcome.failed
        self.intercepted = outcome.changes
        names = {c.id: c.name for c in self.virtual}
        dutch = (self.hass.config.language or "").startswith("nl")
        words = (
            {
                "reject": "tegengehouden",
                "release": "vrijgegeven",
                "limit": "beperkt tot",
            }
            if dutch
            else {"reject": "held back", "release": "released", "limit": "limited to"}
        )
        parts = [
            f"{names.get(i, i)} {words.get(action, action)}"
            + (f" {abs(power):.0f} W" if action == "limit" else "")
            + (f" ({reason})" if reason else "")
            for i, action, power, reason in outcome.changes
        ]
        # Only the kind of change counts, not every watt of a limit.
        gist = "|".join(
            f"{i}:{action}:{reason}" for i, action, _power, reason in outcome.changes
        )
        if gist == self._intercept_gist:
            return
        self._intercept_gist = gist
        if parts:
            self._decisions.async_log(
                "battery", "interceptor_changed", name=name, changes="; ".join(parts)
            )
        else:
            self._decisions.async_log("battery", "interceptor_cleared", name=name)

    def _observe_quality(self, now: datetime) -> None:
        """The round that ends now, if the batteries could follow in it: the
        grid as it would have been with them, against the target."""
        power, self._quality_round = self._quality_round, None
        if power is None:
            return
        flow = self._round_flow(now)
        if flow is None:
            return
        # The simulated grid's distance to the target, as zero on the meter
        # sees it (``nom_balance``): a surplus is all to charge, a shortage
        # never counts the excluded devices or an ignored peak.
        error = flow.grid_w + power - self._forecast.rules.nom_target_w
        if error > 0:
            ignore = self._forecast.spike_ignore_w(
                self._measurements.spike.ignore_w, now
            )
            error = max(error - flow.excluded_w - max(ignore, 0.0), 0.0)
        self.quality.add(now, error, power)

    def _response(self, battery_id: str) -> BatteryResponse:
        if battery_id not in self._responses:
            self._responses[battery_id] = BatteryResponse(
                getattr(self._forecast, "sim_delay_s", 0.0),
                getattr(self._forecast, "sim_ramp_w_s", 0.0),
            )
        return self._responses[battery_id]

    @property
    def held(self) -> set[str]:
        """Virtual batteries the charge hysteresis holds now (were full,
        not yet below the band)."""
        return set(self._full)

    @staticmethod
    def _follows_nom(data: Any) -> bool:
        """Zero on the meter live: the NOM mode, or a plan that fell back to
        it (an own planner failed, arbitrage without prices)."""
        if data is None:
            return True
        plan = data.selected_plan
        strategy = plan.strategy if plan is not None else data.plan_mode
        return data.plan_mode == MODE_NOM or strategy == MODE_NOM

    def _limit_w(self) -> float:
        return phase_limit_w(
            self._measurements.max_current, self._forecast.phase_margin
        )

    def step(self, now: datetime) -> None:
        """Let every virtual battery act for the time since the previous step."""
        last, self._last = self._last, now
        self._round_start = last  # zero on the meter averages from here
        if last is None:
            return
        elapsed = min(now - last, MAX_STEP)
        hours = elapsed.total_seconds() / 3600
        if hours <= 0:
            return
        self._observe_quality(now)
        data = self._forecast.data
        full = {
            c.id: data.full_charge_now(c.id, now) if data else None
            for c in self.virtual
        }
        for config in self.virtual:
            # A full charge that reached 100 % is done: the battery follows
            # the others again (and no longer sets their direction).
            soc = self._batteries.states[config.id].soc
            if full[config.id] and (soc if soc is not None else 0.0) >= 100.0 - 0.01:
                full[config.id] = None
        # What the batteries charging fully take of the surplus: their power
        # now when they react with a delay, else at once their max power.
        self._full_w = sum(
            max(self._batteries.states[c.id].power_w or 0.0, 0.0)
            if self._response(c.id).active
            else c.max_charge_w
            for c in self.virtual
            if full[c.id]
        )
        targets = self._targets(now, hours, [c for c in self.virtual if not full[c.id]])
        socs: dict[str, float] = {}
        wanted: dict[str, float] = {}
        for config in self.virtual:
            state = self._batteries.states[config.id]
            socs[config.id] = soc = (
                state.soc if state.soc is not None else config.initial_soc
            )
            # Forced full charge: max power up to 100 %, above the normal max.
            wanted[config.id] = (
                config.max_charge_w if full[config.id] else targets(config, soc)
            )
        cap = self._forecast.rules.max_charge_w
        if cap > 0:
            # The system's max charge power counts for all together, a full
            # charge first, the others what is left (as in the plan).
            fulls = [i for i in wanted if full[i] and wanted[i] > 0]
            full_sum = sum(wanted[i] for i in fulls)
            if full_sum > cap:
                for i in fulls:
                    wanted[i] *= cap / full_sum
                full_sum = cap
            rest = [i for i in wanted if not full[i] and wanted[i] > 0]
            rest_sum = sum(wanted[i] for i in rest)
            if rest_sum > cap - full_sum:
                for i in rest:
                    wanted[i] *= max(cap - full_sum, 0.0) / rest_sum
        asked = dict(wanted)  # before protections and limits
        nom = self._follows_nom(data)
        reasons = {
            c.id: "full_charge" if full[c.id] else "zero_on_meter" if nom else "plan"
            for c in self.virtual
        }
        # A full charge sets the direction before the protections, so they
        # work from what the batteries will do (a discharge the full charge
        # would stop afterwards does not relieve a phase or the peak).
        wanted = one_direction(wanted, [i for i in wanted if full.get(i)])
        before = dict(wanted)
        wanted = self._phase_relief(wanted, socs, full, now, hours)
        # Protecting a phase: the batteries relief changed, and those whose
        # power (in the right direction) it already counted as relief.
        reasons.update(
            {
                i: "phase_relief"
                for i in wanted
                if abs(wanted[i] - before[i]) > 1.0 or i in self._relief_helpers
            }
        )
        self._relief_ids = {i for i, r in reasons.items() if r == "phase_relief"}
        before = dict(wanted)
        wanted = self._peak_shaving(wanted, socs, full, now, hours)
        # Protecting the peak: the batteries it made discharge. One it only
        # let charge less protects nothing (it does not set the direction).
        reasons.update(
            {
                i: "peak_shaving"
                for i in wanted
                if wanted[i] < -0.5
                and (abs(wanted[i] - before[i]) > 1.0 or i in self._peak_helpers)
                and reasons.get(i) != "phase_relief"
            }
        )
        # The user's last say (interceptor module), then HomeBatteryAssist's
        # own final check (phase limits here, power and state of charge in
        # limit_power), which always wins.
        proposed = dict(wanted)
        wanted = self._intercept(wanted, socs, full, reasons, now)
        overruled = any(abs(wanted[i] - proposed[i]) > 1.0 for i in wanted)
        # Protection is not the interceptor's to undo: where phase relief or
        # peak shaving set the power, that power stands.
        for i, reason in reasons.items():
            if reason in ("phase_relief", "peak_shaving"):
                wanted[i] = proposed[i]
        # Never one battery charging while another discharges: protection
        # first, then a full charge sets the direction; else the net stands.
        wanted = one_direction(
            wanted,
            [i for i, r in reasons.items() if r in ("phase_relief", "peak_shaving")],
            [i for i in wanted if full.get(i)],
        )
        wanted = self._phase_limited(wanted, now)
        # The system's max charge / discharge power is a hard limit, also for
        # protection (phase relief, peak shaving) — the owner's decision.
        wanted = system_limited(wanted, self._forecast.rules)
        wanted = self._hold_without_meter(wanted)
        powers: dict[str, float] = {}
        commands: dict[str, float] = {}
        reacting: dict[str, float] = {}
        efficiencies: dict[str, float] = {}
        for config in self.virtual:
            limits = replace(config, max_soc=100.0) if full[config.id] else config
            efficiencies[config.id] = random_efficiency(config)
            # What the battery is told (within its limits), and what it does
            # with it: at once, or with a simulated delay and ramp.
            commands[config.id], _ = limit_power(
                limits,
                socs[config.id],
                wanted[config.id],
                hours,
                efficiencies[config.id],
            )
            reacting[config.id] = self._response(config.id).apply(
                now, commands[config.id]
            )
        commanded_both = any(w > 0.5 for w in commands.values()) and any(
            w < -0.5 for w in commands.values()
        )
        if (
            not commanded_both
            and any(w > 0.5 for w in reacting.values())
            and any(w < -0.5 for w in reacting.values())
        ):
            # A battery still ramping out of the old direction: the others
            # wait at 0 until it is there (never one charging while another
            # discharges, also while they react). Not when both directions
            # were commanded: that is the protection of two phases
            # overloaded the opposite way (one_direction), which stands.
            direction = 1 if sum(commands.values()) >= 0 else -1
            for i, w in reacting.items():
                if w * direction > 0.5 and any(
                    v * direction < -0.5 for v in reacting.values()
                ):
                    reacting[i] = 0.0
                    self._response(i).hold(0.0, now)
        for config in self.virtual:
            limits = replace(config, max_soc=100.0) if full[config.id] else config
            power, soc = limit_power(
                limits,
                socs[config.id],
                reacting[config.id],
                hours,
                efficiencies[config.id],
            )
            if abs(power - reacting[config.id]) > 0.5:
                self._response(config.id).hold(power, now)  # full / empty: stops
            powers[config.id] = power
            self._batteries.set_virtual(config.id, now, power, soc, now - elapsed)
        # A round counts for the control quality when zero on the meter
        # could do what it asked (no protection, limit or full battery).
        placed = sum(asked[c.id] for c in self.virtual if not full[c.id])
        free = (
            nom
            and self._nom_free
            and abs(placed - self._nom_total) <= 1.0
            and all(
                reasons[i] == "zero_on_meter" and abs(commands[i] - asked[i]) <= 1.0
                for i in powers
            )
        )
        self._quality_round = sum(powers.values()) if free else None
        # Protection or the interceptor set a power this round: next round
        # zero on the meter starts from what it wants, not from that power.
        self._protected_last = overruled or any(
            r in ("phase_relief", "peak_shaving") for r in reasons.values()
        )
        self._commands = (
            {c.id: commands[c.id] for c in self.virtual if not full[c.id]}
            if nom
            else {}
        )
        # A new round: the grid now (for jumps), and start the average anew.
        flow = self._flow()
        self._step_grid = flow.grid_w if flow is not None else None
        self._samples = self._samples[-1:]

    def _phase_relief(
        self,
        wanted: dict[str, float],
        socs: dict[str, float],
        full: dict[str, Any],
        now: datetime,
        hours: float,
    ) -> dict[str, float]:
        """Phase protection: take load off an overloaded phase; explain it."""
        self._relief_helpers = set()
        flow = self._flow()
        if flow is None or not flow.phase_w:
            return wanted
        phases = len(flow.phase_w)
        devices, factor = self._nominal_devices(flow, phases)
        # Active power per phase in the same (nominal current) terms as the
        # load, so the relief takes the reactive part into account.
        loads = flow.phase_load_w
        active = _active_loads(flow)
        result, relieved = relieve(
            {i: w * factor[i] for i, w in wanted.items()},
            devices,
            active_relief_loads(loads, active, self._limit_w()),
            self._limit_w(),
            can_discharge=[
                c.id
                for c in self.virtual
                if socs[c.id] > c.min_soc + 0.01 and not full[c.id]
            ],
            can_charge=[c.id for c in self.virtual if socs[c.id] < c.max_soc - 0.01],
        )
        if not relieved:
            # Nothing overloaded: the powers as they were (no rounding
            # through the voltage factor, which would mark them as relief).
            self.relief_now = {}
            result = dict(wanted)
        else:
            result = {i: w / factor[i] for i, w in result.items()}
        names = {c.id: c.name for c in self.virtual}
        dutch = (self.hass.config.language or "").startswith("nl")
        self.relief_now = dict(relieved)
        for index, power in relieved.items():
            event = self.relief.get(index)
            # Only those working against the overload (discharging on an
            # importing phase, charging on an exporting one).
            sign = -1.0 if flow.phase_load_w[index] > 0 else 1.0
            helpers = [
                d.id
                for d in devices
                if d.phase in (index, None) and result[d.id] * sign > 1
            ]
            if event is None:
                discharging = flow.phase_load_w[index] > 0
                self.relief[index] = event = {
                    "start": now,
                    "wh": 0.0,
                    "names": {names[i] for i in helpers},
                }
                self._decisions.async_log(
                    "battery",
                    "phase_relief",
                    names=", ".join(sorted(event["names"])) or "-",
                    action=(
                        ("ontladen" if discharging else "laden")
                        if dutch
                        else ("discharge" if discharging else "charge")
                    ),
                    power=f"{power:.0f} W",
                    phase=f"L{index + 1}",
                    current=f"{flow.phase_current(index):.1f}",
                    limit=f"{self._limit_w() / NOMINAL_VOLTAGE:.1f}",
                )
            event["seen"] = now
            event["wh"] += power * hours
            event["names"] |= {names[i] for i in helpers}
            self._relief_helpers.update(helpers)
        for index, event in list(self.relief.items()):
            if index not in relieved and now - event["seen"] >= RELIEF_END_AFTER:
                del self.relief[index]
                minutes = max(
                    round((event["seen"] - event["start"]).total_seconds() / 60), 1
                )
                self._decisions.async_log(
                    "battery",
                    "phase_relief_ended",
                    phase=f"L{index + 1}",
                    names=", ".join(sorted(event["names"])) or "-",
                    minutes=minutes,
                    energy=f"{event['wh'] / 1000:.2f}".replace(
                        ".", "," if dutch else "."
                    ),
                )
        return result

    def _peak_shaving(
        self,
        wanted: dict[str, float],
        socs: dict[str, float],
        full: dict[str, Any],
        now: datetime,
        hours: float,
    ) -> dict[str, float]:
        """Keep the total grid import below the peak limit; explain it."""
        self._peak_helpers = set()
        peak = self._forecast.peak_w
        flow = self._flow()
        if peak <= 0 or flow is None:
            return wanted
        phases = max(len(flow.phase_w), 1)
        devices = [PhaseDevice.from_config(c, phases) for c in self.virtual]
        result, shaved = shave_peak(
            wanted,
            devices,
            flow.grid_w
            - (0.0 if self._forecast.peak_include_excluded else flow.excluded_w),
            peak,
            [
                c.id
                for c in self.virtual
                if socs[c.id]
                > max(c.min_soc, self._reserve_floor(now, peak=False)) + 0.01
                and not full[c.id]
            ],
            keep=getattr(self, "_relief_ids", set()),
        )
        # Above the peak without the batteries: every one discharging now
        # protects it (also one that already did, unchanged by shave_peak).
        checked_now = flow.grid_w - (
            0.0 if self._forecast.peak_include_excluded else flow.excluded_w
        )
        if checked_now - peak > 0.5:
            self._peak_helpers = {i for i, w in result.items() if w < -0.5}
        dutch = (self.hass.config.language or "").startswith("nl")
        self.peak_now = shaved
        if shaved > 0:
            event = self._peak
            if event is None:
                names = [
                    c.name
                    for c in self.virtual
                    if abs(result[c.id] - wanted.get(c.id, 0.0)) > 1
                ]
                checked = flow.grid_w - (
                    0.0 if self._forecast.peak_include_excluded else flow.excluded_w
                )
                self._peak = event = {"start": now, "wh": 0.0}
                self._decisions.async_log(
                    "battery",
                    "peak_shaving",
                    grid=f"{checked + sum(wanted.values()):.0f} W",
                    limit=f"{peak:.0f} W",
                    names=", ".join(names) or "-",
                    power=f"{shaved:.0f} W",
                )
            event["seen"] = now
            event["wh"] += shaved * hours
        elif self._peak is not None and now - self._peak["seen"] >= RELIEF_END_AFTER:
            event, self._peak = self._peak, None
            self._decisions.async_log(
                "battery",
                "peak_shaving_ended",
                minutes=max(
                    round((event["seen"] - event["start"]).total_seconds() / 60), 1
                ),
                energy=f"{event['wh'] / 1000:.2f}".replace(".", "," if dutch else "."),
            )
        return result

    def _phase_limited(
        self, wanted: dict[str, float], now: datetime
    ) -> dict[str, float]:
        """Hold the powers within the phase limits; explain when that starts/ends.

        HomeBatteryAssist's own final check: from the worst case of what the
        measurement says (``phase_loads``); without a measurement nothing
        runs."""
        flow = self._flow()
        if flow is None or not flow.phase_w:
            self.limited_phases = []
            return dict.fromkeys(wanted, 0.0)
        phases = len(flow.phase_w)
        max_current = self._measurements.max_current
        devices, factor = self._nominal_devices(flow, phases, worst=True)
        capped, limited = cap_powers(
            {i: w * factor[i] for i, w in wanted.items()},
            devices,
            phase_loads(flow),
            self._limit_w(),
        )
        # Back to W; never more than asked (rounding through the factor).
        capped = {
            i: wanted[i]
            if math.isfinite(wanted[i]) and abs(w / factor[i]) >= abs(wanted[i])
            else w / factor[i]
            for i, w in capped.items()
        }
        self.limited_phases = limited
        if limited:
            self._limit_seen = now
            if not self._limit_logged:
                self._limit_logged = True
                names = {c.id: c.name for c in self.virtual}
                held = [i for i in wanted if abs(capped[i]) < abs(wanted[i]) - 1]
                self._decisions.async_log(
                    "battery",
                    "phase_limit",
                    names=", ".join(names[i] for i in held) or "-",
                    power=f"{sum(abs(capped[i]) for i in held):.0f} W",
                    phase=", ".join(f"L{i + 1}" for i in limited),
                    current=", ".join(f"{flow.phase_current(i):.1f}" for i in limited),
                    max=max_current,
                    margin=round(self._forecast.phase_margin),
                )
        elif (
            self._limit_logged
            and self._limit_seen is not None
            and now - self._limit_seen >= LIMIT_CLEAR_AFTER
        ):
            self._limit_logged = False
            self._decisions.async_log("battery", "phase_limit_cleared")
        return capped

    def _targets(self, now: datetime, hours: float, virtual: list[BatteryConfig]):
        """A function (config, soc) -> target power (W, + charging) per battery.

        The total for the virtual batteries is spread with ``distribute``:
        few batteries at low power, more when more power is needed.
        """
        data = self._forecast.data
        plan = data.selected_plan if data is not None else None
        blocked, unlimited = False, None  # zero on the meter: see below
        if data is not None and not self._follows_nom(data) and plan and plan.slots:
            # Arbitrage: the virtual batteries' share of the planned power (the
            # plan without full charges: those are run per battery).
            slot = next((s for s in plan.slots if s.start <= now < s.end), None)
            states = [s for s in self._batteries.plan_states() if s.soc is not None]
            capacity = sum(s.config.capacity_kwh for s in states)
            virtual_capacity = sum(
                s.config.capacity_kwh for s in states if s.config.virtual
            )
            planned = slot.power_w if slot else 0.0
            if planned > 0 and slot is not None:
                # The full charges in it run per battery (at their own
                # power): the plan's part for them is not spread again over
                # the virtual batteries (a battery already full has none).
                full_soc = {s.config.id: s.soc for s in states if s.soc is not None}
                charging_fully = {
                    i: w
                    for i, w in data.forced_by.get(slot.start, {}).items()
                    if full_soc.get(i, 0.0) < 100.0 - 0.01
                }
                planned = max(planned - sum(charging_fully.values()), 0.0)
                # The rest is the share of the batteries not charging fully.
                rest = [s for s in states if s.config.id not in charging_fully]
                capacity = sum(s.config.capacity_kwh for s in rest)
                virtual_capacity = sum(
                    s.config.capacity_kwh for s in rest if s.config.virtual
                )
            total = planned * virtual_capacity / capacity if slot and capacity else 0.0
            # The real solar surplus instead of the forecast one: more is
            # stored on top of the plan, less is not taken from the grid.
            flow = self._flow()
            forecast_slot = data.consumption_at(now)
            # The PV forecast of the hour now (not of the hour in which the
            # last cycle ran).
            pv_now = data.pv_at(now) if self._forecast.pv_entries else None
            if (
                flow is not None
                and self._measurements.has_pv
                and self._measurements.pv_known
                and pv_now is not None
                and forecast_slot is not None
            ):
                total = plan_balance(
                    total,
                    # The surplus that is really left: what real batteries
                    # (by their own control) store is not there twice.
                    min(solar_surplus_w(flow), max(-flow.grid_w, 0.0)),
                    pv_now - forecast_slot.power_w,
                    self._forecast.pv_deviation_w,
                )
            # A planned discharge only as far as it is needed now: never
            # battery energy into the grid that the plan did not choose.
            if flow is not None and slot is not None:
                total = planned_discharge(total, flow, slot.grid_w)
            self._pd.reset()  # zero on the meter starts anew later
            self._commands = {}
            self._nom_free = False
        else:
            # NOM: the real surplus (+) / shortage (-) on the grid right now,
            # around the target grid power; a shortage never for excluded
            # devices nor for a random short peak (when switched on).
            flow = self._round_flow(now)
            rules = self._forecast.rules
            ignore = self._forecast.spike_ignore_w(
                self._round_ignore
                if self._round_ignore is not None
                else self._measurements.spike.ignore_w,
                now,
            )
            total = (
                nom_balance(flow, rules.nom_target_w, ignore)
                if flow is not None
                else 0.0
            )
            if total > 0:
                # A virtual battery charging fully takes part of the surplus
                # (the measured grid does not contain virtual power).
                total = max(total - self._full_w, 0.0)
            price = self._batteries.price_now()
            blocked = (
                total < 0
                and rules.min_discharge_price is not None
                and price is not None
                and price < rules.min_discharge_price
            )
            if blocked:
                total = 0.0  # discharging only at a high enough price
            if flow is not None:
                # As a real controller: from the previous command and what the
                # batteries (these, not the ones charging fully) do now.
                # What they do now, as the meter sees it when it looks (with a
                # simulated delay / ramp: the power at this moment).
                actual = sum(
                    self._response(c.id).power_at(now)
                    if self._response(c.id).active
                    else self._batteries.states[c.id].power_w or 0.0
                    for c in virtual
                )
                commanded = (
                    sum(self._commands[c.id] for c in virtual)
                    if virtual and all(c.id in self._commands for c in virtual)
                    else None  # another set of batteries: from what they do
                )
                interval = getattr(self._forecast, "react_interval", None) or STEP
                if self._protected_last:
                    # Protection (or the interceptor) set the power last
                    # round: zero on the meter starts anew from what it wants,
                    # not from the protection's power.
                    self._pd.reset()
                    commanded = None
                    actual = total
                total = self._pd.step(
                    total,
                    actual,
                    commanded,
                    # Direct: the whole gap in every round (also an extra
                    # one); PD: its gain per reaction interval of time.
                    1.0 if self._direct else hours * 3600 / interval.total_seconds(),
                )
            else:
                self._pd.reset()  # no meter: start anew when it is back
            unlimited = total
        rules = self._forecast.rules
        if total > 0 and rules.max_charge_w > 0:
            total = min(total, rules.max_charge_w)
        if total < 0 and rules.max_discharge_w > 0:
            total = max(total, -rules.max_discharge_w)
        if unlimited is not None:
            # A round counts for the control quality only when zero on the
            # meter could have its way (no rule or limit held it back).
            self._nom_free = flow is not None and not blocked and total == unlimited
            self._nom_total = total

        candidates = []
        hysteresis = self._forecast.rules.charge_hysteresis
        # Lowest state of charge for the normal targets: the reserve, the
        # night reserve at night, the peak reserve (below it only peak
        # shaving discharges, in its own step).
        floor = self._reserve_floor(now)
        for config in virtual:
            state = self._batteries.states[config.id]
            soc_now = state.soc if state.soc is not None else config.initial_soc
            if hysteresis > 0 and soc_now >= config.max_soc - 0.05:
                self._full.add(config.id)
            elif soc_now < config.max_soc - hysteresis:
                self._full.discard(config.id)
            candidates.append(
                Candidate(
                    config.id,
                    state.soc if state.soc is not None else config.initial_soc,
                    min(max(config.min_soc, floor), config.max_soc),
                    soc_now if config.id in self._full else config.max_soc,
                    config.max_charge_w,
                    config.max_discharge_w,
                )
            )
        shares, switch = self._distributor.distribute(
            total,
            candidates,
            self._forecast.min_battery_power,
            now,
            getattr(self._forecast.rules, "charge_sequential", False),
        )
        if switch:
            names = {c.id: c.name for c in virtual}
            socs = {c.id: c.soc for c in candidates}
            new, old = switch
            dutch = (self.hass.config.language or "").startswith("nl")
            action = (
                ("laden" if total > 0 else "ontladen")
                if dutch
                else ("charging" if total > 0 else "discharging")
            )
            self._decisions.async_log(
                "battery",
                "battery_switch",
                new=names[new],
                old=names[old],
                action=action,
                new_soc=round(socs[new]),
                old_soc=round(socs[old]),
            )
        return lambda config, soc: shares.get(config.id, 0.0)
