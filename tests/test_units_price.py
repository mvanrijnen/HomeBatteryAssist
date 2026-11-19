"""Tests for converting price units to a price per kWh."""

import pytest

from custom_components.homebatteryassist.engine.units import price_unit_factor


@pytest.mark.parametrize(
    ("unit", "factor", "normal"),
    [
        ("€/kWh", 1.0, "€/kWh"),
        ("EUR/kWh", 1.0, "EUR/kWh"),
        ("ct/kWh", 0.01, "EUR/kWh"),
        ("c/kWh", 0.01, "EUR/kWh"),
        ("EUR/MWh", 0.001, "EUR/kWh"),
        ("€/MWh", 0.001, "€/kWh"),
        ("öre/kWh", 0.01, "SEK/kWh"),
        ("SEK/kWh", 1.0, "SEK/kWh"),
        (None, 1.0, None),
        ("", 1.0, ""),
        ("price", 1.0, "price"),
    ],
)
def test_price_unit_factor(unit, factor, normal) -> None:
    got_factor, got_unit = price_unit_factor(unit)
    assert got_factor == pytest.approx(factor)
    assert got_unit == normal
