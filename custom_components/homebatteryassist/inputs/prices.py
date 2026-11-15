"""Price forecast, read from the attributes of a sensor of another integration.

There is no Home Assistant standard for price forecasts, so the common attribute
formats are recognised: lists of ``{start, price}``-like dicts (e.g. Nordpool
``raw_today``/``raw_tomorrow``, ENTSO-e ``prices``, Frank Energie ``prices``) or
``{timestamp: price}`` mappings.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import State

from .units import parse_float, parse_time

PRICE_ATTRIBUTES = (
    "prices",
    "prices_today",
    "prices_tomorrow",
    "raw_today",
    "raw_tomorrow",
    "today",
    "tomorrow",
    "forecast",
    "data",
)
START_KEYS = (
    "start",
    "start_time",
    "starts_at",
    "startsAt",
    "from",
    "time",
    "datetime",
)
END_KEYS = ("end", "end_time", "ends_at", "endsAt", "till", "until", "to")
PRICE_KEYS = ("price", "value", "total", "electricity_price", "price_per_kwh")


@dataclass(frozen=True, slots=True)
class PricePoint:
    """Price for one period, in the unit of the source sensor."""

    start: datetime
    end: datetime
    price: float


def _first(item: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in item:
            return item[key]
    return None


def _raw_points(value: Any) -> list[tuple[datetime, datetime | None, float]]:
    """Extract (start, end or None, price) from one attribute value."""
    points: list[tuple[datetime, datetime | None, float]] = []
    if isinstance(value, Mapping):
        for key, raw_price in value.items():
            start, price = parse_time(key), parse_float(raw_price)
            if start is not None and price is not None:
                points.append((start, None, price))
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, Mapping):
                continue
            start = parse_time(_first(item, START_KEYS))
            price = parse_float(_first(item, PRICE_KEYS))
            if start is not None and price is not None:
                points.append((start, parse_time(_first(item, END_KEYS)), price))
    return points


def parse_price_forecast(state: State | None) -> list[PricePoint]:
    """Return the price forecast found in the attributes of ``state``, sorted.

    Periods without an explicit end last until the next period starts; the last
    one gets the length of the period before it (or one hour).
    """
    if state is None:
        return []
    raw: dict[datetime, tuple[datetime | None, float]] = {}
    for attribute in PRICE_ATTRIBUTES:
        for start, end, price in _raw_points(state.attributes.get(attribute)):
            raw.setdefault(start, (end, price))

    starts = sorted(raw)
    points: list[PricePoint] = []
    for index, start in enumerate(starts):
        end, price = raw[start]
        if end is None:
            if index + 1 < len(starts):
                end = starts[index + 1]
            elif index > 0:
                end = start + (start - starts[index - 1])
            else:
                end = start + timedelta(hours=1)
        points.append(PricePoint(start, end, price))
    return points
