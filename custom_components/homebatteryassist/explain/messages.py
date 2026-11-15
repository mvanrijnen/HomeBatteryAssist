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
        "horizon_setting": "Planning {hours} hours ahead (until {end}): the configured maximum of {days} days.",
        "horizon_price": "Planning {hours} hours ahead (until {end}): the price forecast does not reach further.",
        "horizon_pv": "Planning {hours} hours ahead (until {end}): the PV forecast does not reach further.",
        "horizon_no_price": "No planning possible: the price forecast ({entity}) provides no upcoming prices.",
        "horizon_no_pv": "No planning possible: the selected PV forecasts provide no data.",
        "consumption_unavailable": "House consumption unknown: no valid measurement from {sensors}.",
        "consumption_restored": "House consumption is measured again.",
        "battery_unavailable": "Battery {name} unavailable: its state of charge or power sensor has no valid value.",
        "battery_restored": "Battery {name} is available again.",
        "battery_full_charge": "Battery {name} is fully charged.",
        "history_imported": "Consumption history imported: {count} periods from {first} to {last}.",
        "consumption_method_weekday_hour": "Consumption forecast based on the average per weekday and hour ({days} days of history).",
        "consumption_method_daytype_hour": "Consumption forecast based on weekdays/weekend per hour: not enough history per weekday yet ({days} days).",
        "consumption_method_hour": "Consumption forecast based on the average per hour of the day: little history yet ({days} days).",
        "consumption_method_overall": "Consumption forecast based on the overall average: very little history yet ({days} days).",
        "consumption_method_none": "No consumption forecast: no history yet, or no planning possible.",
        "forecast_adjusted": "Consumption forecast adjusted: {name} ({change}) from {start} to {end}.",
        "forecast_adjustments_cleared": "{count} adjustment(s) of the consumption forecast removed.",
        "correction_consumption": "The consumption forecast is now corrected by {correction} ({mode}, {samples} comparisons), because it deviated systematically.",
        "correction_pv": "The PV forecast is now corrected by {correction} ({mode}, {samples} comparisons): measured production differed systematically from the forecast.",
        "correction_price": "Forecast (estimated) prices are now corrected by {correction} ({mode}, {samples} comparisons) compared with the prices published later.",
        "correction_none": "The {kind} forecast is no longer corrected ({mode}).",
        "correction_mode_learned": "The {kind} forecast is corrected from its running accuracy again.",
        "correction_mode_off": "Correction of the {kind} forecast switched off (until {until}); accuracy is still measured.",
        "correction_mode_manual": "Manual correction of the {kind} forecast: {value} (until {until}).",
        "accuracy_reset": "What was learned about the {kind} forecast has been reset.",
        "battery_plan": "Battery plan ({mode}): expected saving {saving} in the planning window (other modes: {others}). Charge: {charge}. Discharge: {discharge}. Advice only, nothing is controlled.",
        "plan_mode_set": "Battery plan mode set to {mode}.",
    },
    "nl": {
        "horizon_setting": "Planning {hours} uur vooruit (tot {end}): het ingestelde maximum van {days} dagen.",
        "horizon_price": "Planning {hours} uur vooruit (tot {end}): de prijsvoorspelling reikt niet verder.",
        "horizon_pv": "Planning {hours} uur vooruit (tot {end}): de PV-voorspelling reikt niet verder.",
        "horizon_no_price": "Geen planning mogelijk: de prijsvoorspelling ({entity}) bevat geen komende prijzen.",
        "horizon_no_pv": "Geen planning mogelijk: de gekozen PV-voorspellingen leveren geen gegevens.",
        "consumption_unavailable": "Huisverbruik onbekend: geen geldige meting van {sensors}.",
        "consumption_restored": "Huisverbruik wordt weer gemeten.",
        "battery_unavailable": "Batterij {name} niet beschikbaar: de sensor voor vulling of vermogen heeft geen geldige waarde.",
        "battery_restored": "Batterij {name} is weer beschikbaar.",
        "battery_full_charge": "Batterij {name} is volledig opgeladen.",
        "history_imported": "Verbruikshistorie geïmporteerd: {count} perioden van {first} tot {last}.",
        "consumption_method_weekday_hour": "Verbruiksvoorspelling gebaseerd op het gemiddelde per weekdag en uur ({days} dagen historie).",
        "consumption_method_daytype_hour": "Verbruiksvoorspelling gebaseerd op werkdag/weekend per uur: nog te weinig historie per weekdag ({days} dagen).",
        "consumption_method_hour": "Verbruiksvoorspelling gebaseerd op het gemiddelde per uur van de dag: nog weinig historie ({days} dagen).",
        "consumption_method_overall": "Verbruiksvoorspelling gebaseerd op het totale gemiddelde: nog zeer weinig historie ({days} dagen).",
        "consumption_method_none": "Geen verbruiksvoorspelling: nog geen historie, of geen planning mogelijk.",
        "forecast_adjusted": "Verbruiksvoorspelling aangepast: {name} ({change}) van {start} tot {end}.",
        "forecast_adjustments_cleared": "{count} aanpassing(en) van de verbruiksvoorspelling verwijderd.",
        "correction_consumption": "De verbruiksvoorspelling wordt nu gecorrigeerd met {correction} ({mode}, {samples} vergelijkingen), omdat hij systematisch afweek.",
        "correction_pv": "De PV-voorspelling wordt nu gecorrigeerd met {correction} ({mode}, {samples} vergelijkingen): de gemeten opwek week systematisch af van de voorspelling.",
        "correction_price": "Voorspelde prijzen worden nu gecorrigeerd met {correction} ({mode}, {samples} vergelijkingen) ten opzichte van de later gepubliceerde prijzen.",
        "correction_none": "De {kind}-voorspelling wordt niet meer gecorrigeerd ({mode}).",
        "correction_mode_learned": "De {kind}-voorspelling wordt weer gecorrigeerd op basis van de meelopende nauwkeurigheid.",
        "correction_mode_off": "Correctie van de {kind}-voorspelling uitgeschakeld (tot {until}); de nauwkeurigheid wordt wel gemeten.",
        "correction_mode_manual": "Handmatige correctie van de {kind}-voorspelling: {value} (tot {until}).",
        "accuracy_reset": "Wat geleerd was over de {kind}-voorspelling is gewist.",
        "battery_plan": "Batterijplan ({mode}): verwachte besparing {saving} in het planningsvenster (andere modi: {others}). Laden: {charge}. Ontladen: {discharge}. Alleen advies, er wordt niets aangestuurd.",
        "plan_mode_set": "Modus batterijplan ingesteld op {mode}.",
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
