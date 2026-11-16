"""Built-in tariff: the prices as the price source and the export settings give them.

Import: the price source's price (e.g. DynTarNL's all-in price). Export: by
the export settings (market price, a factor of the import price, or a sensor).
"""

from __future__ import annotations

from .base import Tariff, TariffInput, TariffResult


class SourceTariff(Tariff):
    """The source's prices, unchanged."""

    key = "source"
    name = "As the price source gives them"

    def prices(self, data: TariffInput) -> TariffResult:
        return TariffResult(
            [s.price for s in data.slots], [s.export for s in data.slots]
        )
