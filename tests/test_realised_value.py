"""Realised battery value without net metering."""

import pytest

from custom_components.homebatteryassist.engine.inputs.batteries import realised_value

PRICE = 0.30
EXPORT = 0.05


def test_discharge_against_import_saves_import_price() -> None:
    """1 kWh discharged while the house still imports 0.5 kWh."""
    assert realised_value(-1.0, 0.5, PRICE, EXPORT) == pytest.approx(0.30)


def test_charge_from_solar_costs_export_price() -> None:
    """Charging 1 kWh from solar that would have been exported."""
    assert realised_value(1.0, -0.5, PRICE, EXPORT) == pytest.approx(-0.05)


def test_charge_from_grid_costs_import_price() -> None:
    assert realised_value(1.0, 1.5, PRICE, EXPORT) == pytest.approx(-0.30)


def test_discharge_to_grid_earns_export_price_only() -> None:
    """Discharging into an export earns the export price, not the import price."""
    assert realised_value(-1.0, -1.0, PRICE, EXPORT) == pytest.approx(0.05)


def test_mixed_split() -> None:
    """Without battery 0.4 kWh import; discharging 1 kWh: 0.4 saved at import,
    0.6 exported."""
    assert realised_value(-1.0, -0.6, PRICE, EXPORT) == pytest.approx(
        0.4 * PRICE + 0.6 * EXPORT
    )


def test_no_grid_measurement_falls_back_to_import_price() -> None:
    assert realised_value(-1.0, None, PRICE, EXPORT) == pytest.approx(0.30)


def test_no_export_price_means_import_price() -> None:
    assert realised_value(1.0, -2.0, PRICE, None) == pytest.approx(-0.30)
