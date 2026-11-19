"""Price thresholds entered in ct are converted once to the main currency."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist import _convert_cent_thresholds
from custom_components.homebatteryassist.const import DOMAIN
from custom_components.homebatteryassist.engine.explain import DecisionLog


async def test_cent_thresholds_converted_once(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={"min_discharge_price": 4.5, "max_charge_price": 0.2},
    )
    entry.add_to_hass(hass)
    decisions = DecisionLog(hass, entry.entry_id)
    _convert_cent_thresholds(hass, entry, decisions)
    assert entry.options["min_discharge_price"] == 0.045
    assert entry.options["max_charge_price"] == 0.2  # already per kWh
    assert [d["key"] for d in decisions.entries] == ["price_setting_converted"]
    _convert_cent_thresholds(hass, entry, decisions)
    assert len(decisions.entries) == 1


async def test_no_conversion_in_other_currencies(hass: HomeAssistant) -> None:
    hass.config.currency = "CZK"
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={"max_charge_price": 5.0})
    entry.add_to_hass(hass)
    _convert_cent_thresholds(hass, entry, DecisionLog(hass, entry.entry_id))
    assert entry.options["max_charge_price"] == 5.0
