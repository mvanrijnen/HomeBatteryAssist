"""Built-in planners: zero on the meter, manual and time slots.

- ``nom`` (nul op de meter / zero on the meter): charge with PV surplus,
  discharge on shortage, never from or to the grid on purpose.
- ``manual``: always a fixed power (``planning.schedule``).
- ``time_slots``: the actions of the configured time slots, zero on the meter
  outside them.

To make your own variant: copy this file to
``/config/homebatteryassist/planners/``, give the class another ``key`` and
``name``, and change the relative imports (``from .base import``) into
``from custom_components.homebatteryassist.engine.modules.planners.base import``.
"""

from __future__ import annotations

from .base import Planner, PlannerInput, PlannerResult, may_discharge


def follow(data: PlannerInput, fixed_actions: bool) -> PlannerResult:
    """Zero on the meter; with ``fixed_actions`` the target's fixed action
    (manual / time slot) where it gives one."""
    battery = data.battery
    rules = data.rules
    eff = battery.efficiency
    stored = battery.stored_wh
    powers: list[float] = []
    reasons: list[str | None] = []
    # Charge hysteresis: once full, charge again only after dropping this much.
    hysteresis = rules.charge_hysteresis * battery.capacity_wh / 100
    full = hysteresis > 0 and stored >= battery.ceiling_wh - 1
    for slot in data.slots:
        hours = slot.hours
        power = 0.0
        fixed = data.target(slot.start) if fixed_actions and data.target else None
        if full and stored < battery.ceiling_wh - hysteresis:
            full = False
        net = slot.net_w - rules.nom_target_w
        if fixed is not None:
            if fixed.power_w > 0:
                top = battery.ceiling_wh
                if fixed.soc_limit is not None:
                    top = min(top, fixed.soc_limit * battery.capacity_wh / 100)
                room = max(top - stored, 0.0)
                power = min(fixed.power_w, slot.max_charge_w, room / (hours * eff))
            elif fixed.power_w < 0:
                bottom = battery.floor_wh
                if fixed.soc_limit is not None:
                    bottom = max(bottom, fixed.soc_limit * battery.capacity_wh / 100)
                available = max(stored - bottom, 0.0)
                power = -min(
                    -fixed.power_w, slot.max_discharge_w, available * eff / hours
                )
        elif net < 0 and not full:
            room = max(battery.ceiling_wh - stored, 0.0)
            power = min(-net, slot.max_charge_w, room / (hours * eff))
        elif net > 0 and may_discharge(rules, slot.price):
            available = max(stored - battery.floor_wh, 0.0)
            power = -min(net, slot.max_discharge_w, available * eff / hours)
        stored += power * hours * eff if power >= 0 else power * hours / eff
        if hysteresis > 0 and stored >= battery.ceiling_wh - 1:
            full = True
        powers.append(power)
        reasons.append(fixed.reason if fixed is not None else None)
    return PlannerResult(powers, reasons)


class NomPlanner(Planner):
    """Zero on the meter."""

    key = "nom"
    name = "Zero on the meter"

    def plan(self, data: PlannerInput) -> PlannerResult:
        result = follow(data, False)
        result.strategy = self.key
        return result


class ManualPlanner(Planner):
    """A fixed power, as set."""

    key = "manual"
    name = "Manual"

    def plan(self, data: PlannerInput) -> PlannerResult:
        result = follow(data, True)
        result.strategy = self.key
        return result


class TimeSlotsPlanner(Planner):
    """The configured time slots; zero on the meter outside them."""

    key = "time_slots"
    name = "Time slots"

    def plan(self, data: PlannerInput) -> PlannerResult:
        result = follow(data, True)
        result.strategy = self.key
        return result
