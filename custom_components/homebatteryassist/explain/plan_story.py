"""The battery plan told as a short story in plain language.

Instead of lists of periods and numbers, a few sentences:

1. what the batteries do now, and why;
2. the next moment they charge: how much, from what source, at what price,
   for which later moment, and what it brings;
3. how the selected mode compares with the other one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.util import dt as dt_util

from ..planning.battery_plan import BatteryPlan, PlanSlot

ACTIVE_W = 100.0  # below this a battery counts as idle

DAYS = {
    "nl": ("ma", "di", "wo", "do", "vr", "za", "zo"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}

TEXT = {
    "nl": {
        "now_idle_empty": "De batterijen doen nu niets: ze zijn zo leeg als ingesteld, en laden loont nu niet.",
        "now_idle_no_gain": "De batterijen doen nu niets: stroom kost nu {price}, en het duurste moment daarna ({later}) is na verlies niet genoeg duurder om nu te laden.",
        "now_idle": "De batterijen doen nu niets.",
        "now_idle_wait": "De batterijen doen nu niets: ze wachten op goedkopere stroom ({price}, {when}).",
        "now_idle_save": "De batterijen leveren nu niet, omdat stroom nu niet duur genoeg is ({price}): ze bewaren hun energie voor {use}, als stroom {use_price} kost.",
        "now_idle_save_wait": "De batterijen leveren nu niet, omdat stroom nu niet duur genoeg is ({price}): ze bewaren hun energie voor {use}, als stroom {use_price} kost, en laden {when} bij tegen {charge_price}.",
        "now_charge_pv": "De batterijen laden nu {power} met zonnestroom die anders naar het net zou gaan.",
        "now_charge_grid": "De batterijen laden nu {power} uit het net, omdat stroom nu goedkoop is ({price}).",
        "now_discharge": "De batterijen leveren nu {power} aan het huis, omdat stroom nu duur is ({price}).",
        "now_discharge_export": "De batterijen ontladen nu {power}, waarvan {export} terug aan het net, omdat teruglevering nu veel oplevert ({price}).",
        "now_discharge_nom": "De batterijen leveren nu {power} aan het huis, zodat er geen stroom van het net nodig is.",
        "next_grid": "{when} laden we {energy} uit het net tegen {price}, om die te gebruiken {use} als stroom {use_price} kost. Na verlies levert dat ongeveer {gain} op.",
        "next_pv": "{when} laden we {energy} met zonnestroom, om die te gebruiken {use}.",
        "no_charge": "In de komende {hours} uur is laden niet nodig of levert het niets op.",
        "phase_limited": "Daarbij laden we soms langzamer dan kan, zodat de hoofdzekering ({amps} A per fase) niet overbelast raakt.",
        "compare_better": "Met {other} zou het {diff} minder opleveren.",
        "compare_worse": "Let op: met {other} zou het {diff} meer opleveren.",
        "compare_same": "Met {other} zou het ongeveer hetzelfde opleveren.",
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
        },
    },
    "en": {
        "now_idle_empty": "The batteries are idle: they are as empty as allowed, and charging does not pay off now.",
        "now_idle_no_gain": "The batteries are idle: power costs {price} now, and the most expensive moment after that ({later}) is not enough more expensive after losses to charge now.",
        "now_idle": "The batteries are idle.",
        "now_idle_wait": "The batteries are idle: they wait for cheaper power ({price}, {when}).",
        "now_idle_save": "The batteries do not discharge now, because power is not expensive enough now ({price}): they keep their energy for {use}, when power costs {use_price}.",
        "now_idle_save_wait": "The batteries do not discharge now, because power is not expensive enough now ({price}): they keep their energy for {use}, when power costs {use_price}, and charge {when} at {charge_price}.",
        "now_charge_pv": "The batteries are charging {power} with solar power that would otherwise go to the grid.",
        "now_charge_grid": "The batteries are charging {power} from the grid, because power is cheap now ({price}).",
        "now_discharge": "The batteries supply {power} to the house, because power is expensive now ({price}).",
        "now_discharge_export": "The batteries discharge {power}, of which {export} goes to the grid, because export pays well now ({price}).",
        "now_discharge_nom": "The batteries supply {power} to the house, so no power from the grid is needed.",
        "next_grid": "{when} we charge {energy} from the grid at {price}, to use it {use} when power costs {use_price}. After losses that brings about {gain}.",
        "next_pv": "{when} we charge {energy} with solar power, to use it {use}.",
        "no_charge": "In the next {hours} hours charging is not needed or brings nothing.",
        "phase_limited": "At times we charge slower than possible, so the main fuse ({amps} A per phase) is not overloaded.",
        "compare_better": "With {other} it would bring {diff} less.",
        "compare_worse": "Note: with {other} it would bring {diff} more.",
        "compare_same": "With {other} it would bring about the same.",
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
        },
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


def _power(w: float) -> str:
    return f"{abs(w):.0f} W" if abs(w) < 1000 else f"{abs(w) / 1000:.1f} kW"


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
        if merged and not any(
            merged[-1].end <= d.start < block.start for d in discharges
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


def plan_story(
    plan: BatteryPlan,
    others: dict[str, BatteryPlan],
    now: datetime,
    language: str | None,
    efficiency: float,
    cycle_cost: float,
    min_soc_reached: bool,
    max_current: int | None = None,
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

    def per_kwh(value: float) -> str:
        return t["per_kwh"].format(amount=_money(value, lang))

    if current.power_w > ACTIVE_W:
        key = "now_charge_grid" if current.grid_w > ACTIVE_W else "now_charge_pv"
        sentences.append(
            t[key].format(power=_power(current.power_w), price=per_kwh(price_now or 0))
        )
    elif current.power_w < -ACTIVE_W:
        if plan.strategy == "nom" or price_now is None:
            sentences.append(
                t["now_discharge_nom"].format(power=_power(current.power_w))
            )
        elif current.grid_w < -ACTIVE_W:
            sentences.append(
                t["now_discharge_export"].format(
                    power=_power(current.power_w),
                    export=_power(current.grid_w),
                    price=per_kwh(current.export_price or price_now),
                )
            )
        else:
            sentences.append(
                t["now_discharge"].format(
                    power=_power(current.power_w), price=per_kwh(price_now)
                )
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
                    price=per_kwh(price_now), use=use, use_price=per_kwh(saving.price)
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
                price=per_kwh(charges[0].price),
                when=_when(charges[0], now, lang).split(" (")[0].lower(),
            )
        )
    elif min_soc_reached:
        sentences.append(t["now_idle_empty"])
    elif price_now is not None:
        later = max(
            (s.price for s in slots if s.start > now and s.price is not None),
            default=None,
        )
        if later is not None and later * efficiency - cycle_cost <= price_now:
            sentences.append(
                t["now_idle_no_gain"].format(
                    price=per_kwh(price_now), later=per_kwh(later)
                )
            )
        else:
            sentences.append(t["now_idle"])
    else:
        sentences.append(t["now_idle"])

    # 2. The next charge and what it is for.
    if charges:
        block = charges[0]
        until = charges[1].start if len(charges) > 1 else slots[-1].end
        uses = [d for d in discharges if block.end <= d.start < until]
        use_text = f" {t['and']} ".join(
            f"{_time(d.start, lang)}-{dt_util.as_local(d.end):%H:%M}" for d in uses[:2]
        )
        use_text = f"{t['from']} {use_text}" if use_text else ""
        if block.from_grid and block.price is not None and uses:
            weight = sum(d.energy_wh for d in uses if d.price is not None)
            use_price = (
                sum(d.price * d.energy_wh for d in uses if d.price is not None) / weight
                if weight
                else None
            )
            if use_price is not None:
                gain = (
                    block.energy_wh
                    / 1000
                    * (use_price * efficiency - block.price - cycle_cost)
                )
                sentences.append(
                    t["next_grid"].format(
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
        if block.limited and max_current:
            sentences.append(t["phase_limited"].format(amps=max_current))
    else:
        hours = round((slots[-1].end - now).total_seconds() / 3600)
        sentences.append(t["no_charge"].format(hours=hours))

    # 3. Compared with the other mode(s).
    for mode, other in others.items():
        if other.saving is None or plan.saving is None:
            continue
        diff = plan.saving - other.saving
        name = t["modes"].get(mode, mode)
        if abs(diff) < 0.05:
            sentences.append(t["compare_same"].format(other=name))
        elif diff > 0:
            sentences.append(
                t["compare_better"].format(other=name, diff=_money(diff, lang))
            )
        else:
            sentences.append(
                t["compare_worse"].format(other=name, diff=_money(-diff, lang))
            )
    return " ".join(sentences)
