"""Human-readable explanations per decision key, per language.

Placeholders are filled from the decision parameters; datetimes are shown in
local time. Add every new key in all languages (tests enforce this).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

DEFAULT_LANGUAGE = "en"

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "horizon_setting": "Planning {days} days ahead (until {end}), as configured.",
        "horizon_price": "Planning only until {end}: the price forecast does not reach further.",
        "horizon_pv": "Planning only until {end}: the PV forecast does not reach further.",
        "horizon_no_price": "No planning possible: the price forecast ({entity}) provides no upcoming prices.",
        "horizon_no_pv": "No planning possible: the selected PV forecasts provide no data.",
        "consumption_unavailable": "House consumption unknown: no valid measurement from {sensors}.",
        "consumption_restored": "House consumption is measured again.",
    },
    "nl": {
        "horizon_setting": "Planning {days} dagen vooruit (tot {end}), zoals ingesteld.",
        "horizon_price": "Planning alleen tot {end}: de prijsvoorspelling reikt niet verder.",
        "horizon_pv": "Planning alleen tot {end}: de PV-voorspelling reikt niet verder.",
        "horizon_no_price": "Geen planning mogelijk: de prijsvoorspelling ({entity}) bevat geen komende prijzen.",
        "horizon_no_pv": "Geen planning mogelijk: de gekozen PV-voorspellingen leveren geen gegevens.",
        "consumption_unavailable": "Huisverbruik onbekend: geen geldige meting van {sensors}.",
        "consumption_restored": "Huisverbruik wordt weer gemeten.",
    },
}


def _format(value: Any) -> str:
    if isinstance(value, datetime):
        return dt_util.as_local(value).strftime("%d-%m %H:%M")
    return str(value)


def render(language: str | None, key: str, params: dict[str, Any]) -> str:
    """Return the explanation for ``key`` in ``language`` (fallback English)."""
    lang = (language or DEFAULT_LANGUAGE).split("-")[0].lower()
    templates = MESSAGES.get(lang, MESSAGES[DEFAULT_LANGUAGE])
    template = templates.get(key) or MESSAGES[DEFAULT_LANGUAGE].get(key)
    if template is None:
        return key
    try:
        return template.format(**{k: _format(v) for k, v in params.items()})
    except (KeyError, IndexError):
        return template
