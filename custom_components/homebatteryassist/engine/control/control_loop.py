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
   (arbitrage, time slots, manual, own planners), with the real solar
   surplus instead of the forecast one (``plan_balance``; a planned
   discharge only as far as needed now, ``planned_discharge``, threshold
   ``ForecastCoordinator.pv_deviation_w``): an unexpected surplus stored on
   top, a planned charge from the sun that is not there not taken from the
   grid; or, for zero on the meter,
   ``nom_balance`` — surplus charged; a shortage discharged, but never for
   excluded devices nor for a random short peak (spike filter, when on).
   Price rules: no discharging below the minimum discharge price. Lowest
   state of charge for this target: max(min SoC, reserve SoC, night reserve
   while ``ForecastData.night_at(now)``, peak reserve when a peak limit is
   set); below the peak reserve only peak shaving (step 4) discharges, for
   the import above the peak limit. Arbitrage plans already charge from the
   grid for the night reserve before sunrise.
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
   **Never one battery charging while another discharges**
   (``battery_distribution.one_direction``): protection first, then a full
   charge sets the direction and the batteries against it stop; otherwise
   the net stands (the grid sees the same, without the losses of moving
   energy from one battery into the other).
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

**Does the battery follow?** ``CommandMonitor``
(``engine/evaluation/command_check.py``, already active) reads every real
battery's command back from its integration's entities and compares it with
its power. Today that checks the battery's own integration; once this loop
writes the command, it checks HomeBatteryAssist's own commands the same way.
A battery that does not follow without an explanation (``problem``: not
full/empty, not switched off, no hysteresis) is released to its own control
(``control_released``) instead of being commanded on; it is commanded again
once the check is clear.

How a battery is reached (``ReaderDriver``, ``reader_driver.py``):

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
   The export limit (``export_limiter.py``, ``CONTROL``) would then send
   ``ExportLimiter.targets()`` through the PV inverter drivers
   (``devices/inverters``): the export limit to a driver that limits the
   export (Home Manager), the production limit (PV + grid + limit, split by
   breaker) to one that limits its own output; renew before the device's
   fallback (Home Manager 60 min, SunSpec ``WMaxLimPct_RvrtTms``), read
   PMAX / WMax first to turn W into %.
   A real battery with a twin (a virtual battery ``twin_of`` it) is not
   planned and never controlled (it keeps its own control, to compare);
   ``_flow`` of the virtual batteries takes it off the grid, so the twin
   acts in its place.
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
# from ..explain import DecisionLog
# from ..measure.battery_monitor import BatteryConfig, BatteryInput
# from ..measure.house_measurement import MeasurementInput
# from .battery_controller import BatteryController
# from .interceptors import run_interceptor
# from .reader_driver import ReaderDriver  # active code, shared with control_test
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
#         commands: Any = None,  # CommandMonitor: does a battery follow?
#     ) -> None:
#         self.hass = hass
#         self._commands = commands
#         self._decisions = decisions
#         self._batteries = batteries
#         self._measurements = measurements
#         self._forecast = forecast
#         self.enabled = enabled
#         self.controllers: dict[str, BatteryController] = {}
#         for config in batteries.configs:
#             if config.virtual or not config.control:  # step 3: per battery
#                 continue
#             if config.id in twinned_ids(batteries.configs):
#                 continue  # its twin is planned in its place: it keeps its own control
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
#         # Never one battery charging while another discharges.
#         wanted = one_direction(
#             wanted,
#             [i for i, r in reasons.items() if r in ("phase_relief", "peak_shaving")],
#             [i for i in configs_ids if full[i]],
#         )
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
#             check = self._commands.checks.get(config.id) if self._commands else None
#             if check is not None and check.problem:
#                 # It does not follow (and nothing explains it): back to its
#                 # own control rather than commanding on.
#                 if controller.state.active:
#                     self._decisions.async_log(
#                         "battery", "control_released", name=config.name
#                     )
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
#     """No discharging at or below the floor, no charging at or above max.
#     A last safety check: the night and peak reserves are already in the
#     virtual batteries' targets (``_reserve_floor``) and the interceptor's
#     redistribution respects them (``BatteryProposal.floor_soc``)."""
#     floor = max(config.min_soc, forecast.rules.reserve_soc)
#     if power_w < 0 and soc <= floor:
#         return 0.0
#     if power_w > 0 and soc >= config.max_soc:
#         return 0.0
#     return power_w
