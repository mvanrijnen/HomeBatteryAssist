"""Live simulation of virtual batteries (what-if).

Every ``STEP`` the simulator lets each virtual battery act according to the
selected plan mode, using the real measurements:

- ``nom``: absorb the real surplus / cover the real shortage measured on the
  grid right now (after the real batteries);
- ``arbitrage``: follow the battery plan of the current slot, for the virtual
  batteries' share of the planned capacity.

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

from ..const import NOMINAL_VOLTAGE
from ..explain import DecisionLog
from ..forecasts.coordinator import ForecastCoordinator
from ..inputs.batteries import BatteryConfig, BatteryInput
from ..inputs.measurements import MeasurementInput
from ..planning.battery_plan import ARBITRAGE_MODES
from ..planning.distribution import Candidate, Distributor
from ..planning.phase_limit import (
    PhaseDevice,
    cap_powers,
    overloaded,
    phase_limit_w,
    relieve,
    shave_peak,
)

_LOGGER = logging.getLogger(__name__)

STEP = timedelta(seconds=30)
MAX_STEP = timedelta(minutes=5)  # longer gaps (restart) are not simulated
LIMIT_CLEAR_AFTER = timedelta(minutes=5)  # no phase limit this long: log it
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
        self._unsub = async_track_time_interval(self.hass, self._async_step, STEP)
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
        """React at once when a phase is overloaded (or the virtual batteries
        on it would overload it)."""
        if self._last is None or when - self._last < REACT_INTERVAL:
            return
        flow = self._measurements.flow
        if flow is None or not flow.phase_w:
            return
        phases = len(flow.phase_w)
        with_virtual = list(flow.phase_w)
        for config in self.virtual:
            power = self._batteries.states[config.id].power_w or 0.0
            index = PhaseDevice.from_config(config, phases).phase
            for i in range(phases) if index is None else (index,):
                with_virtual[i] += power / (phases if index is None else 1)
        peak = self._forecast.peak_w
        if (
            overloaded(with_virtual, self._limit_w())
            or overloaded(flow.phase_w, self._limit_w())
            or (peak > 0 and sum(with_virtual) > peak)
        ):
            self.step(when)

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
        wanted = self._phase_relief(wanted, socs, full, now, hours)
        wanted = self._peak_shaving(wanted, socs, full, now, hours)
        wanted = self._phase_limited(wanted, now)
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

    def _phase_relief(
        self,
        wanted: dict[str, float],
        socs: dict[str, float],
        full: dict[str, Any],
        now: datetime,
        hours: float,
    ) -> dict[str, float]:
        """Phase protection: take load off an overloaded phase; explain it."""
        flow = self._measurements.flow
        if flow is None or not flow.phase_w:
            return wanted
        phases = len(flow.phase_w)
        devices = [PhaseDevice.from_config(c, phases) for c in self.virtual]
        result, relieved = relieve(
            wanted,
            devices,
            flow.phase_w,
            self._limit_w(),
            can_discharge=[
                c.id
                for c in self.virtual
                if socs[c.id] > c.min_soc + 0.01 and not full[c.id]
            ],
            can_charge=[c.id for c in self.virtual if socs[c.id] < c.max_soc - 0.01],
        )
        names = {c.id: c.name for c in self.virtual}
        dutch = (self.hass.config.language or "").startswith("nl")
        for index, power in relieved.items():
            event = self.relief.get(index)
            helpers = [
                d.id
                for d in devices
                if d.phase in (index, None) and abs(result[d.id]) > 1
            ]
            if event is None:
                discharging = flow.phase_w[index] > 0
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
                minutes = max(round((event["seen"] - event["start"]).seconds / 60), 1)
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
        flow = self._measurements.flow
        if peak <= 0 or flow is None:
            return wanted
        phases = max(len(flow.phase_w), 1)
        devices = [PhaseDevice.from_config(c, phases) for c in self.virtual]
        result, shaved = shave_peak(
            wanted,
            devices,
            flow.grid_w,
            peak,
            [
                c.id
                for c in self.virtual
                if socs[c.id] > c.min_soc + 0.01 and not full[c.id]
            ],
        )
        dutch = (self.hass.config.language or "").startswith("nl")
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
                minutes=max(round((event["seen"] - event["start"]).seconds / 60), 1),
                energy=f"{event['wh'] / 1000:.2f}".replace(".", "," if dutch else "."),
            )
        return result

    def _phase_limited(
        self, wanted: dict[str, float], now: datetime
    ) -> dict[str, float]:
        """Hold the powers within the phase limits; explain when that starts/ends."""
        flow = self._measurements.flow
        if flow is None or not flow.phase_w:
            return wanted
        phases = len(flow.phase_w)
        max_current = self._measurements.max_current
        devices = [PhaseDevice.from_config(c, phases) for c in self.virtual]
        capped, limited = cap_powers(
            wanted,
            devices,
            flow.phase_w,
            self._limit_w(),
        )
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
        if data is not None and data.plan_mode in ARBITRAGE_MODES and data.battery:
            # Arbitrage: the virtual batteries' share of the planned power.
            slot = next((s for s in data.battery if s.start <= now < s.end), None)
            states = [s for s in self._batteries.states.values() if s.soc is not None]
            capacity = sum(s.config.capacity_kwh for s in states)
            virtual_capacity = sum(
                s.config.capacity_kwh for s in states if s.config.virtual
            )
            total = (
                slot.power_w * virtual_capacity / capacity if slot and capacity else 0.0
            )
        else:
            # NOM: the real surplus (+) / shortage (-) on the grid right now.
            flow = self._measurements.flow
            total = -flow.grid_w if flow is not None else 0.0

        candidates = []
        for config in virtual:
            state = self._batteries.states[config.id]
            candidates.append(
                Candidate(
                    config.id,
                    state.soc if state.soc is not None else config.initial_soc,
                    config.min_soc,
                    config.max_soc,
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
