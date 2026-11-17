"""Battery control loop — WRITTEN OUT, COMMENTED OUT (not active).

Everything below the docstring is comment on purpose: HomeBatteryAssist does
not control batteries yet. The code is complete so that switching control on
later is uncommenting it, plus the steps under *Activating* — not designing
it then. ``tests/test_read_only.py`` checks that this file stays without
active code.

What it does, once active
=========================

Every round (setting ``react_interval_s``, default 5 s; on the average of
the meter over the round when ``react_average`` is on) and at once when the
grid meter shows a phase overload, a peak or (``react_jump``) a jump of at
least ``react_jump_w``, the loop decides a power per real battery and hands it to that
battery's ``BatteryController`` (``battery_controller.py``), which applies the
safety rules (master switch, always release, watchdog, refresh, throttle,
deadband, idle = release, limits) and talks to the battery.

The power per battery comes from the same steps the virtual batteries
(``engine/devices/batteries/virtual.py``) already run every second, so what
the dashboard simulates is what would be sent:

1. **Full charge** due for a battery (``ForecastData.full_charge_now``):
   charge at its max power up to 100 %.
2. **Target total**: the selected plan's power for the current slot
   (arbitrage, time slots, manual, own planners), with an unexpected solar
   surplus stored on top (``plan_balance``), or, for zero on the meter,
   ``nom_balance`` — surplus charged; a shortage discharged, but never for
   excluded devices nor for a random short peak (spike filter, when on).
   Price rules: no discharging below the minimum discharge price.
3. **Spread** over the batteries (``Distributor``: few batteries at low power,
   more when more power is needed; per-battery min/max power, hysteresis).
4. **Phase protection** (relieve an overloaded phase, never push a phase over
   its limit — ``phase_limit.py``) and **peak shaving** (``peak.py``).
5. **Interceptor** (``interceptors/``, the user's module, default none):
   per battery approve, limit (less, same direction), hold back (0 W) or
   release (back to its own control); what is held back may be taken over
   by the approved batteries. ``run_interceptor`` holds it to that. Where
   phase relief or peak shaving set the power, that power stands: the
   interceptor cannot undo protection.
6. **HomeBatteryAssist's own final check**, which always wins: phase limits
   (``_phase_limited``), power limits and the state of charge: never below
   max(min SoC, reserve SoC), never above max SoC (100 % during a full
   charge).

   The load per phase is the current as precise as known
   (``PowerFlow.phase_load_w``: measured current; else power / (measured
   voltage x power factor); else power / 230 V). **Real batteries are in
   the measurement**: the meter already sees their current power on their
   phase, so the load without them = measured load - their power now (per
   phase; a battery without a phase spread evenly) before ``relieve`` /
   ``cap_powers`` (the virtual batteries are not in the measurement, so
   they use it as it is). **Grid unknown** (meter gone for 10 s, a grid
   sensor unknown): no control; every battery is released to its own
   control until the grid is measured again (``meter_lost_hold``).
7. Per battery ``controller.async_command(power)`` (a released battery:
   ``controller.async_command(None)``, which releases it); the controller
   decides whether and when it is really sent.

How a battery is reached (``ReaderDriver`` below):

- through the integration it is linked with — the reader's
  ``async_set_power`` / ``async_release`` (e.g. Omnibattery: manual mode +
  charge/discharge power entities; Marstek Modbus: RS485 control mode +
  force charge/discharge). Only when that integration's own control is off,
  otherwise the two fight;
- or a **direct driver** (``engine/devices/batteries/direct/``) once it is
  enabled — the only way for batteries without an integration that can
  control them.

Activating (later, deliberately, with the project owner)
==========================================================

1. Refactor the steps 2 to 4 out of ``VirtualBatteries`` into
   ``engine/control/targets.py`` (``battery_targets(configs, ...)`` with the
   reason per battery, ``intercept_input`` from ``_intercept`` and
   ``load_without`` = the measured phase load minus the real batteries'
   power now), used by
   the virtual batteries and this loop alike (now they work on
   ``self.virtual``; they must take the list of batteries).
2. Uncomment this file and the wiring in ``__init__.py`` (search for
   "control_loop").
3. Add the setting ``control_enabled`` (default off, a clear warning text,
   per battery ``control`` on/off in the battery subentry) and pass it as
   ``enabled``; add the decision log messages (``control_started``,
   ``control_stopped``, ``control_failed``, ``control_released``) in all
   languages.
4. Adapt ``tests/test_read_only.py`` (this file then may contain code) and
   test the write methods of the reader on a real installation first
   (``verified`` per reader / driver).
"""

# The code (commented out; see "Activating" above).
#
# from __future__ import annotations
#
# import logging
# from dataclasses import replace
# from datetime import datetime, timedelta
# from typing import Any
#
# from homeassistant.config_entries import ConfigEntry
# from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
# from homeassistant.helpers.event import async_track_time_interval
# from homeassistant.util import dt as dt_util
#
# from ..devices.batteries import reader_for
# from ..devices.batteries.base import BatteryReader
# from ..devices.batteries.direct.base import DirectBatteryDriver, DirectReading
# from ..explain import DecisionLog
# from ..measure.battery_monitor import BatteryConfig, BatteryInput
# from ..measure.house_measurement import MeasurementInput
# from .battery_controller import BatteryController
# from .interceptors import run_interceptor
# from .targets import (  # step 1 of "Activating"
#     battery_targets,
#     intercept_input,
#     protection_needed,
# )
#
# _LOGGER = logging.getLogger(__name__)
#
# STEP = timedelta(seconds=5)  # fallback; the round is forecast.react_interval
# REACT_INTERVAL = timedelta(seconds=0.5)  # fastest extra round on the meter
#
#
# class ReaderDriver(DirectBatteryDriver):
#     """A battery controlled through the integration it is linked with, in
#     the shape of a driver (what ``BatteryController`` needs)."""
#
#     transport = "integration"
#     can_write = True
#     # Integrations write through entities: not more often than this, and
#     # only for a real change (each write is a state change in HA).
#     min_interval_s = 5.0
#     deadband_w = 50.0
#
#     def __init__(
#         self, hass: HomeAssistant, reader: BatteryReader, config: BatteryConfig
#     ) -> None:
#         super().__init__(hass, config.power_sensor)
#         self.reader = reader
#         self.config = config
#         self.name = config.name
#         self.max_charge_w = config.max_charge_w
#         self.max_discharge_w = config.max_discharge_w
#         self.enabled = True  # the controller's master switch decides
#
#     async def async_read(self) -> DirectReading:
#         return DirectReading()  # reading stays with BatteryInput
#
#     async def async_set_power(self, power_w: float) -> None:
#         await self.reader.async_set_power(self.hass, self.config, power_w)
#
#     async def async_release(self) -> None:
#         await self.reader.async_release(self.hass, self.config)
#
#
# class ControlLoop:
#     """Turns the plan (or zero on the meter) into commands per real battery."""
#
#     def __init__(
#         self,
#         hass: HomeAssistant,
#         entry: ConfigEntry,
#         decisions: DecisionLog,
#         batteries: BatteryInput,
#         measurements: MeasurementInput,
#         forecast: Any,  # ForecastCoordinator (no import cycle)
#         enabled: bool,
#     ) -> None:
#         self.hass = hass
#         self._decisions = decisions
#         self._batteries = batteries
#         self._measurements = measurements
#         self._forecast = forecast
#         self.enabled = enabled
#         self.controllers: dict[str, BatteryController] = {}
#         for config in batteries.configs:
#             if config.virtual or not config.control:  # step 3: per battery
#                 continue
#             reader = reader_for(hass, config)
#             if reader is None or not reader.can_write:
#                 continue  # no way to reach this battery
#             self.controllers[config.id] = BatteryController(
#                 ReaderDriver(hass, reader, config),
#                 enabled=enabled,
#                 limits=(config.max_charge_w, config.max_discharge_w),
#             )
#         self._last: datetime | None = None
#         self._unsub: list[CALLBACK_TYPE] = []
#
#     @property
#     def configs(self) -> list[BatteryConfig]:
#         return [c for c in self._batteries.configs if c.id in self.controllers]
#
#     @callback
#     def async_start(self) -> None:
#         if not self.controllers:
#             return
#         self._last = dt_util.utcnow()
#         self._unsub.append(
#             async_track_time_interval(
#                 self.hass, self._async_step, self._forecast.react_interval or STEP
#             )
#         )
#         self._unsub.append(self._measurements.async_add_listener(self._measured))
#         self._decisions.async_log(
#             "battery",
#             "control_started",
#             names=", ".join(c.name for c in self.configs),
#         )
#
#     async def async_stop(self) -> None:
#         """Stop and hand every battery back to its own control."""
#         for unsub in self._unsub:
#             unsub()
#         self._unsub.clear()
#         for controller in self.controllers.values():
#             await controller.async_stop()  # always releases
#         if self.controllers:
#             self._decisions.async_log("battery", "control_stopped")
#
#     @callback
#     def _measured(self, when: datetime, _power: float | None) -> None:
#         """React at once on a phase overload, a peak or a large jump (as
#         the virtual batteries do: the average over the round and the jump
#         check move to targets.py with step 1), not only every round."""
#         if self._last is not None and when - self._last >= REACT_INTERVAL:
#             # The check of VirtualBatteries._async_measured, moved to
#             # targets.py in step 1 of "Activating".
#             if protection_needed(self._measurements, self._forecast, self.configs):
#                 self.hass.async_create_task(self._async_run(when))
#
#     async def _async_step(self, now: datetime) -> None:
#         await self._async_run(now)
#
#     async def _async_run(self, now: datetime) -> None:
#         last, self._last = self._last, now
#         if last is None:
#             return
#         data = self._forecast.data
#         configs = self.configs
#         full = {
#             c.id: data.full_charge_now(c.id, now) if data else None for c in configs
#         }
#         socs = {
#             c.id: self._batteries.states[c.id].soc for c in configs
#         }
#         if self._measurements.flow is None:
#             # Grid unknown: the phase load is unknown; hand back control.
#             for controller in self.controllers.values():
#                 await controller.async_command(None, now)
#             return
#         # Steps 2-4: the same as the virtual batteries, on the load without
#         # the real batteries (targets.load_without(flow, configs, states)).
#         wanted, reasons = battery_targets(
#             [c for c in configs if not full[c.id]],
#             socs,
#             now,
#             forecast=self._forecast,
#             measurements=self._measurements,
#             batteries=self._batteries,
#         )
#         # Step 5: the interceptor (the same input as for the virtual
#         # batteries, built by targets.intercept_input), then step 6.
#         outcome = run_interceptor(
#             self._forecast.interceptor,
#             intercept_input(configs, socs, full, wanted, reasons, now, ...),
#         )
#         wanted, released = outcome.powers, outcome.released
#         for config in configs:
#             soc = socs[config.id]
#             controller = self.controllers[config.id]
#             if soc is None:
#                 # Unknown state of charge: never act blind.
#                 await controller.async_command(None, now)
#                 continue
#             if full[config.id]:
#                 power = config.max_charge_w if soc < 100.0 else 0.0
#             else:
#                 power = _within_soc(
#                     config, soc, wanted.get(config.id, 0.0), self._forecast
#                 )
#             if config.id in released:  # the interceptor released it
#                 await controller.async_command(None, now)
#                 continue
#             await controller.async_command(power, now)
#             await controller.async_tick(now)
#             if controller.errors:
#                 self._decisions.async_log(
#                     "battery", "control_failed", name=config.name
#                 )
#
#
# def _within_soc(
#     config: BatteryConfig, soc: float, power_w: float, forecast: Any
# ) -> float:
#     """No discharging at or below the floor, no charging at or above max."""
#     floor = max(config.min_soc, forecast.rules.reserve_soc)
#     if power_w < 0 and soc <= floor:
#         return 0.0
#     if power_w > 0 and soc >= config.max_soc:
#         return 0.0
#     return power_w
