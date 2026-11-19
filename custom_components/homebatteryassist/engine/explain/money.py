"""Amounts of money in plain text, in Home Assistant's currency.

Prices are per kWh in the main currency (``engine/units.price_unit_factor``);
the currency is the one set in Home Assistant (``hass.config.currency``).
"""

from __future__ import annotations

DEFAULT_CURRENCY = "EUR"

# Common currency symbols; any other currency is shown by its code.
SYMBOLS = {
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
    "AUD": "A$",
    "CAD": "C$",
    "NZD": "NZ$",
    "JPY": "¥",
    "CNY": "¥",
    "INR": "₹",
    "PLN": "zł",
    "CHF": "CHF",
    "SEK": "kr",
    "NOK": "kr",
    "DKK": "kr",
}


def format_money(
    value: float | None,
    currency: str | None = None,
    language: str | None = None,
    digits: int = 2,
) -> str:
    """``value`` with the currency's symbol (or code), e.g. "€ 0,25" (nl) or
    "€ 0.25"; "-" without a value."""
    if value is None:
        return "-"
    code = (currency or DEFAULT_CURRENCY).upper()
    symbol = SYMBOLS.get(code, code)
    text = f"{value:.{digits}f}"
    if (language or "").lower().startswith("nl"):
        text = text.replace(".", ",")
    return f"{symbol} {text}"
