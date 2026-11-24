---
description: "Maak HomeBatteryAssist van jezelf: planners, verbruiksvoorspellers, tarieven, PV-correcties en piekfilters als modules."
---

# Modules: maak HomeBatteryAssist van jezelf {#modules-make-homebatteryassist-your-own}

De verwisselbare onderdelen van de lagen van HomeBatteryAssist zijn *modules* (apparaten zijn [drivers](drivers.md); zie [Architectuur](architecture.md)). Je kiest uit de ingebouwde modules, en gevorderde gebruikers kunnen hun eigen modules toevoegen zonder de integratie aan te passen. Er zijn nu acht soorten waarvan je eigen modules kunt toevoegen:

| Soort | Wat het doet | Ingebouwd | Eigen modules in | Kiezen in de instellingen |
|---|---|---|---|---|
| **Planner** | Bepaalt per tijdvak hoeveel de batterijen laden of ontladen | Nul op de meter, Arbitrage eigen gebruik, Arbitrage met teruglevering, Tijdvakken, Handmatig | `/config/homebatteryassist/planners/` | Modus batterijplan |
| **Verbruiksvoorspeller** | Voorspelt het huisverbruik per tijdvak | Profiel per weekdag en uur (standaard), Zelfde tijd in de afgelopen weken | `/config/homebatteryassist/forecasters/` | Verbruiksvoorspeller |
| **Tarief** | Maakt van de prijzen van de bron wat een kWh je echt kost en oplevert | Zoals de prijsbron ze geeft (standaard), Marktprijs + opslag + energiebelasting, plus btw (niet getest) | `/config/homebatteryassist/tariffs/` | Tarief |
| **Bron voor PV-voorspelling** | Leest een zonvoorspelling | Integraties voor zonvoorspelling (Forecast.Solar, Solcast, …) | `/config/homebatteryassist/pv_forecasts/` | PV-voorspelling |
| **PV-correctie** | Past de PV-voorspelling aan met wat is geleerd van eerdere voorspellingen en gemeten PV | Per vooruitzicht, uur en niveau (standaard), Per vooruitzicht (oorspronkelijk) | `/config/homebatteryassist/pv_corrections/` | PV-correctie (sectie *Zonvoorspelling*) |
| **Piekfilter** | Herkent korte verbruikspieken terwijl ze gebeuren | Korte pieken boven een drempel | `/config/homebatteryassist/spike_filters/` | Piekfilter (sectie *Korte pieken*) |
| **Weerbron** | Leest de buitentemperatuur nu en de verwachting per uur | Weer-entiteit, KNMI-integratie, Weerlive, Open-Meteo, Open-Meteo KNMI-model | `/config/homebatteryassist/weather_sources/` | Weerbron (sectie *Weer en buitentemperatuur*) |
| **Onderschepper** | Jouw laatste woord per batterij voordat een opdracht de deur uit gaat: goedkeuren, beperken, tegenhouden of vrijgeven | Geen (alles zoals voorgesteld) | `/config/homebatteryassist/interceptors/` | Onderschepper (sectie *Planning*) |

De ingebouwde modules zitten in de integratie en worden mee bijgewerkt; je eigen modules staan in hun eigen map onder `/config`, dus een update komt er nooit aan.

De **prijsbronnen** (`engine/sources/prices/`: [DynTarNL](https://github.com/mvanrijnen/ha-dyntarNL) (geverifieerd), Nord Pool, EnergyZero, easyEnergy, ENTSO-e, EPEX Spot, Frank Energie, Zonneplan, Amber Electric, PVPC, Essent, Pure Energie, een bloktarief (`block_tariff.py`, vaste prijzen per tijdsblok uit een instelling), of elke sensor met prijzen in zijn attributen) zijn ook modules; nieuwe worden voorlopig aan de code toegevoegd (`template.py`). Bronnen die nog in ontwikkeling zijn (bijv. Tibber) staan apart in `in_development/` en worden niet aangeboden. Naast de prijsbron kun je een **extra prijsvoorspelling** kiezen die de marktprijs dagen vooruit voorspelt (`price_forecasts.py`): EpexPredictor en stroomprijsprognose.nl (beide geverifieerd), of de sensoren van Energy Price Forecast EU, WattWanneer, Wattcast en EnerPrice (niet getest). Die wordt eerst op het niveau van de prijsbron gebracht en alleen gebruikt na de prijzen van die bron; de gepubliceerde prijzen blijven van de prijsbron komen.

## HomeBatteryAssist houdt het laatste woord {#homebatteryassist-keeps-the-final-say}

Wat een module ook teruggeeft, HomeBatteryAssist controleert het voordat het wordt gebruikt:

- **Planner**: elk gevraagd vermogen wordt teruggebracht tot wat de batterijen en de fasen toelaten, tot het minimale/maximale laadniveau en tot je prijsregels (niet ontladen onder de minimale ontlaadprijs, niet uit het net laden boven de maximale laadprijs — behalve vaste acties die je zelf instelt, zoals handmatig of tijdvakken). **Daarna worden de periodieke volladingen ingevoegd.** Een planner kan niets plannen wat de batterijen of de netaansluiting niet kunnen.
- **Verbruiksvoorspeller**: een ontbrekende, negatieve of absurde waarde wordt vervangen door de voorspelling van het ingebouwde profiel. De temperatuurstap (optioneel), de geleerde (of handmatige) correctie en je eigen aanpassingen worden daarna toegepast.
- **Tarief**: een ontbrekende of absurde prijs (meer dan 10 per kWh, naar boven of naar beneden) wordt vervangen door de prijs die de bron gaf. De nauwkeurigheid van de prijs*voorspelling* wordt nog steeds op de prijzen van de bron gemeten.
- **Bron voor PV-voorspelling**: negatieve, niet-eindige of absurde waarden en uren zonder tijdzone vallen weg. De PV-correctie en de veiligheidsmarge worden daarna toegepast.
- **Piekfilter**: het deel van het verbruik waarvoor niet wordt ontladen blijft tussen 0 en het verbruik, de energie van een piek tussen 0 en 5 kWh; al het andere telt als geen piek. Een falend filter wordt uitgeschakeld tot het volgende herladen (*Waarom* meldt dat). Regelmatige pieken tellen altijd als normaal verbruik, wat het filter ook zegt.
- **Onderschepper**: die kan alleen onderscheppen — een beperking is hoogstens het voorstel en in dezelfde richting (meer wordt teruggebracht tot het voorstel, de andere richting tot 0 W); onbekende batterijen, onbekende acties en onzin tellen als goedgekeurd; een falende onderschepper laat de voorstellen ongewijzigd door (*Waarom* meldt dat één keer). Daarna komt de eigen eindcontrole van HomeBatteryAssist, die altijd wint: fasegrenzen, vermogensgrenzen en het laadniveau.
- **Weerbron**: uren zonder tijdzone en temperaturen die niet geloofwaardig zijn (buiten −60…60 °C) vallen weg; een falende bron telt als geen voorspelling (de verbruiksvoorspelling wordt dan niet aangepast aan het weer).
- **PV-correctie**: een ontbrekende, negatieve, niet-eindige of absurde waarde (meer dan 3 × de voorspelling + 100 Wh) wordt vervangen door de correctie per vooruitzicht. De nauwkeurigheid wordt altijd op de *ruwe* voorspelling geleerd, zodat een correctie nooit op zichzelf terugkoppelt. Als de correctie met de hand is ingesteld of uitgeschakeld (actie `set_forecast_correction`), wordt alleen de correctie per vooruitzicht gebruikt, zoals ingesteld.

Als een gekozen module faalt, meldt de uitleg (*Waarom*) dat één keer, staan de details in het logboek, en wordt de ingebouwde terugvaloptie gebruikt: nul op de meter voor een planner, het profiel voor een voorspeller, de prijzen van de bron voor een tarief. Het overzicht van het dashboard laat zien welke planner, voorspeller en welk tarief actief zijn, en markeert een terugval.

Modules praten nooit met een apparaat. Met *Besturing aan* bepalen de gebruikte planningsmodule (*Nul op de meter* of *Arbitrage*) en de onderschepper wat de aangestuurde batterijen doen, altijd via de eindcontrole van HomeBatteryAssist en de controller van elke batterij ([beveiligingslagen](architecture.md#safety-layers)); anders is alles advies.

## Vergelijken {#comparing}

- **Planners**: elke planner, ook je eigen, wordt elke cyclus berekend; het dashboard vergelijkt hun verwachte besparing met geen batterij.
- **Verbruiksvoorspellers**: elke voorspeller draait elke cyclus en zijn eigen nauwkeurigheid (vóór correcties) wordt per vooruitzicht bijgehouden. Het tabblad *Nauwkeurigheid* zet ze naast elkaar, de beste vetgedrukt — zo zie je na een week welke voorspeller bij je huis past, en stap je over.
- **Piekfilters**: de diagnostiek laat zien wat het gekozen filter zag (pieken, hun energie) en de uren met regelmatige pieken.
- **PV-correcties**: elke correctie draait elke cyclus en de PV-voorspelling erna wordt per vooruitzicht vergeleken met de gemeten PV. Het tabblad *Nauwkeurigheid* zet ze naast elkaar, met de ongecorrigeerde voorspelling ter vergelijking.

## Zelf maken {#making-your-own}

1. Maak de map van de soort aan (bijv. `/config/homebatteryassist/forecasters/`), bijvoorbeeld met de File editor.
2. Kopieer de `template.py` van de soort uit de integratie daarheen onder een eigen naam — of kopieer een ingebouwde module om daarvan uit te gaan:

   | Soort | Sjabloon en ingebouwde modules |
   |---|---|
   | Planner | `engine/planning/planners/template.py` (laden in de goedkoopste uren); `zero_on_meter.py`, `arbitrage.py` |
   | Verbruiksvoorspeller | `engine/forecast/forecasters/template.py` (gemiddelde van de laatste dag); `weekday_hour_profile.py`, `same_time_last_weeks.py` |
   | Tarief | `engine/sources/tariffs/template.py` (een dynamisch contract op basis van de marktprijs — vul je eigen getallen in); `as_price_source.py`, `market_plus_costs.py` |
   | Bron voor PV-voorspelling | `engine/sources/pv_forecasts/template.py` (een sensor met een attribuut `wh_hours`); `solar_forecast_integrations.py` |
   | PV-correctie | `engine/evaluation/pv_corrections/template.py` (minder in de ochtend, bijv. door een boom); `hour_and_level.py`, `lead_time.py` |
   | Piekfilter | `engine/measure/spike_filters/template.py` (overdag nooit ontladen boven een niveau); `short_peaks.py` |
   | Weerbron | `engine/sources/weather/template.py` (een sensor plus dagwaarden); `ha_weather_entity.py`, `knmi_integration.py`, `weerlive_api.py`, `open_meteo.py` |
   | Onderschepper | `engine/control/interceptors/template.py` (een koude batterij niet ontladen, niet uit het net laden terwijl een groot apparaat draait, hoogstens 1500 W); `pass_through.py` |

3. Geef de klasse een eigen `key` en `name`. Verander in een gekopieerde ingebouwde module de relatieve imports (`from .base import ...`) in absolute (`from custom_components.homebatteryassist.<package>.base import ...`), zoals in de sjablonen.
4. Herlaad HomeBatteryAssist (Instellingen → Apparaten & diensten → HomeBatteryAssist → ⋮ → Herladen). Je module verschijnt in de instellingen als `custom_<key>`, met **(niet getest)** erachter tot je `verified = True` in de klasse zet — doe dat pas nadat je hem op je eigen installatie hebt getest.

Een bestand waarvan de naam met `_` begint wordt genegeerd; een bestand dat niet laadt wordt overgeslagen en gelogd. Herlaad opnieuw nadat je een bestand hebt gewijzigd.

> [!CAUTION]
> Modulebestanden zijn Python-code die binnen Home Assistant draait. Gebruik alleen bestanden die je zelf hebt geschreven of vertrouwt.

## De interfaces {#the-interfaces}

Elke soort heeft een `base.py` in zijn package met de volledige interface en documentatie. In het kort:

### Planner — `engine/planning/planners/base.py` {#planner--engineplanningplannersbasepy}

```python
class Planner:
    key = "my_plan"
    name = "My plan"

    def plan(self, data: PlannerInput) -> PlannerResult | list[float]: ...
```

`data.slots` (per tijdvak: `start`, `end`, `hours`, `house_w`, `pv_w`, `net_w`, `price`, `export_price`, `max_charge_w`, `max_discharge_w`), `data.battery` (alle batterijen als één: `capacity_wh`, `stored_wh`, `floor_wh`, `ceiling_wh`, `efficiency`; `members` = de batterijen apart als er meer zijn), `data.forced` (extra laadvermogen in W per tijdvakstart dat moet gebeuren: het periodiek volladen), `data.rules` (je planregels), `data.cycle_cost`, `data.peak_w`, `data.priced`. Geef het gevraagde vermogen per tijdvak terug in W (+ laden, − ontladen). De eindcontrole verdeelt het over de batterijen (een volle batterij neemt niets meer op, een lege geeft niets) en voegt het volladen toe. Draait buiten de event loop; geen I/O.

### Verbruiksvoorspeller — `engine/forecast/forecasters/base.py` {#consumption-forecaster--engineforecastforecastersbasepy}

```python
class Forecaster:
    key = "my_forecast"
    name = "My forecast"

    def forecast(
        self, data: ForecasterInput
    ) -> ForecasterResult | list[float | None]: ...
```

`data.history` (de verbruiksrecords: `start`, `minutes`, `avg_w`, `coverage`, optioneel `pv_w`, `excluded_w`, `battery_w`, `vacation`, `heating_w` (apparaten voor verwarming/koeling, deel van `avg_w`), `temp_c` (buitentemperatuur) en `zones` (per apparaat voor verwarming/koeling: `w`, en als ze gemeten worden `in` = kamer- en `out` = eigen buitentemperatuur)), `data.slots` (start, eind), `data.now`, `data.interval`, en `data.temperatures` (de verwachte buitentemperatuur per tijdvak in °C, None waar onbekend; None zonder weerbron). Geef het verwachte verbruik per tijdvak terug in W, of None waar je geen idee hebt. Snel, geen I/O.

De optionele [temperatuurstap](forecasting.md#outdoor-temperature-optional) wordt daarna bij je resultaat opgeteld; zet `uses_temperature = True` op je klasse als je voorspeller de temperatuur al meeneemt.

### Tarief — `engine/sources/tariffs/base.py` {#tariff--enginesourcestariffsbasepy}

```python
class Tariff:
    key = "my_contract"
    name = "My contract"
    needs_market = True

    def prices(self, data: TariffInput) -> TariffResult: ...
```

`data.slots` (per periode: `price` van de bron, `market` (EPEX, met `needs_market` en als de bron die aanbiedt), `export` volgens de terugleverinstellingen, `estimated`). Geef de afname- en terugleverprijs per periode terug (None = die van de bron houden). Snel, geen I/O.

### Bron voor PV-voorspelling — `engine/sources/pv_forecasts/base.py` {#pv-forecast-source--enginesourcespv_forecastsbasepy}

```python
class PvForecastSource:
    key = "my_pv"
    name = "My PV forecast"

    async def async_find(self, hass) -> list[PvForecastOption]: ...
    async def async_read(self, hass, option_id) -> dict[datetime, float]: ...
```

`async_find` somt de voorspellingen op die de bron aanbiedt (te zien in de instellingen); `async_read` geeft er één terug als Wh per klokuur (uurbegin met tijdzone). Alleen lezen — stuur nooit een apparaat aan; gebruik de gedeelde HTTP-sessie van Home Assistant voor webdiensten en cache, want de voorspelling wordt elke cyclus gelezen.

### Onderschepper — `engine/control/interceptors/base.py` {#interceptor--enginecontrolinterceptorsbasepy}

```python
class Interceptor:
    key = "my_rules"
    name = "My rules"

    def intercept(self, data: InterceptInput) -> InterceptResult: ...
```

Wordt elke ronde van de batterijen aangeroepen (standaard elke 5 s, direct bij een grote sprong of overbelasting) met het voorstel van HomeBatteryAssist. `data.batteries` bevat per batterij de naam, fase, het laadniveau, het vermogen nu, de temperatuur, capaciteit en grenzen, of er een vollading loopt, het voorgestelde vermogen (`proposed_w`, + laden / − ontladen) en waarom (`reason`: `plan`, `zero_on_meter`, `full_charge`, `min_soc_guard`, `phase_relief`, `peak_shaving`); daarnaast het net (netto en per fase, de fasegrens), huis, zon, uitgesloten apparaten, de willekeurige korte piek nu, de planmodus en de komende tijdvakken van het plan (prijzen, terugleverprijzen, gepland vermogen, 8 uur).

Geef `InterceptResult(decisions, redistribute=True)` terug met een `Decision(battery_id, action, power_w, reason)` voor de batterijen die je niet goedkeurt: `REJECT` (0 W, HomeBatteryAssist houdt de regie), `LIMIT` (hoogstens `power_w`, dezelfde richting) of `RELEASE` (terug naar de eigen regeling van de batterij). Met `redistribute` mogen de goedgekeurde batterijen overnemen wat de andere niet meer doen (tot hun grenzen; bij ontladen niet onder `floor_soc`: het minimum, verhoogd met de reserves die gelden). De `reason` verschijnt in *Waarom* en op het overzicht. Snel, geen I/O. De onderschepper werkt op de virtuele batterijen en, met *Besturing aan*, in dezelfde ronde op de aangestuurde echte batterijen, zodat je met de besturing uit eerst ziet wat hij zou doen.

### Weerbron — `engine/sources/weather/base.py` {#weather-source--enginesourcesweatherbasepy}

```python
class WeatherSource:
    key = "my_weather"
    name = "My weather"
    settings: WeatherSettings  # entity_id, api_key, location (what the user set)

    def temperature_now(self, hass) -> float | None: ...
    async def async_forecast(self, hass) -> dict[datetime, float]: ...
    def describe(self) -> str: ...  # optional: what it reads (diagnostics)
```

`async_forecast` geeft °C per uur terug (uurbegin met tijdzone) zo ver vooruit als hij kan, en wordt elke cyclus aangeroepen: cache dus (de ingebouwde vragen een webdienst elke 30 minuten). `daily_curve` en `combine` in `base.py` maken van minimum-/maximumtemperaturen per dag uren na een uurverwachting. Alleen lezen; gebruik de gedeelde HTTP-sessie van Home Assistant.

### Piekfilter — `engine/measure/spike_filters/base.py` {#spike-filter--enginemeasurespike_filtersbasepy}

```python
class SpikeFilter:
    key = "my_filter"
    name = "My spike filter"
    threshold_w: float  # from the settings
    max_duration_s: float  # from the settings

    def update(self, when, house_w) -> SpikeState: ...
    def details(self) -> dict: ...  # optional: what it saw (diagnostics)
```

`update` krijgt elke nieuwe waarde van het huisverbruik (W, None = onbekend; ongeveer elke 1 tot 10 s) en houdt zijn eigen toestand bij; bij elke start wordt een nieuwe instantie gemaakt. Geef `SpikeState(ignore_w, ended_wh)` terug: het deel van het verbruik nu dat een piek is (daarvoor wordt niet ontladen), en één keer, als een piek voorbij is, de energie ervan (die niet meetelt in het gemiddelde). Snel, geen I/O.

### PV-correctie — `engine/evaluation/pv_corrections/base.py` {#pv-correction--engineevaluationpv_correctionsbasepy}

```python
class PvCorrector:
    key = "my_correction"
    name = "My PV correction"

    def correct(self, data: PvCorrectionInput) -> list[float | None]: ...
    def details(self) -> dict: ...  # optional: what was learned (diagnostics)
```

`data.slots` (UTC-uurbegin, ruwe voorspelling in Wh), `data.results` (de afgelopen weken per uur: `start`, `actual` gemeten Wh en `predictions` = ruwe voorspelling in Wh per vooruitzichtsklasse `0-1h` … `5d+`), `data.lead_factor(start)` (de ingebouwde factor per vooruitzicht voor een tijdvak) en `data.bucket_factors`, `data.now`. Geef de gecorrigeerde Wh per tijdvak terug, of None om de correctie per vooruitzicht te gebruiken. Snel, geen I/O. De correctie wordt gebruikt als *Correctie zonvoorspelling* op automatisch staat (of op automatisch en vaste marge); de vaste marge komt daarna.
