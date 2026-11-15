"""Live simulation of virtual batteries (what-if).

Every ``STEP`` the simulator lets each virtual battery act according to the
selected plan mode, using the real measurements:

- ``nom``: absorb the real surplus / cover the real shortage measured on the
  grid right now (after the real batteries);
- ``arbitrage``: follow the battery plan of the current slot, for the virtual
  batteries' share of the planned capacity.

The total is spread over the virtual batteries with
``planning.distribution.distribute`` (minimum power per battery).

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
from datetime import datetime, timedelta

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from ..explain import DecisionLog
from ..forecasts.coordinator import ForecastCoordinator
from ..inputs.batteries import BatteryConfig, BatteryInput
from ..inputs.measurements import MeasurementInput
from ..planning.battery_plan import MODE_ARBITRAGE
from ..planning.distribution import Candidate, Distributor

_LOGGER = logging.getLogger(__name__)

STEP = timedelta(seconds=30)
MAX_STEP = timedelta(minutes=5)  # longer gaps (restart) are not simulated


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

    @callback
    def async_stop(self) -> None:
        """Stop simulating."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @callback
    def _async_step(self, now: datetime) -> None:
        self.step(now)

    def step(self, now: datetime) -> None:
        """Let every virtual battery act for the time since the previous step."""
        last, self._last = self._last, now
        if last is None:
            return
        elapsed = min(now - last, MAX_STEP)
        hours = elapsed.total_seconds() / 3600
        if hours <= 0:
            return
        targets = self._targets(now, hours)
        for config in self.virtual:
            state = self._batteries.states[config.id]
            soc = state.soc if state.soc is not None else config.initial_soc
            power, soc = limit_power(
                config, soc, targets(config, soc), hours, random_efficiency(config)
            )
            self._batteries.set_virtual(config.id, now, power, soc)

    def _targets(self, now: datetime, hours: float):
        """A function (config, soc) -> target power (W, + charging) per battery.

        The total for the virtual batteries is spread with ``distribute``:
        few batteries at low power, more when more power is needed.
        """
        virtual = self.virtual
        data = self._forecast.data
        if data is not None and data.plan_mode == MODE_ARBITRAGE and data.battery:
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
