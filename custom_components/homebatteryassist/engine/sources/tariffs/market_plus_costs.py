"""Built-in tariff: the bare market price plus the costs, then VAT.

For a price source that gives only the market (EPEX / Nord Pool) price, e.g.
Nord Pool, EnergyZero or easyEnergy: import = (market + supplier surcharge +
energy tax) x (1 + VAT), with the amounts from the settings (per kWh excl.
VAT). Without a market price for a period (e.g. a longer, estimated
forecast after the source's own prices) the market price is the source's
price minus the usual difference between the two (the median over the
periods that have both; a source incl. VAT, or a forecast put on the level
of the import prices, is not taxed twice); without any period that has both,
the source's price. Export:
as the export settings give it (no net metering is assumed).
"""

from __future__ import annotations

from .base import Tariff, TariffInput, TariffResult


class MarketPlusCostsTariff(Tariff):
    """Market price + surcharge + energy tax, plus VAT."""

    key = "market_plus_costs"
    name = "Market price + surcharge + energy tax, plus VAT"
    needs_market = True

    def prices(self, data: TariffInput) -> TariffResult:
        surcharge = float(data.settings.get("tariff_surcharge", 0.0))
        tax = float(data.settings.get("tariff_energy_tax", 0.0))
        vat = float(data.settings.get("tariff_vat", 21.0)) / 100
        differences = sorted(
            s.price - s.market
            for s in data.slots
            if s.market is not None and s.price is not None
        )
        offset = differences[len(differences) // 2] if differences else 0.0
        imports: list[float | None] = []
        for slot in data.slots:
            market = slot.market if slot.market is not None else slot.price - offset
            imports.append(round((market + surcharge + tax) * (1 + vat), 6))
        return TariffResult(imports, [s.export for s in data.slots])
