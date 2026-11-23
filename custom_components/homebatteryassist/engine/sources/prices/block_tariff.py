"""Price driver: a block tariff — fixed prices per time block, no price sensor.

For a contract with fixed prices in time blocks (day/night, peak hours, a
supplier's cheap moments at fixed hours) instead of dynamic prices. The
blocks are written in the setting *Block tariff* (``price_blocks``), one rule
per line (or separated by ``;``):

    0,30                      the price at any other time
    23:00-07:00 0,22          every day from 23:00 to 07:00 (past midnight)
    mon-fri 17:00-21:00 0,40  only on working days
    sat,sun 11:00-15:00 0,18  only in the weekend

Days: ``mon tue wed thu fri sat sun`` or Dutch ``ma di wo do vr za zo``, as a
range (``mon-fri``) or a list (``sat,sun``). Prices per kWh in Home
Assistant's currency, with a decimal point or comma. A later rule wins over
an earlier one where they overlap. Time not covered by any rule has no price
(the plans then end there).

The prices are fixed, so they count as published for the whole planning
horizon (``DAYS_AHEAD``). Export: by the export settings (a factor of these
prices or a sensor).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ....const import DOMAIN
from .base import ROLE_IMPORT, PriceData, PriceDriver, PriceSource
from .price_points import PricePoint

CONF_PRICE_BLOCKS = "price_blocks"
SOURCE_ID = "settings"
DAYS_AHEAD = 8  # the planning horizon is at most 7 days
STEP = timedelta(minutes=15)
DAYS = {
    **{d: i for i, d in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))},
    **{d: i for i, d in enumerate(("ma", "di", "wo", "do", "vr", "za", "zo"))},
}
_TIME = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")


class BlockError(ValueError):
    """A rule that cannot be read (``line`` is its number, from 1)."""

    def __init__(self, line: int, text: str) -> None:
        """Initialize."""
        super().__init__(f"line {line}: {text}")
        self.line = line
        self.text = text


@dataclass(frozen=True, slots=True)
class Block:
    """One rule: on ``days`` (weekday numbers) from ``start`` to ``end``
    (minutes after midnight; ``end`` <= ``start`` runs past midnight) the
    ``price``; ``start`` None = the price at any other time."""

    days: frozenset[int]
    start: int | None
    end: int | None
    price: float

    def covers(self, weekday: int, minute: int) -> bool:
        """Whether the rule holds on ``weekday`` at ``minute`` past midnight."""
        if self.start is None or self.end is None:
            return weekday in self.days
        if self.start < self.end:
            return weekday in self.days and self.start <= minute < self.end
        # Past midnight: the evening part on the day itself, the morning
        # part on the next day.
        if minute >= self.start:
            return weekday in self.days
        return minute < self.end and (weekday - 1) % 7 in self.days


def _days(token: str) -> frozenset[int] | None:
    found: set[int] = set()
    for part in token.lower().split(","):
        first, _, last = part.partition("-")
        if first not in DAYS or (last and last not in DAYS):
            return None
        a, b = DAYS[first], DAYS[last or first]
        found.update(range(a, b + 1) if a <= b else [*range(a, 7), *range(b + 1)])
    return frozenset(found)


def _price(token: str) -> float | None:
    try:
        return float(token.replace(",", "."))
    except ValueError:
        return None


def parse_blocks(text: str | None) -> list[Block]:
    """The rules of ``text``; raises ``BlockError`` for one it cannot read."""
    blocks: list[Block] = []
    rules = [r.strip() for r in re.split(r"[;\n]", text or "")]
    for number, rule in enumerate(rules, start=1):
        if not rule or rule.startswith("#"):
            continue
        tokens = rule.split()
        price = _price(tokens[-1])
        if price is None or not -10 <= price <= 10:
            raise BlockError(number, rule)
        days: frozenset[int] = frozenset(range(7))
        start = end = None
        time_seen = False
        for token in tokens[:-1]:
            match = _TIME.match(token)
            if match and not time_seen:
                h1, m1, h2, m2 = (int(g) for g in match.groups())
                if h1 > 24 or h2 > 24 or m1 > 59 or m2 > 59:
                    raise BlockError(number, rule)
                start, end = h1 * 60 + m1, h2 * 60 + m2
                if start >= 24 * 60 or end > 24 * 60:
                    raise BlockError(number, rule)
                if start == 0 and end == 24 * 60:
                    start = end = None  # the whole day
                    time_seen = True
                    continue
                end %= 24 * 60
                time_seen = True
                continue
            found = _days(token)
            if found is None:
                raise BlockError(number, rule)
            days = found
        if start is not None and start == end:
            raise BlockError(number, rule)
        blocks.append(Block(days, start, end, price))
    return blocks


def block_prices(
    blocks: list[Block], start: datetime, end: datetime
) -> list[PricePoint]:
    """The price per quarter of an hour from ``start`` to ``end`` (local
    time), neighbours with the same price merged; no point where no rule
    holds."""
    points: list[PricePoint] = []
    t = dt_util.as_local(start)
    t = t.replace(minute=t.minute // 15 * 15, second=0, microsecond=0)
    end = dt_util.as_local(end)
    while t < end:
        minute = t.hour * 60 + t.minute
        price = None
        for block in blocks:
            if block.covers(t.weekday(), minute):
                price = block.price
        # (A clock change: the next quarter by wall time.)
        nxt = dt_util.as_local(dt_util.as_utc(t) + STEP)
        if price is not None:
            utc_t, utc_n = dt_util.as_utc(t), dt_util.as_utc(nxt)
            last = points[-1] if points else None
            if last is not None and last.end == utc_t and last.price == price:
                points[-1] = PricePoint(last.start, utc_n, price)
            else:
                points.append(PricePoint(utc_t, utc_n, price))
        t = nxt
    return points


def _options(hass: HomeAssistant) -> dict[str, Any]:
    entries = hass.config_entries.async_entries(DOMAIN)
    return dict(entries[0].options) if entries else {}


class BlockTariffDriver(PriceDriver):
    """Fixed prices per time block from the setting *Block tariff*."""

    key = "blocks"
    name = "Block tariff"
    verified = False

    def find(self, hass: HomeAssistant) -> list[PriceSource]:
        """Always offered: the blocks are filled in in the same settings."""
        dutch = (hass.config.language or "").startswith("nl")
        title = (
            "Bloktarief (vaste prijzen per tijdsblok, instelling Bloktarief)"
            if dutch
            else "Block tariff (fixed prices per time block, setting Block tariff)"
        )
        return [
            PriceSource(
                driver=self.key,
                id=SOURCE_ID,
                title=title,
                roles=frozenset({ROLE_IMPORT}),
                days_ahead=DAYS_AHEAD,
            )
        ]

    async def async_read(
        self, hass: HomeAssistant, source: str, role: str
    ) -> PriceData:
        """The block prices from the start of today to ``DAYS_AHEAD`` on."""
        if role != ROLE_IMPORT:
            return PriceData([])
        try:
            blocks = parse_blocks(_options(hass).get(CONF_PRICE_BLOCKS))
        except BlockError:
            return PriceData([])  # the settings form does not store these
        now = dt_util.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        currency = hass.config.currency or "EUR"
        return PriceData(
            block_prices(blocks, start, start + timedelta(days=DAYS_AHEAD)),
            f"{currency}/kWh",
        )
