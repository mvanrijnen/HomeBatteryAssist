"""The battery plan told as a short story in plain language.

Instead of lists of periods and numbers, a few sentences:

1. what the batteries do now, and why;
2. the next moment they charge: how much, from what source, at what price,
   for which later moment, and what it brings;
3. what the plan is expected to bring compared with no battery.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from ..planning.battery_plan import BatteryPlan, PlanSlot

ACTIVE_W = 100.0  # below this a battery counts as idle
SMALL_GAIN = 0.05  # below this a charge "brings next to nothing"
HOLD = timedelta(hours=6)  # stored this long before use: explain why

DAYS = {
    "nl": ("ma", "di", "wo", "do", "vr", "za", "zo"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}

TEXT = {
    "nl": {
        "now_idle_empty": "Tot {until} doen de batterijen niets en komt de stroom van het net: ze zijn zo leeg als ingesteld, en laden loont nu niet.",
        "now_idle_no_gain": "Tot {until} doen de batterijen niets en komt de stroom van het net: stroom kost nu {price}, en het duurste moment daarna ({later}) is na verlies niet genoeg duurder om nu te laden.",
        "now_idle": "Tot {until} doen de batterijen niets.",
        "now_idle_wait": "Tot {until} doen de batterijen niets en komt de stroom van het net: ze wachten op goedkopere stroom ({price}, {when}).",
        "now_idle_save": "Tot {start} leveren de batterijen niet en komt de stroom van het net, omdat stroom nu niet duur genoeg is ({price}): ze bewaren hun energie voor {use}, als stroom {use_price} kost.",
        "now_idle_save_wait": "Tot {start} leveren de batterijen niet en komt de stroom van het net, omdat stroom nu niet duur genoeg is ({price}): ze bewaren hun energie voor {use}, als stroom {use_price} kost, en laden {when} bij tegen {charge_price}.",
        "now_charge_pv": "Van nu tot {until} laden de batterijen met zonnestroom die anders naar het net zou gaan.",
        "now_charge_grid": "Van nu tot {until} laden de batterijen uit het net, omdat stroom dan goedkoop is ({price}).",
        "now_discharge": "Van nu tot {until} leveren de batterijen stroom aan het huis, omdat stroom dan duur is ({price}).",
        "now_discharge_export": "Van nu tot {until} leveren de batterijen stroom aan het huis en terug aan het net, omdat teruglevering dan veel oplevert ({price}).",
        "now_discharge_nom": "Van nu tot {until} leveren de batterijen stroom aan het huis, zodat er geen stroom van het net nodig is.",
        "next_grid": "{when} laden we {energy} uit het net tegen {price}, om die te gebruiken {use}, als stroom gemiddeld {use_price} kost. Na verlies en slijtage levert laden uit het net in dit plan ongeveer {gain} op.",
        "uses_many": "verspreid over {n} momenten van {first} tot {last}, het meest {main}",
        "hold": "Tot {first} blijft die energie in de batterij en komt de stroom van het net: stroom kost tussendoor hooguit {gap_price}, en is later duurder (tot {max_price}).",
        "full_charge": "Daarmee wordt {names} ook helemaal vol geladen, zoals gepland.",
        "next_grid_small": "{when} laden we {energy} uit het net tegen {price}, om die te gebruiken {use}, als stroom gemiddeld {use_price} kost. Na verlies en slijtage levert dat vrijwel niets op (ongeveer {gain}).",
        "next_pv": "{when} laden we {energy} met zonnestroom, om die te gebruiken {use}.",
        "no_charge": "In de komende {hours} uur is laden niet nodig of levert het niets op.",
        "phase_limited": "Daarbij laden we soms langzamer dan kan, zodat de hoofdzekering ({amps} A per fase) niet overbelast raakt.",
        "vs_none_saves": "Tot {end} scheelt dit plan naar verwachting {diff} ten opzichte van geen batterij.",
        "vs_none_costs": "Tot {end} kost dit plan naar verwachting {diff} meer dan geen batterij.",
        "vs_none_same": "Tot {end} scheelt dit plan naar verwachting niets ten opzichte van geen batterij.",
        "per_kwh": "{amount} per kWh",
        "from": "op",
        "and": "en",
        "tonight": "Vannacht",
        "today": "Vandaag",
        "tomorrow": "Morgen",
        "modes": {
            "nom": "nul op de meter",
            "arbitrage": "arbitrage",
            "arbitrage_full": "arbitrage volledig",
            "time_slots": "tijdvakken",
            "manual": "handmatig",
        },
        "now_fixed_charge": "Van nu tot {until} laden de batterijen: {why}.",
        "now_fixed_discharge": "Van nu tot {until} leveren de batterijen stroom: {why}.",
        "now_fixed_idle": "Tot {until} doen de batterijen niets: {why}.",
        "why_manual": "zo ingesteld (handmatig)",
        "why_slot": "volgens tijdvak {name}",
        "fixed_outside": "Buiten de tijdvakken werken ze als nul op de meter.",
    },
    "en": {
        "now_idle_empty": "Until {until} the batteries are idle and the house runs on the grid: they are as empty as allowed, and charging does not pay off now.",
        "now_idle_no_gain": "Until {until} the batteries are idle and the house runs on the grid: power costs {price} now, and the most expensive moment after that ({later}) is not enough more expensive after losses to charge now.",
        "now_idle": "Until {until} the batteries are idle.",
        "now_idle_wait": "Until {until} the batteries are idle and the house runs on the grid: they wait for cheaper power ({price}, {when}).",
        "now_idle_save": "Until {start} the batteries do not discharge and the house runs on the grid, because power is not expensive enough now ({price}): they keep their energy for {use}, when power costs {use_price}.",
        "now_idle_save_wait": "Until {start} the batteries do not discharge and the house runs on the grid, because power is not expensive enough now ({price}): they keep their energy for {use}, when power costs {use_price}, and charge {when} at {charge_price}.",
        "now_charge_pv": "From now until {until} the batteries charge with solar power that would otherwise go to the grid.",
        "now_charge_grid": "From now until {until} the batteries charge from the grid, because power is cheap then ({price}).",
        "now_discharge": "From now until {until} the batteries supply the house, because power is expensive then ({price}).",
        "now_discharge_export": "From now until {until} the batteries supply the house and the grid, because export pays well then ({price}).",
        "now_discharge_nom": "From now until {until} the batteries supply the house, so no power from the grid is needed.",
        "next_grid": "{when} we charge {energy} from the grid at {price}, to use it {use}, when power costs {use_price} on average. After losses and wear, charging from the grid brings about {gain} in this plan.",
        "uses_many": "spread over {n} moments from {first} to {last}, most {main}",
        "hold": "Until {first} that energy stays in the battery and the house runs on the grid: power costs at most {gap_price} in between, and is more expensive later (up to {max_price}).",
        "full_charge": "This also charges {names} completely, as planned.",
        "next_grid_small": "{when} we charge {energy} from the grid at {price}, to use it {use}, when power costs {use_price} on average. After losses and wear that brings next to nothing (about {gain}).",
        "next_pv": "{when} we charge {energy} with solar power, to use it {use}.",
        "no_charge": "In the next {hours} hours charging is not needed or brings nothing.",
        "phase_limited": "At times we charge slower than possible, so the main fuse ({amps} A per phase) is not overloaded.",
        "vs_none_saves": "Until {end} this plan is expected to save {diff} compared with no battery.",
        "vs_none_costs": "Until {end} this plan is expected to cost {diff} more than no battery.",
        "vs_none_same": "Until {end} this plan is expected to save nothing compared with no battery.",
        "per_kwh": "{amount} per kWh",
        "from": "on",
        "and": "and",
        "tonight": "Tonight",
        "today": "Today",
        "tomorrow": "Tomorrow",
        "modes": {
            "nom": "zero on the meter",
            "arbitrage": "arbitrage",
            "arbitrage_full": "full arbitrage",
            "time_slots": "time slots",
            "manual": "manual",
        },
        "now_fixed_charge": "From now until {until} the batteries charge: {why}.",
        "now_fixed_discharge": "From now until {until} the batteries discharge: {why}.",
        "now_fixed_idle": "Until {until} the batteries are idle: {why}.",
        "why_manual": "as set (manual)",
        "why_slot": "following time slot {name}",
        "fixed_outside": "Outside the time slots they work as zero on the meter.",
    },
}


@dataclass(frozen=True, slots=True)
class _Block:
    start: datetime
    end: datetime
    energy_wh: float
    price: float | None  # energy weighted
    from_grid: bool
    limited: bool = False  # held back by the phase limits


def _lang(language: str | None) -> str:
    return "nl" if (language or "").startswith("nl") else "en"


def _money(value: float, lang: str) -> str:
    text = f"€ {value:.2f}"
    return text.replace(".", ",") if lang == "nl" else text


def _kwh(wh: float, lang: str) -> str:
    text = f"{wh / 1000:.1f} kWh"
    return text.replace(".", ",") if lang == "nl" else text


def _time(when: datetime, lang: str) -> str:
    local = dt_util.as_local(when)
    return f"{DAYS[lang][local.weekday()]} {local:%H:%M}"


def _blocks(slots: list[PlanSlot], charging: bool) -> list[_Block]:
    blocks: list[_Block] = []
    current: list[PlanSlot] = []

    def close() -> None:
        if not current:
            return
        energy = sum(
            abs(s.power_w) * (s.end - s.start).total_seconds() / 3600 for s in current
        )
        priced = [s for s in current if s.price is not None]
        weight = sum(abs(s.power_w) for s in priced)
        price = (
            sum(s.price * abs(s.power_w) for s in priced) / weight if weight else None
        )
        if charging:
            # Mostly from the grid: at least half of the charged energy came
            # from the grid (the grid import up to the charge power per slot);
            # a solar charge with a little grid import stays a solar charge.
            from_grid_wh = sum(
                min(s.power_w, max(s.grid_w, 0.0))
                * (s.end - s.start).total_seconds()
                / 3600
                for s in current
            )
            from_grid = from_grid_wh >= energy / 2
        else:
            from_grid = any(s.grid_w > ACTIVE_W for s in current)
        limited = any(s.limited for s in current)
        blocks.append(
            _Block(current[0].start, current[-1].end, energy, price, from_grid, limited)
        )
        current.clear()

    for slot in slots:
        active = slot.power_w > ACTIVE_W if charging else slot.power_w < -ACTIVE_W
        if active and (not current or current[-1].end == slot.start):
            current.append(slot)
        else:
            close()
            if active:
                current.append(slot)
    close()
    return blocks


def _merge(charges: list[_Block], discharges: list[_Block]) -> list[_Block]:
    """Join charge blocks that have no discharging in between (one charge moment)."""
    merged: list[_Block] = []
    for block in charges:
        if (
            merged
            and merged[-1].from_grid == block.from_grid  # same source only
            and not any(merged[-1].end <= d.start < block.start for d in discharges)
        ):
            last = merged.pop()
            energy = last.energy_wh + block.energy_wh
            prices = [
                (b.price, b.energy_wh) for b in (last, block) if b.price is not None
            ]
            weight = sum(e for _, e in prices)
            price = sum(p * e for p, e in prices) / weight if weight else None
            block = _Block(
                last.start,
                block.end,
                energy,
                price,
                last.from_grid or block.from_grid,
                last.limited or block.limited,
            )
        merged.append(block)
    return merged


def _when(block: _Block, now: datetime, lang: str) -> str:
    t = TEXT[lang]
    start, end = dt_util.as_local(block.start), dt_util.as_local(block.end)
    today = dt_util.as_local(now).date()
    span = f"{_time(block.start, lang)}-{end:%H:%M}"
    if (start.date() == today and start.hour >= 18) or (
        (start.date() - today).days == 1 and start.hour < 7
    ):
        return f"{t['tonight']} ({span})"
    if start.date() == today:
        return f"{t['today']} ({span})"
    if (start.date() - today).days == 1:
        return f"{t['tomorrow']} ({span})"
    return f"{t['from'].capitalize()} {span}"


def _run_end(slots: list[PlanSlot], current: PlanSlot, lang: str, now: datetime) -> str:
    """Local end time of the run of slots doing the same as ``current``."""

    def kind(slot: PlanSlot) -> tuple[int, bool, str | None]:
        sign = 1 if slot.power_w > ACTIVE_W else -1 if slot.power_w < -ACTIVE_W else 0
        return sign, sign > 0 and slot.grid_w > ACTIVE_W, slot.reason

    end = current.end
    for slot in slots:
        if slot.start < current.end:
            continue
        if slot.start != end or kind(slot) != kind(current):
            break
        end = slot.end
    return _at(end, lang, now)


def _at(when: datetime, lang: str, now: datetime) -> str:
    """``HH:MM`` today, else with the weekday."""
    local = dt_util.as_local(when)
    if local.date() == dt_util.as_local(now).date():
        return f"{local:%H:%M}"
    return _time(when, lang)


def plan_story(
    plan: BatteryPlan,
    others: dict[str, BatteryPlan],
    now: datetime,
    language: str | None,
    efficiency: float,
    cycle_cost: float,
    min_soc_reached: bool,
    max_current: int | None = None,
    full_charges: Sequence[tuple[datetime, datetime, str]] = (),
) -> str:
    """A few plain sentences about what the plan does and why."""
    lang = _lang(language)
    t = TEXT[lang]
    slots = plan.slots
    if not slots:
        return ""
    sentences: list[str] = []

    discharges = _blocks(slots, False)
    charges = _merge([b for b in _blocks(slots, True) if b.end > now], discharges)

    # 1. Now.
    current = next((s for s in slots if s.start <= now < s.end), slots[0])
    price_now = current.price

    until = _run_end(slots, current, lang, now)

    def per_kwh(value: float) -> str:
        return t["per_kwh"].format(amount=_money(value, lang))

    if current.reason is not None:
        # Manual / time slot: the action is fixed, its reason is the setting.
        why = (
            t["why_manual"]
            if current.reason == "manual"
            else t["why_slot"].format(name=current.reason)
        )
        key = (
            "now_fixed_charge"
            if current.power_w > ACTIVE_W
            else "now_fixed_discharge"
            if current.power_w < -ACTIVE_W
            else "now_fixed_idle"
        )
        sentences.append(t[key].format(until=until, why=why))
        if plan.strategy == "time_slots":
            sentences.append(t["fixed_outside"])
    elif current.power_w > ACTIVE_W:
        key = "now_charge_grid" if current.grid_w > ACTIVE_W else "now_charge_pv"
        sentences.append(t[key].format(until=until, price=per_kwh(price_now or 0)))
    elif current.power_w < -ACTIVE_W:
        if plan.strategy == "nom" or price_now is None:
            sentences.append(t["now_discharge_nom"].format(until=until))
        elif current.grid_w < -ACTIVE_W:
            sentences.append(
                t["now_discharge_export"].format(
                    until=until,
                    price=per_kwh(current.export_price or price_now),
                )
            )
        else:
            sentences.append(
                t["now_discharge"].format(until=until, price=per_kwh(price_now))
            )
    elif (
        not min_soc_reached
        and price_now is not None
        and (saving := next((d for d in discharges if d.start > now), None))
        and saving.price is not None
        and saving.price > price_now
    ):
        # Not discharging now: the energy is worth more later.
        use = f"{_time(saving.start, lang)}-{dt_util.as_local(saving.end):%H:%M}"
        charge = next(
            (
                c
                for c in charges
                if c.start < saving.start
                and c.from_grid
                and c.price is not None
                and c.price < price_now
            ),
            None,
        )
        if charge is not None:
            sentences.append(
                t["now_idle_save_wait"].format(
                    start=_at(saving.start, lang, now),
                    price=per_kwh(price_now),
                    use=use,
                    use_price=per_kwh(saving.price),
                    when=_when(charge, now, lang).split(" (")[0].lower(),
                    charge_price=per_kwh(charge.price),
                )
            )
        else:
            sentences.append(
                t["now_idle_save"].format(
                    start=_at(saving.start, lang, now),
                    price=per_kwh(price_now),
                    use=use,
                    use_price=per_kwh(saving.price),
                )
            )
    elif (
        price_now is not None
        and charges
        and charges[0].price is not None
        and charges[0].from_grid
        and charges[0].price < price_now
    ):
        sentences.append(
            t["now_idle_wait"].format(
                until=until,
                price=per_kwh(charges[0].price),
                when=_when(charges[0], now, lang).split(" (")[0].lower(),
            )
        )
    elif min_soc_reached:
        sentences.append(t["now_idle_empty"].format(until=until))
    elif price_now is not None:
        later = max(
            (s.price for s in slots if s.start > now and s.price is not None),
            default=None,
        )
        # Wear is paid on the kWh charged and on the kWh discharged.
        if (
            later is not None
            and later * efficiency - cycle_cost * (1 + efficiency) <= price_now
        ):
            sentences.append(
                t["now_idle_no_gain"].format(
                    until=until, price=per_kwh(price_now), later=per_kwh(later)
                )
            )
        else:
            sentences.append(t["now_idle"].format(until=until))
    else:
        sentences.append(t["now_idle"].format(until=until))

    # 2. The next charge and what it is for.
    if charges:
        # Tell the next charge from the grid if there is one (the decision
        # worth explaining), else the next charge with solar power.
        block = next((c for c in charges if c.from_grid), charges[0])
        # The energy is used until the next charge from the grid (charging
        # with solar power in between does not replace it).
        until = next(
            (c.start for c in charges if c.from_grid and c.start > block.start),
            slots[-1].end,
        )
        uses = [d for d in discharges if block.end <= d.start < until]

        def span(d: _Block) -> str:
            return f"{_time(d.start, lang)}-{dt_util.as_local(d.end):%H:%M}"

        if len(uses) > 2:
            main = max(uses, key=lambda d: d.energy_wh)
            use_text = t["uses_many"].format(
                n=len(uses),
                first=_time(uses[0].start, lang),
                last=_time(uses[-1].end, lang),
                main=f"{t['from']} {span(main)}",
            )
        else:
            use_text = f" {t['and']} ".join(span(d) for d in uses)
            use_text = f"{t['from']} {use_text}" if use_text else ""
        if block.from_grid and block.price is not None and uses:
            weight = sum(d.energy_wh for d in uses if d.price is not None)
            use_price = (
                sum(d.price * d.energy_wh for d in uses if d.price is not None) / weight
                if weight
                else None
            )
            if use_price is not None:
                # What is really used of it (kWh delivered), what that took
                # from the grid, and the wear on both.
                used = (
                    min(sum(d.energy_wh for d in uses), block.energy_wh * efficiency)
                    / 1000
                )
                charged = used / efficiency if efficiency else used
                gain = (
                    used * use_price
                    - charged * block.price
                    - cycle_cost * (charged + used)
                )
                # The planner's own figure where it can be had: what this plan
                # brings more than zero on the meter (which never charges from
                # the grid), so the story matches the plan.
                nom = others.get("nom")
                if (
                    nom is not None
                    and nom.saving is not None
                    and plan.saving is not None
                    and plan.strategy != "nom"
                ):
                    gain = plan.saving - nom.saving
                key = "next_grid" if gain >= SMALL_GAIN else "next_grid_small"
                sentences.append(
                    t[key].format(
                        when=_when(block, now, lang),
                        energy=_kwh(block.energy_wh, lang),
                        price=per_kwh(block.price),
                        use=use_text,
                        use_price=per_kwh(use_price),
                        gain=_money(max(gain, 0.0), lang),
                    )
                )
        elif uses or not block.from_grid:
            sentences.append(
                t["next_pv"]
                .format(
                    when=_when(block, now, lang),
                    energy=_kwh(block.energy_wh, lang),
                    use=use_text or "later",
                )
                .replace(" ,", ",")
            )
        names = sorted(
            {
                name
                for start, end, name in full_charges
                if start < block.end and end > block.start
            }
        )
        if names:
            sentences.append(t["full_charge"].format(names=f" {t['and']} ".join(names)))
        if uses and uses[0].start - block.end >= HOLD:
            # Why the energy is not used earlier: the moments in between are cheaper.
            gap = [
                s.price
                for s in slots
                if block.end <= s.start < uses[0].start and s.price is not None
            ]
            top = max((d.price for d in uses if d.price is not None), default=None)
            if gap and top is not None and max(gap) < top:
                sentences.append(
                    t["hold"].format(
                        first=_time(uses[0].start, lang),
                        gap_price=per_kwh(max(gap)),
                        max_price=per_kwh(top),
                    )
                )
        if block.limited and max_current:
            sentences.append(t["phase_limited"].format(amps=max_current))
    else:
        hours = round((slots[-1].end - now).total_seconds() / 3600)
        sentences.append(t["no_charge"].format(hours=hours))

    # 3. Compared with no battery over the whole plan.
    if plan.saving is not None:
        end_text = _at(slots[-1].end, lang, now)
        if abs(plan.saving) < 0.05:
            sentences.append(t["vs_none_same"].format(end=end_text))
        elif plan.saving > 0:
            sentences.append(
                t["vs_none_saves"].format(end=end_text, diff=_money(plan.saving, lang))
            )
        else:
            sentences.append(
                t["vs_none_costs"].format(end=end_text, diff=_money(-plan.saving, lang))
            )
    return " ".join(sentences)
