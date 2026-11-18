"""Net metering (NL, until 2027): what exported energy is worth."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.homebatteryassist.engine.sources.prices.price_points import (
    PricePoint,
)
from custom_components.homebatteryassist.engine.sources.tariffs.net_metering import (
    apply_net_metering,
)

START = datetime(2026, 12, 31, 22, tzinfo=UTC)
UNTIL = datetime(2026, 12, 31, 23, tzinfo=UTC)  # 1 Jan 2027 00:00 local (CET)
H = timedelta(hours=1)


def _points(*prices: float) -> list[PricePoint]:
    return [
        PricePoint(START + i * H, START + (i + 1) * H, p) for i, p in enumerate(prices)
    ]


def test_dynamic_adds_the_netted_tax_until_the_end() -> None:
    """Dynamic: export price + energy tax before 2027, the export price after."""
    imports = _points(0.30, 0.28)
    exports = _points(0.08, 0.07)
    result = apply_net_metering(
        imports, exports, mode="dynamic", tax=0.1108, until=UNTIL, export_factor=0.25
    )
    assert [round(p.price, 4) for p in result] == [0.1908, 0.07]


def test_fixed_export_is_the_import_price() -> None:
    imports = _points(0.25, 0.25)
    result = apply_net_metering(
        imports, [], mode="fixed", tax=0.1108, until=UNTIL, export_factor=0.25
    )
    assert [p.price for p in result] == [0.25]  # after 2027: no export price known


def test_none_changes_nothing_and_unknown_export_uses_the_factor() -> None:
    imports = _points(0.40)
    exports = _points(0.05)
    assert (
        apply_net_metering(
            imports, exports, mode="none", tax=0.1108, until=UNTIL, export_factor=0.25
        )
        == exports
    )
    result = apply_net_metering(
        imports, [], mode="dynamic", tax=0.1, until=UNTIL, export_factor=0.25
    )
    assert round(result[0].price, 4) == 0.2  # 0.40 x 0.25 + 0.1
