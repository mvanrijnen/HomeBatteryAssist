"""Notifications: important decisions sent to notify services (optional).

The user chooses which kinds of decisions to be told about and through which
notify services (e.g. the companion app) and/or a persistent notification in
Home Assistant. Every decision that falls in a chosen kind is sent with its
plain-language explanation.
"""

from __future__ import annotations

import logging

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback

from .decision_log import Decision

_LOGGER = logging.getLogger(__name__)

PERSISTENT = "persistent_notification"

# kind of notification -> decision keys (or key prefixes ending with "*")
KINDS: dict[str, tuple[str, ...]] = {
    "plan": ("battery_plan_story", "plan_mode_set"),
    "prices": ("prices_updated", "horizon_*"),
    "protection": (
        "phase_relief",
        "phase_relief_ended",
        "peak_shaving",
        "peak_shaving_ended",
        "phase_limit",
        "phase_limit_cleared",
        "interceptor_changed",
        "interceptor_cleared",
        "interceptor_failed",
    ),
    "full_charge": ("full_charge_planned", "full_charge_overdue"),
    "measurement": (
        "consumption_unavailable",
        "consumption_restored",
        "meter_lost_hold",
        "meter_back_resume",
    ),
    "solar": (
        "pv_surplus_unexpected",
        "pv_surplus_unexpected_ended",
        "pv_shortage_unexpected",
        "pv_shortage_unexpected_ended",
    ),
}


def kind_of(key: str) -> str | None:
    """The notification kind of a decision key."""
    for kind, keys in KINDS.items():
        for pattern in keys:
            if key == pattern or (
                pattern.endswith("*") and key.startswith(pattern[:-1])
            ):
                return kind
    return None


class Notifier:
    """Sends chosen decisions to notify services."""

    def __init__(
        self, hass: HomeAssistant, targets: list[str], kinds: list[str]
    ) -> None:
        """``targets``: notify service names (``notify.<name>``) or PERSISTENT."""
        self.hass = hass
        self.targets = targets
        self.kinds = set(kinds)

    @callback
    def async_decision(self, decision: Decision) -> None:
        """Send a decision when its kind is chosen."""
        if not self.targets or kind_of(decision["key"]) not in self.kinds:
            return
        title = "HomeBatteryAssist"
        for target in self.targets:
            if target == PERSISTENT:
                persistent_notification.async_create(
                    self.hass,
                    decision["message"],
                    title,
                    f"homebatteryassist_{decision['category']}",
                )
                continue
            if not self.hass.services.has_service("notify", target):
                _LOGGER.debug("Notify service %s not found", target)
                continue
            self.hass.async_create_task(
                self.hass.services.async_call(
                    "notify",
                    target,
                    {"title": title, "message": decision["message"]},
                    blocking=False,
                )
            )
