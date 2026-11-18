"""The interface of a tariff module.

A tariff turns the prices of the price source into what a kWh from the grid
really costs and what a kWh to the grid really earns, per period — e.g. for a
contract with export costs, own surcharges or no net metering. The plans,
explanations and the price chart use its outcome.

HomeBatteryAssist keeps the final say: a missing, non-finite or absurd price
(more than ``MAX_PRICE`` per kWh either way) is replaced by the price the
source gave. The accuracy of the price *forecast* is still measured on the
source's prices, before the tariff.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

MAX_PRICE = 10.0  # per kWh; anything beyond is not believed


@dataclass(frozen=True, slots=True)
class TariffSlot:
    """One price period."""

    start: datetime
    end: datetime
    price: float  # import price from the price source (often all-in)
    market: float | None  # market (EPEX) price, if the source offers it
    export: float | None  # export price by the export settings; None = unknown
    estimated: bool  # a forecast, not a published price


@dataclass(frozen=True, slots=True)
class TariffInput:
    """Everything a tariff gets."""

    now: datetime
    slots: list[TariffSlot]
    unit: str | None  # e.g. "EUR/kWh"


@dataclass(slots=True)
class TariffResult:
    """Import and export price per slot (None = keep the source's)."""

    import_prices: list[float | None]
    export_prices: list[float | None]


class Tariff:
    """Base class of a tariff module.

    Subclasses set ``key`` (unique, lowercase), ``name`` and implement
    ``prices``. Set ``needs_market = True`` to get market prices in
    ``TariffSlot.market`` (when the price source offers them). It runs in the
    event loop and must be quick (no I/O).
    """

    key: str = ""
    name: str = ""
    # Tested on a real setup; until then every place where it is chosen
    # says "not tested". Own modules too: set True only after testing.
    verified: bool = False
    description: str = ""
    needs_market: bool = False

    def prices(self, data: TariffInput) -> TariffResult:
        """Import and export price per slot of ``data.slots``."""
        raise NotImplementedError
