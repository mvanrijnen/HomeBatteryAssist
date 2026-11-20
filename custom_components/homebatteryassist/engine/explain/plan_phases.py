"""The battery plan as phases: what the batteries do now and next, and why.

Four kinds, each a run of plan slots (per slot several kinds can apply,
e.g. charging partly with solar and partly from the grid):

- ``discharge``: the batteries supply power (house, or also the grid);
- ``charge_grid``: they charge with power from the grid;
- ``charge_pv``: they charge with solar power that would otherwise go to the
  grid;
- ``grid_only``: they are idle and the house runs on the grid.

Per kind the phase running now and the next one: start, end, duration,
energy (kWh), the average price and the reason in plain language; and the
energy per battery (by capacity share: the plan is for all batteries
together, spread over them as the virtual batteries do). Pure: no Home
Assistant state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from ..planning.battery_plan import MODE_NOM, PlanSlot
from .money import format_money

ACTIVE_W = 100.0  # below this a battery counts as idle
KINDS = ("discharge", "charge_grid", "charge_pv", "grid_only")
FIXED_MODES = ("time_slots", "manual")

DAYS = {
    "nl": ("ma", "di", "wo", "do", "vr", "za", "zo"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}
TEXT = {
    "nl": {
        "discharge_nom": "het huis vraagt stroom; nul op de meter",
        "discharge_price": "stroom is dan duur ({price} per kWh)",
        "discharge_export": "teruglevering levert dan veel op ({price} per kWh)",
        "charge_grid": "stroom is dan goedkoop ({price} per kWh), later duurder (tot {later} per kWh)",
        "charge_grid_plain": "stroom is dan goedkoop ({price} per kWh)",
        "charge_grid_needed": "laden uit het net ({price} per kWh) voor volladen of de reserve",
        "charge_pv": "zonnestroom die anders naar het net gaat (levert {price} per kWh op)",
        "grid_only_save": "de batterijen bewaren hun energie voor {when} (stroom dan {price} per kWh)",
        "grid_only_wait": "de batterijen wachten op goedkopere stroom om te laden ({when})",
        "grid_only_empty": "de batterijen zijn zo leeg als ingesteld",
        "grid_only_none": "laden of ontladen loont dan niet",
        "fixed_manual": "zo ingesteld (handmatig)",
        "fixed_slot": "volgens tijdvak {name}",
    },
    "en": {
        "discharge_nom": "the house needs power; zero on the meter",
        "discharge_price": "power is expensive then ({price} per kWh)",
        "discharge_export": "exporting earns a lot then ({price} per kWh)",
        "charge_grid": "power is cheap then ({price} per kWh), more expensive later (up to {later} per kWh)",
        "charge_grid_plain": "power is cheap then ({price} per kWh)",
        "charge_grid_needed": "charging from the grid ({price} per kWh) for a full charge or the reserve",
        "charge_pv": "solar power that would otherwise go to the grid (earns {price} per kWh)",
        "grid_only_save": "the batteries keep their energy for {when} (power then {price} per kWh)",
        "grid_only_wait": "the batteries wait for cheaper power to charge ({when})",
        "grid_only_empty": "the batteries are as empty as allowed",
        "grid_only_none": "charging or discharging does not pay off then",
        "fixed_manual": "set like this (manual)",
        "fixed_slot": "following time slot {name}",
    },
}


@dataclass(frozen=True, slots=True)
class Phase:
    """One run of plan slots of one kind."""

    kind: str
    start: datetime
    end: datetime
    wh: float  # energy of this kind in the phase (all batteries)
    price: float | None  # average price (import; export for charge_pv)
    reason: str
    begin: datetime | None = None  # counted from here (now, for a running phase)

    @property
    def minutes(self) -> int:
        """Minutes from ``begin`` (the start) to the end."""
        begin = self.begin or self.start
        return round((self.end - begin).total_seconds() / 60)


def slot_parts(slot: PlanSlot) -> dict[str, float]:
    """The kinds that apply to a slot, with their power (W)."""
    power = slot.power_w
    without = slot.grid_w - power  # the house's net without the batteries
    surplus = max(-without, 0.0)
    charge = max(power, 0.0)
    from_pv = min(charge, surplus)
    parts: dict[str, float] = {}
    if power < -ACTIVE_W:
        parts["discharge"] = -power
    if from_pv > ACTIVE_W:
        parts["charge_pv"] = from_pv
    if charge - from_pv > ACTIVE_W:
        parts["charge_grid"] = charge - from_pv
    if abs(power) <= ACTIVE_W and slot.grid_w > ACTIVE_W:
        parts["grid_only"] = slot.grid_w
    return parts


def _lang(language: str | None) -> str:
    return "nl" if (language or "").lower().startswith("nl") else "en"


def _money(value: float | None, lang: str, currency: str | None = None) -> str:
    return format_money(value, currency, lang)


def _when(when: datetime, lang: str) -> str:
    local = dt_util.as_local(when)
    return f"{DAYS[lang][local.weekday()]} {local:%H:%M}"


def _runs(slots: Sequence[PlanSlot], kind: str) -> list[list[tuple[PlanSlot, float]]]:
    runs: list[list[tuple[PlanSlot, float]]] = []
    for slot in slots:
        watts = slot_parts(slot).get(kind)
        if watts is None:
            continue
        if runs and runs[-1][-1][0].end == slot.start:
            runs[-1].append((slot, watts))
        else:
            runs.append([(slot, watts)])
    return runs


def _reason(
    kind: str,
    run: list[tuple[PlanSlot, float]],
    slots: Sequence[PlanSlot],
    mode: str,
    floor_soc: float,
    lang: str,
    currency: str | None = None,
) -> str:
    text = TEXT[lang]
    first = run[0][0]
    end = run[-1][0].end
    if mode in FIXED_MODES and kind != "grid_only" and first.reason:
        if first.reason == "manual":
            return text["fixed_manual"]
        return text["fixed_slot"].format(name=first.reason)
    if mode in FIXED_MODES and not first.reason:
        mode = MODE_NOM  # outside its time slots the plan is zero on the meter
    prices = [s.price for s, _ in run if s.price is not None]
    price = sum(prices) / len(prices) if prices else None
    if kind == "discharge":
        if mode == MODE_NOM:
            return text["discharge_nom"]
        if any(s.grid_w < -ACTIVE_W for s, _ in run):
            exports = [s.export_price for s, _ in run if s.export_price is not None]
            value = sum(exports) / len(exports) if exports else price
            return text["discharge_export"].format(price=_money(value, lang, currency))
        return text["discharge_price"].format(price=_money(price, lang, currency))
    if kind == "charge_grid":
        later = [
            s.price
            for s in slots
            if s.start >= end and s.price is not None and s.power_w < -ACTIVE_W
        ]
        if later and price is not None and max(later) > price:
            return text["charge_grid"].format(
                price=_money(price, lang, currency),
                later=_money(max(later), lang, currency),
            )
        if later:
            # Used later at no higher price: not for the price difference.
            return text["charge_grid_needed"].format(
                price=_money(price, lang, currency)
            )
        return text["charge_grid_plain"].format(price=_money(price, lang, currency))
    if kind == "charge_pv":
        exports = [s.export_price for s, _ in run if s.export_price is not None]
        value = sum(exports) / len(exports) if exports else None
        return text["charge_pv"].format(price=_money(value, lang, currency))
    # grid_only: why the batteries do nothing
    if first.soc <= floor_soc + 1:
        following = next(
            (s for s in slots if s.start >= end and s.power_w > ACTIVE_W), None
        )
        if following is not None:
            return text["grid_only_wait"].format(when=_when(following.start, lang))
        return text["grid_only_empty"]
    use = next((s for s in slots if s.start >= end and s.power_w < -ACTIVE_W), None)
    if use is not None and mode != MODE_NOM:
        return text["grid_only_save"].format(
            when=_when(use.start, lang), price=_money(use.price, lang, currency)
        )
    return text["grid_only_none"]


def _phase(
    kind: str,
    run: list[tuple[PlanSlot, float]],
    slots: Sequence[PlanSlot],
    mode: str,
    floor_soc: float,
    lang: str,
    currency: str | None = None,
    now: datetime | None = None,
) -> Phase:
    # A running phase counts from now: the energy and minutes still to come.
    begin = run[0][0].start if now is None else max(run[0][0].start, now)
    wh = sum(
        w * max((s.end - max(s.start, begin)).total_seconds(), 0.0) / 3600
        for s, w in run
    )
    if kind == "charge_pv":
        values = [s.export_price for s, _ in run if s.export_price is not None]
    else:
        values = [s.price for s, _ in run if s.price is not None]
    return Phase(
        kind,
        run[0][0].start,
        run[-1][0].end,
        wh,
        sum(values) / len(values) if values else None,
        _reason(kind, run, slots, mode, floor_soc, lang, currency),
        begin,
    )


def current_and_next(
    slots: Sequence[PlanSlot],
    kind: str,
    now: datetime,
    mode: str,
    floor_soc: float = 0.0,
    language: str | None = None,
    currency: str | None = None,
) -> tuple[Phase | None, Phase | None]:
    """The phase of ``kind`` running now (None) and the next one (None). The
    running phase's kWh and minutes are what is left from ``now``."""
    lang = _lang(language)
    current = following = None
    for run in _runs(slots, kind):
        start, end = run[0][0].start, run[-1][0].end
        if start <= now < end:
            current = _phase(kind, run, slots, mode, floor_soc, lang, currency, now)
        elif start > now and following is None:
            following = _phase(kind, run, slots, mode, floor_soc, lang, currency)
            break
    return current, following


def phase_attributes(
    phase: Phase | None,
    prefix: str,
    shares: Mapping[str, tuple[str, float]],
    share: float = 1.0,
) -> dict[str, Any]:
    """Attributes of one phase (``current_`` / ``next_``); ``shares`` maps
    battery id -> (name, share of the plan); ``share`` scales the energy to
    one battery."""
    if phase is None:
        return {f"{prefix}start": None}
    out: dict[str, Any] = {
        f"{prefix}start": phase.start.isoformat(),
        f"{prefix}end": phase.end.isoformat(),
        f"{prefix}minutes": phase.minutes,
        f"{prefix}kwh": round(phase.wh * share / 1000, 2),
        f"{prefix}price": None if phase.price is None else round(phase.price, 4),
        f"{prefix}reason": phase.reason,
    }
    if shares and share == 1.0 and phase.kind != "grid_only":
        out[f"{prefix}batteries"] = {
            name: round(phase.wh * part / 1000, 2) for name, part in shares.values()
        }
    return out
