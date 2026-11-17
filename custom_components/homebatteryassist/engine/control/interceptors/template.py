"""Template for an own interceptor — an example, never registered.

Copy it to ``/config/homebatteryassist/interceptors/<name>.py``, change the
relative import into an absolute one (``from custom_components.
homebatteryassist.engine.control.interceptors.base import ...``), give
``key`` and ``name`` a value and write your rules. Reload HomeBatteryAssist;
choose it in the settings (section *Planning*).

HomeBatteryAssist's own final check comes after yours and always wins: you
can hold back or limit, never ask more than proposed.
"""

from __future__ import annotations

from .base import LIMIT, REJECT, Decision, InterceptInput, Interceptor, InterceptResult

COLD_C = 5.0  # no discharging below this battery temperature
SAUNA_W = 3000.0  # excluded devices above this: no grid charging


class TemplateInterceptor(Interceptor):
    """Example rules: protect cold batteries, no grid charging while a big
    excluded device runs, never discharge more than 1500 W per battery."""

    key = "template"
    name = "Template (example rules)"

    def intercept(self, data: InterceptInput) -> InterceptResult:
        """Decide per battery."""
        decisions = []
        for battery in data.batteries:
            proposed = battery.proposed_w
            if (
                proposed < 0
                and battery.temperature_c is not None
                and battery.temperature_c < COLD_C
            ):
                decisions.append(Decision(battery.id, REJECT, reason="too cold"))
            elif (
                proposed > 0
                and (data.excluded_w or 0.0) > SAUNA_W
                and (data.pv_w or 0.0) < proposed
            ):
                decisions.append(
                    Decision(
                        battery.id, REJECT, reason="big device on, no grid charging"
                    )
                )
            elif proposed < -1500:
                decisions.append(Decision(battery.id, LIMIT, -1500, "at most 1500 W"))
        # What a cold battery does not supply, the others may take over.
        return InterceptResult(decisions, redistribute=True)
