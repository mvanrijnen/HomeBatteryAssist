"""Net metering (NL: salderen, until 1 January 2027).

While net metering applies, exported energy (up to what is imported over the
year) is worth more than the export price alone:

- **dynamic contract**: per hour the export price of the contract (the market
  price minus the supplier's fee), plus the energy tax with VAT that is netted
  (``tax``, per kWh);
- **fixed contract**: the same as a kWh imported (the import price).

Applied after the tariff, to the periods before ``until``. Not counted: the
part of the year's export above the year's import, which earns only the
export price (HomeBatteryAssist does not follow the yearly totals).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ..prices.price_points import PricePoint

NET_METERING_NONE = "none"
NET_METERING_DYNAMIC = "dynamic"
NET_METERING_FIXED = "fixed"
NET_METERING_MODES = (NET_METERING_NONE, NET_METERING_DYNAMIC, NET_METERING_FIXED)


def apply_net_metering(
    prices: Sequence[PricePoint],
    export_prices: Sequence[PricePoint],
    *,
    mode: str,
    tax: float,
    until: datetime,
    export_factor: float,
) -> list[PricePoint]:
    """The export prices with net metering, per period of ``prices`` (the
    import prices) that starts before ``until``; later periods as they were.
    Where the contract's export price is not known: import x factor."""
    if mode not in (NET_METERING_DYNAMIC, NET_METERING_FIXED) or not prices:
        return list(export_prices)
    known = sorted(export_prices, key=lambda p: p.start)

    def export_at(when: datetime) -> float | None:
        return next((p.price for p in known if p.start <= when < p.end), None)

    result: list[PricePoint] = []
    for point in prices:
        base = export_at(point.start)
        if point.start >= until:
            if base is not None:
                result.append(PricePoint(point.start, point.end, base, point.estimated))
            continue
        if mode == NET_METERING_FIXED:
            price = point.price
        else:
            own = base if base is not None else point.price * export_factor
            price = own + tax
        result.append(PricePoint(point.start, point.end, price, point.estimated))
    # Export prices beyond the import prices stay as they were.
    last = prices[-1].end
    result.extend(p for p in known if p.start >= last)
    return result
