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
from ...planning.battery_distribution import Candidate, Distributor
from ...planning.battery_plan import MODE_NOM
from ...planning.phase_limit import (
    PhaseDevice,
    active_relief_loads,
    cap_powers,
    overloaded,
    phase_limit_w,
    relieve,
    shave_peak,
)
from ...units import state_to_celsius

_LOGGER = logging.getLogger(__name__)

# The round is a setting (react_interval_s, default 5 s); this is the fallback.
STEP = timedelta(seconds=5)
MAX_STEP = timedelta(minutes=5)  # longer gaps (restart) are not simulated
LIMIT_CLEAR_AFTER = timedelta(minutes=5)  # no phase limit this long: log it
INTERCEPT_HORIZON = timedelta(hours=8)  # coming slots an interceptor sees
RELIEF_END_AFTER = timedelta(minutes=1)  # phase back under the limit this long
REACT_INTERVAL = timedelta(seconds=2)  # fastest extra step on an overload


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
    elif target_w < 0:
        available = max(soc - config.min_soc, 0.0) * wh_per_pct
        power = -min(
            -target_w, config.max_discharge_w, available * eff / hours if hours else 0
        )
        soc += power * hours / eff / wh_per_pct
    else:
        power = 0.0
    return round(power, 1) + 0.0, round(min(max(soc, 0.0), 100.0), 3)


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
            q = math.sqrt(max((measured[i] * v) ** 2 - flow.phase_w[i] ** 2, 0.0))
            amps.append(round(math.hypot(phase_w[i], q) / v, 2))
        phase_a = tuple(amps)
    return replace(
        flow,
        grid_w=flow.grid_w - total,
        battery_w=flow.battery_w - total,
        phase_w=tuple(phase_w),
        phase_a=phase_a,
    )


def random_efficiency(config: BatteryConfig) -> float:
    """Round-trip efficiency for one step: a random loss within the range."""
    return 1 - random.uniform(config.loss_min, config.loss_max)


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
        self.hass = hass
        self._decisions = decisions
        self._distributor = Distributor(forecast.balance_interval)
        self._batteries = batteries
        self._measurements = measurements
        self._forecast = forecast
        self._last: datetime | None = None
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
        self._samples: list[tuple[datetime, float, float]] = []
        self._step_grid: float | None = None
        self._meter_lost = False  # grid unknown: batteries held
        # No message while the meter starts up after a (re)start.
        self._quiet_until = dt_util.utcnow() + timedelta(minutes=2)
        # The interceptor (the user's last say) and what it did lately.
        self.intercepted: list[tuple[str, str, float, str]] = []
        self._intercept_gist = ""
        self._intercept_failed = False

    def _flow(self) -> Any:
        """The grid as the virtual batteries see it: measured, without the
        real batteries that have a twin (the twin acts in their place)."""
        flow = self._measurements.flow
        if flow is None:
            return None
        twinned = twinned_ids(self._batteries.configs)
        if not twinned:
            return flow
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
            self._samples.append((when, flow.grid_w, flow.excluded_w))
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
        if (
            overloaded(with_virtual, self._limit_w())
            or overloaded(flow.phase_load_w, self._limit_w())
            or (peak > 0 and sum(with_virtual) > peak)
        ):
            self.step(when)

    def _nominal_devices(
        self, flow: Any, phases: int
    ) -> tuple[list[PhaseDevice], dict[str, float]]:
        """The batteries for the phase checks in current terms: the phase
        limit and load are current x 230 V, so a battery's power counts as
        power x 230 / (measured voltage of its phase(s)); ``factor`` per
        battery (1 without a measured voltage), to convert back after."""
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
            f = NOMINAL_VOLTAGE / (sum(used) / len(used)) if used else 1.0
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
            return wanted
        if not self._meter_lost and dt_util.utcnow() >= self._quiet_until:
            self._meter_lost = True
            self._decisions.async_log("battery", "meter_lost_hold")
        return dict.fromkeys(wanted, 0.0)

    def _round_flow(self, now: datetime):
        """The grid as zero on the meter sees it: the average over the round
        (when switched on, time-weighted), else the last value."""
        flow = self._flow()
        interval = getattr(self._forecast, "react_interval", None) or STEP
        start = now - interval
        # The sample that was in force at the start of the round counts from
        # that start (else the beginning of the round is missing).
        older = [s for s in self._samples if s[0] < start]
        samples = [s for s in self._samples if s[0] >= start]
        if older:
            samples.insert(0, (start, older[-1][1], older[-1][2]))
        if flow is None or not getattr(self._forecast, "react_average", True):
            return flow
        if len(samples) < 2:
            return flow
        grid = excluded = seconds = 0.0
        for (t1, g, x), (t2, _g, _x) in zip(
            samples, [*samples[1:], (now, 0.0, 0.0)], strict=True
        ):
            span = max((t2 - t1).total_seconds(), 0.0)
            grid += g * span
            excluded += x * span
            seconds += span
        if seconds <= 0:
            return flow
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
                    max_soc=config.max_soc,
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

    def _limit_w(self) -> float:
        return phase_limit_w(
            self._measurements.max_current, self._forecast.phase_margin
        )

    def step(self, now: datetime) -> None:
        """Let every virtual battery act for the time since the previous step."""
        last, self._last = self._last, now
        if last is None:
            return
        elapsed = min(now - last, MAX_STEP)
        hours = elapsed.total_seconds() / 3600
        if hours <= 0:
            return
        data = self._forecast.data
        full = {
            c.id: data.full_charge_now(c.id, now) if data else None
            for c in self.virtual
        }
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
        nom = data is None or data.plan_mode == MODE_NOM
        reasons = {
            c.id: "full_charge" if full[c.id] else "zero_on_meter" if nom else "plan"
            for c in self.virtual
        }
        before = dict(wanted)
        wanted = self._phase_relief(wanted, socs, full, now, hours)
        reasons.update({i: "phase_relief" for i in wanted if wanted[i] != before[i]})
        before = dict(wanted)
        wanted = self._peak_shaving(wanted, socs, full, now, hours)
        reasons.update({i: "peak_shaving" for i in wanted if wanted[i] != before[i]})
        # The user's last say (interceptor module), then HomeBatteryAssist's
        # own final check (phase limits here, power and state of charge in
        # limit_power), which always wins.
        proposed = dict(wanted)
        wanted = self._intercept(wanted, socs, full, reasons, now)
        # Protection is not the interceptor's to undo: where phase relief or
        # peak shaving set the power, that power stands.
        for i, reason in reasons.items():
            if reason in ("phase_relief", "peak_shaving"):
                wanted[i] = proposed[i]
        wanted = self._phase_limited(wanted, now)
        wanted = self._hold_without_meter(wanted)
        for config in self.virtual:
            limits = replace(config, max_soc=100.0) if full[config.id] else config
            power, soc = limit_power(
                limits,
                socs[config.id],
                wanted[config.id],
                hours,
                random_efficiency(config),
            )
            self._batteries.set_virtual(config.id, now, power, soc)
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
        flow = self._flow()
        if flow is None or not flow.phase_w:
            return wanted
        phases = len(flow.phase_w)
        devices, factor = self._nominal_devices(flow, phases)
        # Active power per phase in the same (nominal current) terms as the
        # load, so the relief takes the reactive part into account.
        # Only where the reactive part is really known: a measured voltage,
        # or a power factor without a measured current; else the load as it
        # is (a voltage below 230 V must not look like reactive power).
        volts = tuple(getattr(flow, "phase_v", ()) or ())
        amps = tuple(getattr(flow, "phase_a", ()) or ())
        pfs = tuple(getattr(flow, "phase_pf", ()) or ())
        loads = flow.phase_load_w
        active = [
            p * NOMINAL_VOLTAGE / volts[i]
            if i < len(volts) and volts[i] > 100
            else p
            if i >= len(amps) and i < len(pfs) and pfs[i]
            else abs(loads[i])
            for i, p in enumerate(flow.phase_w)
        ]
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
        result = {i: w / factor[i] for i, w in result.items()}
        names = {c.id: c.name for c in self.virtual}
        dutch = (self.hass.config.language or "").startswith("nl")
        self.relief_now = dict(relieved)
        for index, power in relieved.items():
            event = self.relief.get(index)
            helpers = [
                d.id
                for d in devices
                if d.phase in (index, None) and abs(result[d.id]) > 1
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
        )
        dutch = (self.hass.config.language or "").startswith("nl")
        self.peak_now = shaved
        if shaved > 0:
            event = self._peak
            if event is None:
                names = [c.name for c in self.virtual if abs(result[c.id]) > 1]
                self._peak = event = {"start": now, "wh": 0.0}
                self._decisions.async_log(
                    "battery",
                    "peak_shaving",
                    grid=f"{flow.grid_w + sum(wanted.values()):.0f} W",
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
        """Hold the powers within the phase limits; explain when that starts/ends."""
        flow = self._flow()
        if flow is None or not flow.phase_w:
            return wanted
        phases = len(flow.phase_w)
        max_current = self._measurements.max_current
        devices, factor = self._nominal_devices(flow, phases)
        capped, limited = cap_powers(
            {i: w * factor[i] for i, w in wanted.items()},
            devices,
            flow.phase_load_w,
            self._limit_w(),
        )
        capped = {i: w / factor[i] for i, w in capped.items()}
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
        if data is not None and data.plan_mode != MODE_NOM and plan and plan.slots:
            # Arbitrage: the virtual batteries' share of the planned power (the
            # plan without full charges: those are run per battery).
            slot = next((s for s in plan.slots if s.start <= now < s.end), None)
            states = [s for s in self._batteries.plan_states() if s.soc is not None]
            capacity = sum(s.config.capacity_kwh for s in states)
            virtual_capacity = sum(
                s.config.capacity_kwh for s in states if s.config.virtual
            )
            total = (
                slot.power_w * virtual_capacity / capacity if slot and capacity else 0.0
            )
            # The real solar surplus instead of the forecast one: more is
            # stored on top of the plan, less is not taken from the grid.
            flow = self._flow()
            forecast_slot = data.consumption_at(now)
            if (
                flow is not None
                and self._measurements.has_pv
                and self._measurements.pv_known
                and data.pv_now_w is not None
                and forecast_slot is not None
            ):
                total = plan_balance(
                    total,
                    solar_surplus_w(flow),
                    data.pv_now_w - forecast_slot.power_w,
                    self._forecast.pv_deviation_w,
                )
            # A planned discharge only as far as it is needed now: never
            # battery energy into the grid that the plan did not choose.
            if flow is not None and slot is not None:
                total = planned_discharge(total, flow, slot.grid_w)
        else:
            # NOM: the real surplus (+) / shortage (-) on the grid right now,
            # around the target grid power; a shortage never for excluded
            # devices nor for a random short peak (when switched on).
            flow = self._round_flow(now)
            rules = self._forecast.rules
            ignore = self._forecast.spike_ignore_w(
                self._measurements.spike.ignore_w, now
            )
            total = (
                nom_balance(flow, rules.nom_target_w, ignore)
                if flow is not None
                else 0.0
            )
            price = self._batteries.price_now()
            if (
                total < 0
                and rules.min_discharge_price is not None
                and price is not None
                and price < rules.min_discharge_price
            ):
                total = 0.0  # discharging only at a high enough price
        rules = self._forecast.rules
        if total > 0 and rules.max_charge_w > 0:
            total = min(total, rules.max_charge_w)
        if total < 0 and rules.max_discharge_w > 0:
            total = max(total, -rules.max_discharge_w)

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
            total, candidates, self._forecast.min_battery_power, now
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
