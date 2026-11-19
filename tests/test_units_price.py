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


def test_generic_cents_take_home_assistants_currency() -> None:
    from custom_components.homebatteryassist.engine.units import price_unit_factor

    assert price_unit_factor("c/kWh", "AUD") == (0.01, "AUD/kWh")
    assert price_unit_factor("ct/kWh") == (0.01, "EUR/kWh")
    assert price_unit_factor("öre/kWh", "EUR") == (0.01, "SEK/kWh")


def test_money_in_home_assistants_currency() -> None:
    from custom_components.homebatteryassist.engine.explain.money import format_money

    assert format_money(0.25, "EUR", "nl") == "€ 0,25"
    assert format_money(0.25, "USD", "en") == "$ 0.25"
    assert format_money(1.5, "XYZ", "en") == "XYZ 1.50"
    assert format_money(None) == "-"
