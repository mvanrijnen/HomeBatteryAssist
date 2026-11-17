"""Interceptor modules: the user's last say before commands go to batteries.

Every control step HomeBatteryAssist's proposal per battery goes through the
chosen interceptor (``base.py``), which may approve, limit, reject or release
per battery. ``run_interceptor`` then holds it to its rules — never more
than proposed, never the other direction, unknown or nonsense counts as
approved — and, when the interceptor allows it, lets the approved batteries
take over what the others do not do. HomeBatteryAssist's own final check
(power and phase limits, state of charge) comes after this and always wins.

Built-in: ``none`` (``pass_through.py``, default). Own interceptors are
Python files in ``/config/homebatteryassist/interceptors/`` (see
``template.py``), keyed ``custom_<key>``. Used by the virtual batteries now,
and by the control loop once that is switched on.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

from homeassistant.core import HomeAssistant

from ...own_modules import async_load_modules, load_modules_from
from .base import (
    APPROVE,
    LIMIT,
    REJECT,
    RELEASE,
    BatteryProposal,
    Decision,
    InterceptInput,
    Interceptor,
    InterceptResult,
    PriceSlot,
)
from .pass_through import PassThrough

_LOGGER = logging.getLogger(__name__)

KIND = "interceptors"
DEFAULT_INTERCEPTOR = PassThrough.key
BUILTIN: dict[str, type[Interceptor]] = {PassThrough.key: PassThrough}

__all__ = [
    "APPROVE",
    "BUILTIN",
    "DEFAULT_INTERCEPTOR",
    "LIMIT",
    "REJECT",
    "RELEASE",
    "BatteryProposal",
    "Decision",
    "InterceptInput",
    "InterceptResult",
    "Interceptor",
    "Outcome",
    "PriceSlot",
    "async_load_user_interceptors",
    "create_interceptor",
    "load_interceptors_from",
    "run_interceptor",
]


def _usable(found: dict[str, Interceptor]) -> dict[str, Interceptor]:
    return {
        k: s for k, s in found.items() if type(s).intercept is not Interceptor.intercept
    }


def load_interceptors_from(folder: Path) -> dict[str, Interceptor]:
    """Interceptors defined in the Python files of ``folder`` (blocking)."""
    return _usable(load_modules_from(folder, Interceptor, KIND))


async def async_load_user_interceptors(hass: HomeAssistant) -> dict[str, Interceptor]:
    """The user's own interceptors (``/config/homebatteryassist/interceptors``)."""
    return _usable(await async_load_modules(hass, KIND, Interceptor))


def create_interceptor(key: str | None, own: dict[str, Interceptor]) -> Interceptor:
    """The chosen interceptor (an own one, else built-in, else none)."""
    key = key or DEFAULT_INTERCEPTOR
    if key in own:
        return own[key]
    return BUILTIN.get(key, PassThrough)()


@dataclass
class Outcome:
    """What the interceptor decided, after HomeBatteryAssist's rules."""

    powers: dict[str, float]  # per battery, + charge / - discharge
    released: set[str] = field(default_factory=set)  # back to own control
    # (battery id, action, power W, reason) for every battery not approved
    changes: list[tuple[str, str, float, str]] = field(default_factory=list)
    failed: bool = False


def _limited(proposed: float, value: object) -> float:
    """At most ``proposed``, in the same direction (0 for nonsense)."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    if proposed > 0:
        return min(max(number, 0.0), proposed)
    if proposed < 0:
        return max(min(number, 0.0), proposed)
    return 0.0


def run_interceptor(interceptor: Interceptor, data: InterceptInput) -> Outcome:
    """Run the interceptor and hold it to the rules (see the module text)."""
    proposals = {b.id: b for b in data.batteries}
    powers = {b.id: b.proposed_w for b in data.batteries}
    outcome = Outcome(dict(powers))
    try:
        result = interceptor.intercept(data)
    except Exception:  # an own module may fail in any way
        _LOGGER.exception("Interceptor %s failed", interceptor.key)
        outcome.failed = True
        return outcome
    if not isinstance(result, InterceptResult):
        return outcome
    decided: set[str] = set()
    for decision in result.decisions or ():
        if not isinstance(decision, Decision) or decision.battery_id not in proposals:
            continue
        if decision.battery_id in decided:
            continue  # the first decision per battery counts
        decided.add(decision.battery_id)
        proposed = powers[decision.battery_id]
        if decision.action == REJECT:
            value = 0.0
        elif decision.action == RELEASE:
            value = 0.0
            outcome.released.add(decision.battery_id)
        elif decision.action == LIMIT:
            value = _limited(proposed, decision.power_w)
        else:
            continue  # approve, or unknown: as proposed
        if decision.action == LIMIT and abs(value - proposed) < 1:
            continue
        outcome.powers[decision.battery_id] = value
        outcome.changes.append(
            (
                decision.battery_id,
                decision.action,
                value,
                str(decision.reason or "")[:100],
            )
        )
    if result.redistribute and outcome.changes:
        _redistribute(outcome, proposals, powers)
    return outcome


def _redistribute(
    outcome: Outcome, proposals: dict[str, BatteryProposal], proposed: dict[str, float]
) -> None:
    """Let the approved batteries take over what the others no longer do, per
    direction, up to their limits, in proportion to the room they have."""
    changed = {battery_id for battery_id, *_ in outcome.changes}
    for sign in (1.0, -1.0):
        missing = sum(
            sign * (proposed[i] - outcome.powers[i])
            for i in changed
            if sign * proposed[i] > 0
        )
        if missing <= 1:
            continue
        room = {
            i: (p.max_charge_w if sign > 0 else p.max_discharge_w)
            - sign * outcome.powers[i]
            for i, p in proposals.items()
            if i not in changed and not p.full_charge and sign * proposed[i] >= 0
        }
        room = {i: r for i, r in room.items() if r > 1}
        total = sum(room.values())
        if total <= 0:
            continue
        share = min(missing / total, 1.0)
        for i, r in room.items():
            outcome.powers[i] += sign * r * share
