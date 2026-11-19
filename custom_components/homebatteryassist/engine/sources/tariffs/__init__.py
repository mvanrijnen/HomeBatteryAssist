"""Tariff modules: the built-in one and the user's own.

Own tariffs are Python files in ``/config/homebatteryassist/tariffs/`` (see
``template.py``), keyed ``custom_<key>``. ``apply_tariff`` runs the chosen
tariff with HomeBatteryAssist's final check.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from homeassistant.core import HomeAssistant

from ...own_modules import async_load_modules, load_modules_from
from ..prices.price_points import PricePoint
from .as_price_source import SourceTariff
from .base import MAX_PRICE, Tariff, TariffInput, TariffResult, TariffSlot
from .market_plus_costs import MarketPlusCostsTariff

DEFAULT_TARIFF = "source"
BUILTIN: dict[str, Tariff] = {
    t.key: t for t in (SourceTariff(), MarketPlusCostsTariff())
}

__all__ = [
    "BUILTIN",
    "DEFAULT_TARIFF",
    "Tariff",
    "TariffInput",
    "TariffResult",
    "TariffSlot",
    "apply_tariff",
    "async_load_user_tariffs",
    "load_tariffs_from",
]


def _usable(found: dict[str, Tariff]) -> dict[str, Tariff]:
    return {k: t for k, t in found.items() if type(t).prices is not Tariff.prices}


def load_tariffs_from(folder: Path) -> dict[str, Tariff]:
    """Tariffs defined in the Python files of ``folder`` (blocking)."""
    return _usable(load_modules_from(folder, Tariff, "tariffs"))


async def async_load_user_tariffs(hass: HomeAssistant) -> dict[str, Tariff]:
    """The user's own tariffs from ``/config/homebatteryassist/tariffs``."""
    return _usable(await async_load_modules(hass, "tariffs", Tariff))


def _checked(value: float | None, fallback: float | None) -> float | None:
    try:
        number = float(value) if value is not None else None
    except (TypeError, ValueError):
        number = None
    if number is None or not math.isfinite(number) or abs(number) > MAX_PRICE:
        return fallback
    return number


def apply_tariff(
    tariff: Tariff,
    prices: Sequence[PricePoint],
    export_prices: Sequence[PricePoint],
    market: Sequence[PricePoint],
    now: datetime,
    unit: str | None,
    export_factor: float,
    settings: dict[str, float] | None = None,
) -> tuple[list[PricePoint], list[PricePoint]]:
    """Import and export prices per period of ``prices`` after ``tariff``.

    Where the export price is not known it is the import price x
    ``export_factor`` (as without a tariff). Raises what the tariff raises.
    """
    if not prices:
        return [], list(export_prices)

    def over(
        points: Sequence[PricePoint], start: datetime, end: datetime
    ) -> float | None:
        """Time-weighted price over [start, end) (hourly import prices with
        quarter export or market prices); None when nothing covers it."""
        total = seconds = 0.0
        for p in points:
            if p.end <= start or p.start >= end:
                continue
            part = (min(p.end, end) - max(p.start, start)).total_seconds()
            total += p.price * part
            seconds += part
        return total / seconds if seconds else None

    slots = []
    for point in prices:
        export = over(export_prices, point.start, point.end)
        slots.append(
            TariffSlot(
                point.start,
                point.end,
                point.price,
                over(market, point.start, point.end),
                export if export is not None else point.price * export_factor,
                point.estimated,
            )
        )
    result = tariff.prices(TariffInput(now, slots, unit, dict(settings or {})))
    imports, exports = [], []
    for i, (point, slot) in enumerate(zip(prices, slots, strict=True)):
        new_import = _checked(
            result.import_prices[i] if i < len(result.import_prices) else None,
            point.price,
        )
        new_export = _checked(
            result.export_prices[i] if i < len(result.export_prices) else None,
            slot.export,
        )
        imports.append(PricePoint(point.start, point.end, new_import, point.estimated))
        if new_export is not None:
            exports.append(
                PricePoint(point.start, point.end, new_export, point.estimated)
            )
    return imports, exports
