"""Tests for the built-in tariff market price + costs."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.homebatteryassist.engine.sources.tariffs import (
    BUILTIN,
    TariffInput,
    TariffSlot,
)

T0 = datetime(2026, 11, 19, 12, tzinfo=UTC)


def test_market_plus_costs() -> None:
    tariff = BUILTIN["market_plus_costs"]
    assert tariff.needs_market
    assert not tariff.verified
    slots = [
        TariffSlot(T0, T0 + timedelta(hours=1), 0.12, 0.10, 0.10, False),
        TariffSlot(T0, T0 + timedelta(hours=1), 0.12, None, 0.08, False),
    ]
    settings = {"tariff_surcharge": 0.02, "tariff_energy_tax": 0.09, "tariff_vat": 21}
    result = tariff.prices(TariffInput(T0, slots, "EUR/kWh", settings))
    assert result.import_prices[0] == pytest.approx((0.10 + 0.02 + 0.09) * 1.21)
    # No market price (e.g. an estimated extension): the source's price minus
    # the usual difference with the market price (0.02 here).
    assert result.import_prices[1] == pytest.approx((0.10 + 0.02 + 0.09) * 1.21)
    assert result.export_prices == [0.10, 0.08]  # as given (no net metering)
