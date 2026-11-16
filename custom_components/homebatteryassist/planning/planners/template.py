"""Template for an own planner — a code example only, never registered here.

Copy this file to ``/config/homebatteryassist/planners/`` (create the folder),
rename the class, set ``key`` and ``name``, and reload HomeBatteryAssist
(Settings → Devices & services → HomeBatteryAssist → ⋮ → Reload). The planner
then appears in the settings as a choice for the plan mode.

In ``/config`` use absolute imports, as below. ``plan`` gets the forecast per
slot and returns the requested battery power per slot (W, + charging,
- discharging). HomeBatteryAssist checks it afterwards: power, phase limits,
minimum/maximum state of charge and price rules are enforced, and periodic
full charges are inserted after that. Plans are advice only; no battery is
controlled.

This example: charge from the grid in the cheapest quarter of the slots,
discharge for the house in the most expensive quarter, otherwise zero on the
meter (PV surplus is stored, shortage covered).
"""

from __future__ import annotations

from custom_components.homebatteryassist.planning.planners.base import (
    Planner,
    PlannerInput,
    PlannerResult,
)


class CheapestHoursPlanner(Planner):
    """Charge in the cheapest slots, discharge in the most expensive ones."""

    key = "cheapest_hours"  # becomes "custom_cheapest_hours"
    name = "Cheapest hours"
    description = "Charge in the cheapest quarter, use in the most expensive quarter."

    def plan(self, data: PlannerInput) -> PlannerResult:
        slots = data.slots
        if not data.priced:
            # Without prices: zero on the meter.
            return PlannerResult([-s.net_w for s in slots])
        prices = sorted(s.price for s in slots)
        cheap = prices[len(prices) // 4]
        dear = prices[-(len(prices) // 4) - 1]
        powers = []
        for slot in slots:
            if slot.price <= cheap:
                powers.append(slot.max_charge_w)  # HomeBatteryAssist stops at full
            elif slot.price >= dear:
                powers.append(-max(slot.net_w, 0.0))  # only what the house needs
            else:
                powers.append(-slot.net_w)  # zero on the meter
        return PlannerResult(powers, strategy=self.key)
