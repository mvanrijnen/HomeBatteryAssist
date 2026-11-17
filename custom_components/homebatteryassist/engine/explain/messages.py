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
        "planner_failed": "Planner {name} failed (see the log); its plan is skipped, and if it is the chosen one, zero on the meter is used.",
        "battery_charging": "Since {since} {name} has been charging with {extra}{until}.{plan}",
        "battery_discharging": "Since {since} {name} has been supplying the house{extra}, so less power comes from the grid{until}.{plan}",
        "battery_now_charging": "{name} is charging now with {extra}{until}.{plan}",
        "battery_now_discharging": "{name} is supplying the house now{extra}, so less power comes from the grid{until}.{plan}",
        "battery_now_idle": "{name} is idle now{why}{idle}{until}.{plan}",
        "battery_stopped_charging": "{name} charged from {start} to {end}: {energy}{why}. {idle}{until}.{plan}",
        "battery_stopped_discharging": "{name} supplied power from {start} to {end}: {energy}{why}. {idle}{until}.{plan}",
        "history_imported": "Consumption history imported: {count} periods from {first} to {last}.",
        "consumption_method_weekday_hour": "Consumption forecast based on the average per weekday and hour ({days} days of history).",
        "consumption_method_hour": "Consumption forecast based on the average per hour of the day: little history yet ({days} days).",
        "consumption_method_overall": "Consumption forecast based on the overall average: very little history yet ({days} days).",
        "consumption_method_module": 'Consumption forecast made by the forecaster "{name}" ({days} days of history).',
        "tariff_failed": "Tariff {name} failed (see the log); the prices of the price source are used instead.",
        "forecaster_failed": "Consumption forecaster {name} failed (see the log); the built-in profile is used instead where needed.",
        "consumption_method_none": "No consumption forecast: no history yet, or no planning possible.",
        "temperature_effect": "The consumption follows the outdoor temperature: about {heat} W more per degree colder than {base} °C and {cool} W more per degree warmer than 22 °C (learned from {days} days). The consumption forecast takes the weather forecast into account.",
        "temperature_effect_heat": "The consumption follows the outdoor temperature: about {heat} W more per degree colder than {base} °C (learned from {days} days). The consumption forecast takes the weather forecast into account.",
        "temperature_effect_cool": "The consumption follows the outdoor temperature: about {cool} W more per degree warmer than 22 °C (learned from {days} days). The consumption forecast takes the weather forecast into account.",
        "temperature_no_effect": "No effect of the outdoor temperature on the consumption found ({days} days); the forecast is not adjusted for the weather.",
        "temperature_learning": "Not enough days with outdoor temperature yet to learn its effect on the consumption (7 needed).",
        "temperature_zone_effect": "{name} follows the outdoor temperature: about {heat} W more per degree colder than {base} °C and {cool} W more per degree warmer than 22 °C (learned from {days} days).",
        "temperature_zone_effect_heat": "{name} follows the outdoor temperature: about {heat} W more per degree colder than {base} °C (learned from {days} days).",
        "temperature_zone_effect_cool": "{name} follows the outdoor temperature: about {cool} W more per degree warmer than 22 °C (learned from {days} days).",
        "temperature_zone_no_effect": "No effect of the outdoor temperature on {name} found ({days} days).",
        "temperature_room": "{name}: the room is usually about {day} °C during the day and {night} °C at night; the forecast assumes that.",
        "temperature_room_days": "{name}: the room during the day is usually {days} °C, at night about {night} °C; the forecast assumes that per day of the week.",
        "temperature_no_forecast": "The weather entity gives no temperature forecast; the consumption forecast is not adjusted for the weather.",
        "forecast_adjusted": "Consumption forecast adjusted: {name} ({change}) from {start} to {end}.",
        "forecast_adjustments_cleared": "{count} adjustment(s) of the consumption forecast removed.",
        "correction_consumption": "The consumption forecast is now corrected by {correction} ({mode}, {samples} comparisons), because it deviated systematically.",
        "correction_pv": "The PV forecast is now corrected by {correction} ({mode}, {samples} comparisons): measured production differed systematically from the forecast.",
        "correction_price": "Forecast (estimated) prices are now corrected by {correction} ({mode}, {samples} comparisons) compared with the prices published later.",
        "correction_none": "The {kind} is no longer corrected ({mode}).",
        "correction_mode_learned": "The {kind} is corrected from its running accuracy again.",
        "correction_mode_off": "Correction of the {kind} switched off{until}; accuracy is still measured.",
        "correction_mode_manual": "Manual correction of the {kind}: {value}{until}.",
        "accuracy_reset": "What was learned about the {kind} has been reset.",
        "battery_plan": "Battery plan ({mode}): expected saving {saving} in the planning window (other modes: {others}). Charge: {charge}. Discharge: {discharge}. Advice only, nothing is controlled.",
        "battery_plan_prices": "Battery plan ({mode}): expected saving {saving} in the planning window (other modes: {others}). Charge: {charge} at avg. {charge_price}. Discharge: {discharge} at avg. {discharge_price}. Price difference {spread}, {net_spread} after losses and wear. Advice only, nothing is controlled.",
        "plan_mode_set": "Battery plan mode set to {mode}.",
        "battery_plan_story": "{text}",
        "full_charge_planned": "Full charge of {name} planned {start} - {end} at avg. {price} (average in the period {avg_price}): the cheapest moment before the deadline {deadline} (last full charge: {last}).",
        "full_charge_overdue": "Full charge of {name} is overdue (last full charge: {last}); caught up {start} - {end} at avg. {price} (average in the period {avg_price}), the cheapest moment within {days} days.",
        "battery_switch": "{new} takes over {action} from {old} to keep the batteries balanced (state of charge {new_soc}% vs {old_soc}%).",
        "phase_limit": "{names} held back to {power} together: phase {phase} carries {current} A of at most {max} A (main fuse, with a {margin}% margin).",
        "phase_limit_cleared": "The phases have room again: the virtual batteries are no longer held back by the main fuse.",
        "prices_updated": "New prices published, now until {end} ({hours} hours more); the plans have been recalculated.",
        "phase_relief": "Phase protection: phase {phase} carries {current} A, above the limit of {limit} A. {names} {action} {power} to take load off the phase.",
        "phase_relief_ended": "Phase {phase} is back under the limit. {names} took load off it for {minutes} min, {energy} kWh in total.",
        "peak_shaving": "Peak shaving: the grid would supply {grid}, above the peak limit of {limit}. {names} take {power} off it.",
        "peak_shaving_ended": "Grid import is back under the peak limit. The batteries shaved the peak for {minutes} min, {energy} kWh in total.",
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
        "planner_failed": "Planningsmodule {name} gaf een fout (zie het logboek); het plan ervan wordt overgeslagen, en als die gekozen is, wordt nul op de meter gebruikt.",
        "battery_charging": "{name} laadt sinds {since} met {extra}{until}.{plan}",
        "battery_discharging": "{name} levert sinds {since} stroom aan het huis{extra}, zodat er minder stroom van het net nodig is{until}.{plan}",
        "battery_now_charging": "{name} laadt op dit moment met {extra}{until}.{plan}",
        "battery_now_discharging": "{name} levert op dit moment stroom aan het huis{extra}, zodat er minder stroom van het net nodig is{until}.{plan}",
        "battery_now_idle": "{name} doet op dit moment niets{why}{idle}{until}.{plan}",
        "battery_stopped_charging": "{name} heeft geladen van {start} tot {end}: {energy}{why}. {idle}{until}.{plan}",
        "battery_stopped_discharging": "{name} heeft stroom geleverd van {start} tot {end}: {energy}{why}. {idle}{until}.{plan}",
        "history_imported": "Verbruikshistorie geïmporteerd: {count} perioden van {first} tot {last}.",
        "consumption_method_weekday_hour": "Verbruiksvoorspelling gebaseerd op het gemiddelde per weekdag en uur ({days} dagen historie).",
        "consumption_method_hour": "Verbruiksvoorspelling gebaseerd op het gemiddelde per uur van de dag: nog weinig historie ({days} dagen).",
        "consumption_method_overall": "Verbruiksvoorspelling gebaseerd op het totale gemiddelde: nog zeer weinig historie ({days} dagen).",
        "consumption_method_module": 'Verbruiksvoorspelling gemaakt door de voorspeller "{name}" ({days} dagen historie).',
        "tariff_failed": "Tarief {name} gaf een fout (zie het logboek); de prijzen van de prijsbron worden gebruikt.",
        "forecaster_failed": "Verbruiksvoorspeller {name} gaf een fout (zie het logboek); waar nodig wordt het ingebouwde profiel gebruikt.",
        "consumption_method_none": "Geen verbruiksvoorspelling: nog geen historie, of geen planning mogelijk.",
        "temperature_effect": "Het verbruik volgt de buitentemperatuur: ongeveer {heat} W meer per graad kouder dan {base} °C en {cool} W meer per graad warmer dan 22 °C (geleerd uit {days} dagen). De verbruiksvoorspelling houdt rekening met de weersverwachting.",
        "temperature_effect_heat": "Het verbruik volgt de buitentemperatuur: ongeveer {heat} W meer per graad kouder dan {base} °C (geleerd uit {days} dagen). De verbruiksvoorspelling houdt rekening met de weersverwachting.",
        "temperature_effect_cool": "Het verbruik volgt de buitentemperatuur: ongeveer {cool} W meer per graad warmer dan 22 °C (geleerd uit {days} dagen). De verbruiksvoorspelling houdt rekening met de weersverwachting.",
        "temperature_no_effect": "Geen invloed van de buitentemperatuur op het verbruik gevonden ({days} dagen); de voorspelling wordt niet aangepast aan het weer.",
        "temperature_learning": "Nog niet genoeg dagen met buitentemperatuur om de invloed op het verbruik te leren (7 nodig).",
        "temperature_zone_effect": "{name} volgt de buitentemperatuur: ongeveer {heat} W meer per graad kouder dan {base} °C en {cool} W meer per graad warmer dan 22 °C (geleerd uit {days} dagen).",
        "temperature_zone_effect_heat": "{name} volgt de buitentemperatuur: ongeveer {heat} W meer per graad kouder dan {base} °C (geleerd uit {days} dagen).",
        "temperature_zone_effect_cool": "{name} volgt de buitentemperatuur: ongeveer {cool} W meer per graad warmer dan 22 °C (geleerd uit {days} dagen).",
        "temperature_zone_no_effect": "Geen invloed van de buitentemperatuur op {name} gevonden ({days} dagen).",
        "temperature_room": "{name}: de kamer is overdag meestal ongeveer {day} °C en 's nachts {night} °C; de voorspelling gaat daarvan uit.",
        "temperature_room_days": "{name}: de kamer is overdag meestal {days} °C, 's nachts ongeveer {night} °C; de voorspelling gaat daarvan uit per dag van de week.",
        "temperature_no_forecast": "De weer-entiteit geeft geen temperatuurverwachting; de verbruiksvoorspelling wordt niet aangepast aan het weer.",
        "forecast_adjusted": "Verbruiksvoorspelling aangepast: {name} ({change}) van {start} tot {end}.",
        "forecast_adjustments_cleared": "{count} aanpassing(en) van de verbruiksvoorspelling verwijderd.",
        "correction_consumption": "De verbruiksvoorspelling wordt nu gecorrigeerd met {correction} ({mode}, {samples} vergelijkingen), omdat hij systematisch afweek.",
        "correction_pv": "De PV-voorspelling wordt nu gecorrigeerd met {correction} ({mode}, {samples} vergelijkingen): de gemeten opwek week systematisch af van de voorspelling.",
        "correction_price": "Voorspelde prijzen worden nu gecorrigeerd met {correction} ({mode}, {samples} vergelijkingen) ten opzichte van de later gepubliceerde prijzen.",
        "correction_none": "De {kind} wordt niet meer gecorrigeerd ({mode}).",
        "correction_mode_learned": "De {kind} wordt weer gecorrigeerd op basis van de meelopende nauwkeurigheid.",
        "correction_mode_off": "Correctie van de {kind} uitgeschakeld{until}; de nauwkeurigheid wordt wel gemeten.",
        "correction_mode_manual": "Handmatige correctie van de {kind}: {value}{until}.",
        "accuracy_reset": "Wat geleerd was over de {kind} is gewist.",
        "battery_plan": "Batterijplan ({mode}): verwachte besparing {saving} in het planningsvenster (andere modi: {others}). Laden: {charge}. Ontladen: {discharge}. Alleen advies, er wordt niets aangestuurd.",
        "battery_plan_prices": "Batterijplan ({mode}): verwachte besparing {saving} in het planningsvenster (andere modi: {others}). Laden: {charge} tegen gem. {charge_price}. Ontladen: {discharge} tegen gem. {discharge_price}. Prijsverschil {spread}, {net_spread} na verlies en slijtage. Alleen advies, er wordt niets aangestuurd.",
        "plan_mode_set": "Modus batterijplan ingesteld op {mode}.",
        "battery_plan_story": "{text}",
        "full_charge_planned": "{name} moet vóór {deadline} weer eens helemaal vol (laatste keer: {last}). Dat gebeurt {start} tot {end}, het goedkoopste moment ({price} per kWh, gemiddeld {avg_price}).",
        "full_charge_overdue": "{name} moet nodig weer eens helemaal vol (laatste keer: {last}). Dat gebeurt {start} tot {end}, het goedkoopste moment van de komende {days} dagen ({price} per kWh, gemiddeld {avg_price}).",
        "battery_switch": "{new} neemt het {action} over van {old} om de batterijen in balans te houden (vulling {new_soc}% tegen {old_soc}%).",
        "phase_limit": "{names} samen teruggeschroefd naar {power}: fase {phase} voert {current} A van maximaal {max} A (hoofdzekering, met {margin}% marge).",
        "phase_limit_cleared": "De fasen hebben weer ruimte: de virtuele batterijen worden niet meer beperkt door de hoofdzekering.",
        "prices_updated": "Nieuwe prijzen gepubliceerd, nu tot {end} ({hours} uur extra); de plannen zijn opnieuw berekend.",
        "phase_relief": "Fasebeveiliging: fase {phase} voert {current} A, boven de grens van {limit} A. {names} gaat {power} {action} om de fase te ontlasten.",
        "phase_relief_ended": "Fase {phase} is weer onder de grens. {names} ontlastte de fase {minutes} min, met in totaal {energy} kWh.",
        "peak_shaving": "Piekafvlakking: het net zou {grid} leveren, boven de piekgrens van {limit}. {names} vangen daarvan {power} op.",
        "peak_shaving_ended": "De netafname is weer onder de piekgrens. De batterijen vlakten de piek {minutes} min af, met in totaal {energy} kWh.",
    },
}


def _format(value: Any) -> str:
    if isinstance(value, datetime):
        return dt_util.as_local(value).strftime("%d-%m %H:%M")
    return str(value)


KIND_NAMES: dict[str, dict[str, str]] = {
    "en": {
        "consumption": "consumption forecast",
        "pv": "solar forecast",
        "price": "price forecast",
    },
    "nl": {
        "consumption": "verbruiksvoorspelling",
        "pv": "zonnevoorspelling",
        "price": "prijsvoorspelling",
    },
}


# Phrases filled into a message: a parameter value "@<term>" is replaced by
# the term in the message's language, itself filled from the other parameters.
TERMS: dict[str, dict[str, str]] = {
    "en": {
        "none": "",
        "src_pv": "solar power that would otherwise go to the grid",
        "src_grid": "power from the grid",
        "src_mixed": "solar power and power from the grid",
        "also_export": " and the grid",
        "until_none": "",
        "until_set": " (until {time})",
        "until_empty": ", expected until about {time}, when it is empty",
        "until_full": ", expected until about {time}, when it is full",
        "until_pv_end": ", expected until about {time}, when the solar surplus ends",
        "until_pv_covers": ", expected until about {time}, when solar power covers the house again",
        "until_other": ", expected until about {time}",
        "until_resume_charging": ", expected until about {time}, when it charges again",
        "until_resume_supplying": ", expected until about {time}, when it supplies the house again",
        "idle_none": "Now it is idle",
        "idle_grid": "Now it is idle and the house runs on the grid",
        "idle_export": "Now it is idle and the solar surplus goes to the grid",
        "idle_pv": "Now it is idle and solar power covers the house",
        "now_none": "",
        "now_full": " (it is full)",
        "now_empty": " (it is empty)",
        "now_idle_none": "",
        "now_idle_grid": "; the house runs on the grid",
        "now_idle_export": "; the solar surplus goes to the grid",
        "now_idle_pv": "; solar power covers the house",
        "stop_none": "",
        "stop_full": " — it is full",
        "stop_empty": " — it is empty (set lower limit)",
        "plan_none": "",
        "plan_same": " That matches the plan.",
        "plan_charge": " The plan said: charge now. The battery follows its own control; HomeBatteryAssist only advises.",
        "plan_discharge": " The plan said: supply now. The battery follows its own control; HomeBatteryAssist only advises.",
        "plan_idle": " The plan said: neither charge nor supply now. The battery follows its own control; HomeBatteryAssist only advises.",
    },
    "nl": {
        "none": "",
        "src_pv": "zonnestroom die anders naar het net zou gaan",
        "src_grid": "stroom uit het net",
        "src_mixed": "zonnestroom en stroom uit het net",
        "also_export": " en aan het net",
        "until_none": "",
        "until_set": " (tot {time})",
        "until_empty": ", naar verwachting tot ongeveer {time}, dan is hij leeg",
        "until_full": ", naar verwachting tot ongeveer {time}, dan is hij vol",
        "until_pv_end": ", naar verwachting tot ongeveer {time}, dan is er geen zonne-overschot meer",
        "until_pv_covers": ", naar verwachting tot ongeveer {time}, dan dekt zonnestroom het verbruik weer",
        "until_other": ", naar verwachting tot ongeveer {time}",
        "until_resume_charging": ", naar verwachting tot ongeveer {time}, dan gaat hij weer laden",
        "until_resume_supplying": ", naar verwachting tot ongeveer {time}, dan gaat hij weer leveren",
        "idle_none": "Nu doet hij niets",
        "idle_grid": "Nu doet hij niets en komt de stroom voor het huis van het net",
        "idle_export": "Nu doet hij niets en gaat het zonne-overschot naar het net",
        "idle_pv": "Nu doet hij niets en dekt zonnestroom het verbruik van het huis",
        "now_none": "",
        "now_full": " (hij is vol)",
        "now_empty": " (hij is leeg)",
        "now_idle_none": "",
        "now_idle_grid": "; de stroom voor het huis komt van het net",
        "now_idle_export": "; het zonne-overschot gaat naar het net",
        "now_idle_pv": "; zonnestroom dekt het verbruik van het huis",
        "stop_none": "",
        "stop_full": " — hij is vol",
        "stop_empty": " — hij is leeg (ingestelde ondergrens)",
        "plan_none": "",
        "plan_same": " Dat klopt met het plan.",
        "plan_charge": " Het plan zei: nu laden. De batterij volgt haar eigen sturing; HomeBatteryAssist geeft alleen advies.",
        "plan_discharge": " Het plan zei: nu leveren. De batterij volgt haar eigen sturing; HomeBatteryAssist geeft alleen advies.",
        "plan_idle": " Het plan zei: nu niet laden of leveren. De batterij volgt haar eigen sturing; HomeBatteryAssist geeft alleen advies.",
    },
}


def render(language: str | None, key: str, params: dict[str, Any]) -> str:
    """Return the explanation for ``key`` in ``language`` (fallback English)."""
    lang = (language or DEFAULT_LANGUAGE).split("-")[0].lower()
    templates = MESSAGES.get(lang, MESSAGES[DEFAULT_LANGUAGE])
    template = templates.get(key) or MESSAGES[DEFAULT_LANGUAGE].get(key)
    if template is None:
        return key
    if "kind" in params:
        # Forecast kinds by name in the user's language.
        names = KIND_NAMES.get(lang, KIND_NAMES[DEFAULT_LANGUAGE])
        params = {**params, "kind": names.get(params["kind"], params["kind"])}
    terms = TERMS.get(lang, TERMS[DEFAULT_LANGUAGE])
    plain = {
        k: _format(v)
        for k, v in params.items()
        if not (isinstance(v, str) and v.startswith("@"))
    }
    filled = dict(params)
    for name, value in params.items():
        if isinstance(value, str) and value.startswith("@"):
            term = terms.get(value[1:], TERMS[DEFAULT_LANGUAGE].get(value[1:], ""))
            try:
                filled[name] = term.format(**plain)
            except (KeyError, IndexError):
                filled[name] = term
    params = filled
    try:
        return template.format(**{k: _format(v) for k, v in params.items()})
    except (KeyError, IndexError):
        return template
