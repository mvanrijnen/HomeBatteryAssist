"""Template for an own tariff — a code example only, never registered here.

Copy this file to ``/config/homebatteryassist/tariffs/`` (create the folder),
rename the class, set ``key`` and ``name``, fill in the numbers of your
contract, and reload HomeBatteryAssist. Choose it in the settings (Tariff).

``prices`` gets per period the price source's price, the market price (with
``needs_market = True``, when the source offers it) and the export price by
the export settings, and returns what a kWh really costs and earns. Return
None to keep the source's price for a period.

This example: a dynamic contract without net metering, built from the market
price. THE NUMBERS BELOW ARE PLACEHOLDERS — use those of your own contract
(per kWh, in the unit of your prices).
"""

from __future__ import annotations

from custom_components.homebatteryassist.inputs.tariffs.base import (
    Tariff,
    TariffInput,
    TariffResult,
)

SURCHARGE = 0.02  # supplier's surcharge on import, excl. VAT (placeholder)
ENERGY_TAX = 0.10  # energy tax, excl. VAT (placeholder)
VAT = 0.21  # VAT on import
EXPORT_COST = 0.02  # supplier's cost per exported kWh (placeholder)


class DynamicContractTariff(Tariff):
    """Market price + surcharges for import; market price - costs for export."""

    key = "dynamic_contract"  # becomes "custom_dynamic_contract"
    name = "Dynamic contract (example)"
    needs_market = True

    def prices(self, data: TariffInput) -> TariffResult:
        imports: list[float | None] = []
        exports: list[float | None] = []
        for slot in data.slots:
            if slot.market is None:
                # No market price: keep what the source gives.
                imports.append(None)
                exports.append(None)
                continue
            imports.append(round((slot.market + SURCHARGE + ENERGY_TAX) * (1 + VAT), 5))
            exports.append(round(slot.market - EXPORT_COST, 5))
        return TariffResult(imports, exports)
