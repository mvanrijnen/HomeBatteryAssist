"""Price forecast, read from the attributes of a sensor of another integration.

There is no Home Assistant standard for price forecasts, so the common attribute
formats are recognised:

- lists of ``{start, price}``-like dicts (e.g. Nordpool ``raw_today`` /
  ``raw_tomorrow``, ENTSO-e ``prices``, Frank Energie ``prices``, DynTarNL
  ``today`` / ``tomorrow``);
- lists of ``[timestamp, price, flag]`` arrays, timestamp in epoch (ms or s) or
  ISO 8601, optional flag ``"p"`` (published) / ``"f"`` (forecast), e.g. DynTarNL
  ``prices`` with its EPEX forecast;
- ``{timestamp: price}`` mappings.

Each price is marked as published or estimated (forecast), so forecasts can be
checked afterwards against the published prices.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import State
from homeassistant.util import dt as dt_util

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
ESTIMATED_FLAGS = {"f", "forecast", "estimate", "estimated", "predicted"}
EPOCH_MS_THRESHOLD = 10**11  # larger numbers are milliseconds


@dataclass(frozen=True, slots=True)
class PricePoint:
    """Price for one period, in the unit of the source sensor."""

    start: datetime
    end: datetime
    price: float
    estimated: bool = False  # True for a forecast, False for a published price


type RawPoint = tuple[datetime, datetime | None, float, bool]


def _first(item: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in item:
            return item[key]
    return None


def _parse_start(value: Any) -> datetime | None:
    """ISO timestamp, datetime, or epoch seconds / milliseconds."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = value / 1000 if value > EPOCH_MS_THRESHOLD else value
        try:
            return dt_util.utc_from_timestamp(seconds)
        except (OverflowError, OSError, ValueError):
            return None
    return parse_time(value)


def _estimated(flag: Any) -> bool:
    return isinstance(flag, str) and flag.lower() in ESTIMATED_FLAGS


def _raw_points(value: Any) -> list[RawPoint]:
    """Extract (start, end or None, price, estimated) from one attribute value."""
    points: list[RawPoint] = []
    if isinstance(value, Mapping):
        for key, raw_price in value.items():
            start, price = parse_time(key), parse_float(raw_price)
            if start is not None and price is not None:
                points.append((start, None, price, False))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, Mapping):
                start = parse_time(_first(item, START_KEYS))
                price = parse_float(_first(item, PRICE_KEYS))
                if start is not None and price is not None:
                    end = parse_time(_first(item, END_KEYS))
                    points.append((start, end, price, _estimated(item.get("type"))))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                start, price = _parse_start(item[0]), parse_float(item[1])
                if start is not None and price is not None:
                    flag = item[2] if len(item) > 2 else None
                    points.append((start, None, price, _estimated(flag)))
    return points


def parse_price_forecast(state: State | None) -> list[PricePoint]:
    """Return the price forecast found in the attributes of ``state``, sorted.

    If several attributes cover the same start, the first one found wins
    (``PRICE_ATTRIBUTES`` order). Periods without an explicit end last until
    the next period starts; the last one gets the length of the period before
    it (or one hour).
    """
    if state is None:
        return []
    raw: dict[datetime, tuple[datetime | None, float, bool]] = {}
    for attribute in PRICE_ATTRIBUTES:
        for start, end, price, estimated in _raw_points(
            state.attributes.get(attribute)
        ):
            raw.setdefault(start, (end, price, estimated))

    starts = sorted(raw)
    points: list[PricePoint] = []
    for index, start in enumerate(starts):
        end, price, estimated = raw[start]
        if end is None:
            if index + 1 < len(starts):
                end = starts[index + 1]
            elif index > 0:
                end = start + (start - starts[index - 1])
            else:
                end = start + timedelta(hours=1)
        points.append(PricePoint(start, end, price, estimated))
    return points
