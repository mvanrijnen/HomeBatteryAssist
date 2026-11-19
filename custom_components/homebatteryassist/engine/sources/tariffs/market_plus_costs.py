"""Built-in tariff: the bare market price plus the costs, then VAT.

For a price source that gives only the market (EPEX / Nord Pool) price, e.g.
Nord Pool, EnergyZero or easyEnergy: import = (market + supplier surcharge +
energy tax) x (1 + VAT), with the amounts from the settings (per kWh excl.
VAT). Without a market price for a period the source's price is kept. Export:
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
        imports: list[float | None] = []
        for slot in data.slots:
            if slot.market is None:
                imports.append(None)  # keep the source's price
            else:
                imports.append(round((slot.market + surcharge + tax) * (1 + vat), 6))
        return TariffResult(imports, [s.export for s in data.slots])
