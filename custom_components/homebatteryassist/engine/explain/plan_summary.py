"""The plan at a glance: a few lines that say what the batteries do and why.

- ``now``: what the batteries do now, until when and why, with the price
  thresholds of the plan (using the batteries pays above, charging from the
  grid below; planners that know them, e.g. arbitrage);
- ``power``: batteries the plans give less power for their temperature
  (warm now; cold once that is learned);
- ``next``: the next change (another kind of phase);
- ``plan``: the charge and discharge periods in one line and the expected
  saving compared with no battery;
- ``sun``: the expected solar production and the surplus for the batteries,
  today and tomorrow;
- ``cheapest``: the cheapest published price from now and how far the
  published prices reach.

Pure: no Home Assistant state (the coordinator passes what it needs).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from ..planning.battery_plan import BatteryPlan, PlanSlot
from .money import format_money
from .plan_phases import DAYS, Phase, current_and_next, reason_now, slot_parts

MAX_SPANS = 3  # periods per kind in the plan line
STATE_MAX = 255  # Home Assistant's limit for a state

TEXT = {
    "nl": {
        "labels": {
            "now": "Nu",
            "power": "Vermogen",
            "next": "Straks",
            "plan": "Plan",
            "sun": "Zon",
            "cheapest": "Goedkoopst",
        },
        "kind": {
            "discharge": "Leveren",
            "charge_grid": "Laden uit het net",
            "charge_pv": "Laden met zonnestroom",
            "grid_only": "Wachten",
        },
        "now": "{kind} tot {until}: {reason}.",
        "sun_covers": "De batterijen doen niets: de zon dekt het huis.",
        "no_plan": "Nog geen plan.",
        "price_now": "Stroom kost nu {price} per kWh.",
        "idle_both": "Gebruiken van de batterijen loont pas boven {use} per kWh, laden uit het net onder {charge} (na verlies, slijtage en marge).",
        "idle_use": "Gebruiken van de batterijen loont pas boven {use} per kWh (na verlies, slijtage en marge).",
        "idle_charge": "Laden uit het net loont pas onder {charge} per kWh (na verlies, slijtage en marge).",
        "charging": "Dit laden loont zolang stroom minder kost dan {charge} per kWh (na verlies, slijtage en marge).",
        "using": "Leveren loont zolang stroom meer kost dan {use} per kWh (na verlies, slijtage en marge).",
        "short": "{kind} tot {until}.",
        "short_price": "Stroom nu {price}.",
        "short_both": "Gebruiken loont boven {use}, laden uit het net onder {charge}.",
        "short_use": "Gebruiken loont boven {use}.",
        "short_charge": "Laden uit het net loont onder {charge}.",
        "short_charging": "Dit laden loont tot {charge}.",
        "short_using": "Leveren loont vanaf {use}.",
        "power_warm": "{name} is warm ({temperature}): laden met hooguit {charge} W in plaats van {max_charge} W.",
        "power_limited": "{name} laadt nu met hooguit {charge} W in plaats van {max_charge} W (beperkt door de batterij zelf).",
        "power_warm_both": "{name} is warm ({temperature}): laden met hooguit {charge} W in plaats van {max_charge} W, ontladen met hooguit {discharge} W in plaats van {max_discharge} W.",
        "next": "{when}: {kind} tot {end} ({energy}): {reason}.",
        "plan_part": {
            "charge_grid": "laden uit het net {spans}",
            "charge_pv": "laden met zon {spans}",
            "discharge": "leveren {spans}",
        },
        "more": "(+{n})",
        "nothing": "Geen laden of leveren gepland",
        "saves": "verwachte winst tot {end}: {amount} tegenover geen batterij",
        "costs": "verwacht tot {end}: {amount} duurder dan geen batterij",
        "sun": "verwacht vandaag nog {today}, morgen {tomorrow}; overschot voor de batterijen vandaag {surplus_today}, morgen {surplus_tomorrow}.",
        "cheapest": "{span}: {price} per kWh · prijzen bekend tot {until}.",
        "cheapest_open": "{span}: {price} per kWh.",
    },
    "en": {
        "labels": {
            "now": "Now",
            "power": "Power",
            "next": "Next",
            "plan": "Plan",
            "sun": "Sun",
            "cheapest": "Cheapest",
        },
        "kind": {
            "discharge": "Supplying",
            "charge_grid": "Charging from the grid",
            "charge_pv": "Charging with solar power",
            "grid_only": "Waiting",
        },
        "now": "{kind} until {until}: {reason}.",
        "sun_covers": "The batteries are idle: the sun covers the house.",
        "no_plan": "No plan yet.",
        "price_now": "Power costs {price} per kWh now.",
        "idle_both": "Using the batteries only pays above {use} per kWh, charging from the grid below {charge} (after losses, wear and margin).",
        "idle_use": "Using the batteries only pays above {use} per kWh (after losses, wear and margin).",
        "idle_charge": "Charging from the grid only pays below {charge} per kWh (after losses, wear and margin).",
        "charging": "This charge pays as long as power costs less than {charge} per kWh (after losses, wear and margin).",
        "using": "Supplying pays as long as power costs more than {use} per kWh (after losses, wear and margin).",
        "short": "{kind} until {until}.",
        "short_price": "Power now {price}.",
        "short_both": "Using pays above {use}, charging from the grid below {charge}.",
        "short_use": "Using pays above {use}.",
        "short_charge": "Charging from the grid pays below {charge}.",
        "short_charging": "This charge pays up to {charge}.",
        "short_using": "Supplying pays from {use}.",
        "power_warm": "{name} is warm ({temperature}): charging at {charge} W at most instead of {max_charge} W.",
        "power_limited": "{name} charges at {charge} W at most now instead of {max_charge} W (limited by the battery itself).",
        "power_warm_both": "{name} is warm ({temperature}): charging at {charge} W at most instead of {max_charge} W, discharging at {discharge} W at most instead of {max_discharge} W.",
        "next": "{when}: {kind} until {end} ({energy}): {reason}.",
        "plan_part": {
            "charge_grid": "charge from the grid {spans}",
            "charge_pv": "charge with solar {spans}",
            "discharge": "supply {spans}",
        },
        "more": "(+{n})",
        "nothing": "No charging or supplying planned",
        "saves": "expected saving until {end}: {amount} compared with no battery",
        "costs": "expected until {end}: {amount} more than no battery",
        "sun": "expected {today} more today, {tomorrow} tomorrow; surplus for the batteries {surplus_today} today, {surplus_tomorrow} tomorrow.",
        "cheapest": "{span}: {price} per kWh · prices known until {until}.",
        "cheapest_open": "{span}: {price} per kWh.",
    },
}

ORDER = ("now", "power", "next", "plan", "sun", "cheapest")


def _power_line(limits: Sequence[Mapping[str, Any]], lang: str) -> str | None:
    """The batteries planned with less power for their temperature, or for
    the charge power they limited themselves to lately."""
    text = TEXT[lang]
    parts = []
    for info in limits:
        if info.get("reason") == "limited":
            parts.append(
                text["power_limited"].format(
                    name=info["name"],
                    charge=info["charge_w"],
                    max_charge=info["max_charge_w"],
                )
            )
            continue
        both = info["discharge_w"] < info["max_discharge_w"]
        temperature = f"{info['temperature_c']:.1f} °C"
        if lang == "nl":
            temperature = temperature.replace(".", ",")
        parts.append(
            text["power_warm_both" if both else "power_warm"].format(
                name=info["name"],
                temperature=temperature,
                charge=info["charge_w"],
                max_charge=info["max_charge_w"],
                discharge=info["discharge_w"],
                max_discharge=info["max_discharge_w"],
            )
        )
    return " ".join(parts) or None


def _lang(language: str | None) -> str:
    return "nl" if (language or "").lower().startswith("nl") else "en"


def _price(value: float | None, lang: str, currency: str | None) -> str:
    return format_money(value, currency, lang, 3)


def _kwh(wh: float, lang: str) -> str:
    text = f"{wh / 1000:.1f} kWh"
    return text.replace(".", ",") if lang == "nl" else text


def _at(when: datetime, lang: str, now: datetime) -> str:
    """``HH:MM`` today, else with the weekday."""
    local = dt_util.as_local(when)
    if local.date() == dt_util.as_local(now).date():
        return f"{local:%H:%M}"
    return f"{DAYS[lang][local.weekday()]} {local:%H:%M}"


def _span(start: datetime, end: datetime, lang: str, now: datetime) -> str:
    return f"{_at(start, lang, now)}-{dt_util.as_local(end):%H:%M}"


def _now_line(
    slots: Sequence[PlanSlot],
    now: datetime,
    mode: str,
    floor_soc: float,
    lang: str,
    currency: str | None,
) -> tuple[str, str, Phase | None]:
    """The ``now`` line, its short form (the sensor state: what the
    batteries do, the price now and the thresholds) and the phase now."""
    text = TEXT[lang]
    slot = next((s for s in slots if s.start <= now < s.end), None)
    if slot is None:
        return text["no_plan"], text["no_plan"], None
    phase = reason_now(slots, now, mode, floor_soc, lang, currency)
    if phase is None:
        line = short = text["sun_covers"]
    else:
        until = _at(phase.end, lang, now)
        line = text["now"].format(
            kind=text["kind"][phase.kind], until=until, reason=phase.reason
        )
        short = text["short"].format(kind=text["kind"][phase.kind], until=until)
    kind = phase.kind if phase else None
    use = slot.use_above
    charge = slot.charge_below
    money = {
        "use": _price(use, lang, currency),
        "charge": _price(charge, lang, currency),
    }
    which = None
    if kind == "charge_grid" and charge is not None:
        which = ("charging", "short_charging")
    elif kind == "discharge" and use is not None:
        which = ("using", "short_using")
    elif kind in ("grid_only", None):
        if use is not None and charge is not None:
            which = ("idle_both", "short_both")
        elif use is not None:
            which = ("idle_use", "short_use")
        elif charge is not None:
            which = ("idle_charge", "short_charge")
    if which is None:
        return line, short, phase
    if slot.price is not None:
        price = _price(slot.price, lang, currency)
        line += " " + text["price_now"].format(price=price)
        short += " " + text["short_price"].format(price=price)
    line += " " + text[which[0]].format(**money)
    short += " " + text[which[1]].format(**money)
    return line, short, phase


def _next_line(
    slots: Sequence[PlanSlot],
    now: datetime,
    current: Phase | None,
    mode: str,
    floor_soc: float,
    lang: str,
    currency: str | None,
) -> str | None:
    """The next phase of another kind than now (after the running one)."""
    text = TEXT[lang]
    after = current.end if current else now
    kind_now = current.kind if current else None
    candidates = []
    for kind in ("discharge", "charge_grid", "charge_pv", "grid_only"):
        if kind == kind_now:
            continue
        running, following = current_and_next(
            slots, kind, now, mode, floor_soc, lang, currency
        )
        for phase in (running, following):
            if phase is not None and phase.start >= after:
                candidates.append(phase)
                break
    if not candidates:
        return None
    phase = min(candidates, key=lambda p: (p.start, p.kind != "discharge"))
    return text["next"].format(
        when=_at(phase.start, lang, now),
        kind=text["kind"][phase.kind].lower(),
        end=_at(phase.end, lang, now),
        energy=_kwh(phase.wh, lang),
        reason=phase.reason,
    )


def _runs(
    slots: Sequence[PlanSlot], kind: str, now: datetime
) -> list[tuple[datetime, datetime]]:
    runs: list[tuple[datetime, datetime]] = []
    for slot in slots:
        if slot.end <= now or kind not in slot_parts(slot):
            continue
        if runs and runs[-1][1] == slot.start:
            runs[-1] = (runs[-1][0], slot.end)
        else:
            runs.append((slot.start, slot.end))
    return runs


def _plan_line(
    plan: BatteryPlan | None,
    slots: Sequence[PlanSlot],
    now: datetime,
    lang: str,
    currency: str | None,
) -> str:
    text = TEXT[lang]
    parts = []
    for kind in ("charge_grid", "charge_pv", "discharge"):
        runs = _runs(slots, kind, now)
        if not runs:
            continue
        spans = " · ".join(
            _span(max(a, now), b, lang, now) for a, b in runs[:MAX_SPANS]
        )
        if len(runs) > MAX_SPANS:
            spans += " " + text["more"].format(n=len(runs) - MAX_SPANS)
        parts.append(text["plan_part"][kind].format(spans=spans))
    line = "; ".join(parts) if parts else text["nothing"]
    line = line[:1].upper() + line[1:]
    saving = plan.saving if plan is not None else None
    if saving is not None and slots:
        end = _at(slots[-1].end, lang, now)
        key = "saves" if saving >= 0 else "costs"
        line += (
            ". "
            + text[key][:1].upper()
            + text[key][1:].format(
                end=end, amount=format_money(abs(saving), currency, lang)
            )
        )
    return line + "."


def _sun_line(
    slots: Sequence[PlanSlot],
    pv_wh: Mapping[datetime, float],
    now: datetime,
    lang: str,
) -> str | None:
    if not pv_wh:
        return None
    today = dt_util.as_local(now).date()
    tomorrow = today + timedelta(days=1)
    produced = {today: 0.0, tomorrow: 0.0}
    for start, wh in pv_wh.items():
        end = start + timedelta(hours=1)
        if end <= now:
            continue
        day = dt_util.as_local(start).date()
        if day in produced:
            part = (end - max(start, now)).total_seconds() / 3600
            produced[day] += max(wh, 0.0) * part
    surplus = {today: 0.0, tomorrow: 0.0}
    for slot in slots:
        if slot.end <= now:
            continue
        day = dt_util.as_local(slot.start).date()
        if day in surplus:
            without = slot.grid_w - slot.power_w  # the house without batteries
            hours = (slot.end - max(slot.start, now)).total_seconds() / 3600
            surplus[day] += max(-without, 0.0) * hours
    return TEXT[lang]["sun"].format(
        today=_kwh(produced[today], lang),
        tomorrow=_kwh(produced[tomorrow], lang),
        surplus_today=_kwh(surplus[today], lang),
        surplus_tomorrow=_kwh(surplus[tomorrow], lang),
    )


def _cheapest_line(
    slots: Sequence[PlanSlot],
    now: datetime,
    published_until: datetime | None,
    lang: str,
    currency: str | None,
) -> str | None:
    """The cheapest published price from now on (its run of slots)."""
    known = [
        s
        for s in slots
        if s.end > now
        and s.price is not None
        and (published_until is None or s.end <= published_until)
    ]
    if not known:
        return None
    best = min(s.price for s in known)
    first = next(s for s in known if s.price is not None and s.price <= best + 1e-9)
    end = first.end
    for slot in known:
        if slot.start == end and slot.price is not None and slot.price <= best + 1e-9:
            end = slot.end
    span = _span(max(first.start, now), end, lang, now)
    price = _price(best, lang, currency)
    if published_until is None:
        return TEXT[lang]["cheapest_open"].format(span=span, price=price)
    return TEXT[lang]["cheapest"].format(
        span=span, price=price, until=_at(published_until, lang, now)
    )


def plan_summary(
    plan: BatteryPlan | None,
    slots: Sequence[PlanSlot],
    now: datetime,
    mode: str,
    floor_soc: float = 0.0,
    language: str | None = None,
    currency: str | None = None,
    pv_wh: Mapping[datetime, float] | None = None,
    published_until: datetime | None = None,
    power_limits: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """The lines of the summary (``now``, ``power``, ``next``, ``plan``,
    ``sun``, ``cheapest``; None when there is nothing to say), ``lines``
    (label and text, in order, for the dashboard) and the thresholds of now.
    ``power_limits``: per battery planned with less power for its
    temperature its name, temperature and powers (``ForecastCoordinator``)."""
    lang = _lang(language)
    now_text, short, current = _now_line(slots, now, mode, floor_soc, lang, currency)
    slot = next((s for s in slots if s.start <= now < s.end), None)
    out: dict[str, Any] = {
        "now": now_text,
        "power": _power_line(power_limits, lang),
        "next": (
            _next_line(slots, now, current, mode, floor_soc, lang, currency)
            if slots
            else None
        ),
        "plan": _plan_line(plan, slots, now, lang, currency) if slots else None,
        "sun": _sun_line(slots, pv_wh or {}, now, lang),
        "cheapest": _cheapest_line(slots, now, published_until, lang, currency),
    }
    labels = TEXT[lang]["labels"]
    out["lines"] = [
        {"key": key, "label": labels[key], "text": out[key]}
        for key in ORDER
        if out[key]
    ]
    out["state"] = short
    out["use_above"] = slot.use_above if slot else None
    out["charge_below"] = slot.charge_below if slot else None
    return out


def state_text(summary: Mapping[str, Any]) -> str:
    """The short form of ``now`` as a state (at most 255 characters)."""
    text = str(summary.get("state") or summary.get("now") or "")
    if len(text) <= STATE_MAX:
        return text
    return text[: STATE_MAX - 1].rstrip() + "…"
