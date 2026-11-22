---
description: "Wat HomeBatteryAssist nodig heeft als invoer: netmeter, batterijen, prijzen (DynTarNL afname-, markt- en terugleverprijzen, tarief), PV-voorspelling, weer en historie."
---

# Invoer: wat HomeBatteryAssist nodig heeft {#inputs-what-homebatteryassist-needs}

HomeBatteryAssist maakt **zelf geen voorspellingen**: het leest metingen en voorspellingen uit andere integraties en combineert die. Deze pagina zet alle invoer op één plek: waarvoor ze dient, of ze nodig is, waar ze vandaan komt en wat er gebeurt zonder.

## In één oogopslag {#at-a-glance}

| Invoer | Nodig voor | Verplicht? | Gebruikelijke bron |
|---|---|---|---|
| [Netmeter](#grid-meter) | alles (huisverbruik, fasebeveiliging) | **ja** | HomeWizard P1, SMA Home Manager, je eigen sensoren |
| [Batterijen](#batteries) | batterijplannen, tellers, plancontrole | voor plannen | Omnibattery, Marstek Modbus, eigen sensoren, of een virtuele batterij |
| [Afnameprijs](#prices) | arbitrage, kosten en besparing | voor arbitrage | [DynTarNL](#dyntarnl), Nord Pool, EnergyZero, … |
| [Terugleverprijs](#export-price) | waarde van teruggeleverde energie | aanbevolen | de prijsbron, sensoren, of afnameprijs × factor |
| [Marktprijs](#prices) | alleen voor het tarief *markt + kosten* of de terugleverprijs *marktprijs* | soms | de prijsbron |
| [Prijsverlenging](#price-extension) | verder vooruit plannen | optioneel | EpexPredictor, stroomprijsprognose.nl |
| [PV-voorspelling](#pv-forecast) | zon in de plannen, nachtreserve | met zonnepanelen | Forecast.Solar, Solcast |
| [PV-meting](#pv-measurement) | huisverbruik, de PV-correctie leren | met zonnepanelen | sensor van de omvormer of een kWh-meter |
| [Uitgesloten apparaten / verwarming](#excluded-devices-and-heating) | een zuiver verbruiksprofiel | optioneel | laadpaal, sensoren van een warmtepomp |
| [Weer](#weather) | het temperatuureffect op het verbruik | optioneel | weerentiteit, KNMI, Weerlive, Open-Meteo |
| [Historie](#history) | goede voorspellingen vanaf dag één | optioneel (eenmalig) | de statistieken van Home Assistant |

## Netmeter {#grid-meter}

**Verplicht.** Het vermogen per fase (W, + afname / − teruglevering): van een rechtstreeks uitgelezen meter (HomeWizard P1, SMA Home Manager, Shelly, IAMMETER), via de sensoren van zijn integratie, of je eigen sensoren (één sensor met teken, of afname en teruglevering apart). Optioneel per fase: **stroom** (A) en **spanning** (V), en een arbeidsfactor als de meter die stuurt; daarmee werkt de fasebeveiliging op de echte stroom (zie [Stroom per fase](measuring.md#current-per-phase)). Zonder netwaarde is het huisverbruik onbekend en doen de virtuele batterijen niets.

## Batterijen {#batteries}

Per batterij van **haar eigen integratie** (alleen lezen): **laadniveau** (%) en **vermogen** (W, met het teken: + laden of + ontladen, in te stellen in het batterijformulier). Capaciteit, maximaal laad-/ontlaadvermogen, min/max laadniveau en rendement worden ingevuld bij een herkende batterij en kunnen worden aangepast. Zonder batterijen meet en voorspelt HomeBatteryAssist wel, maar maakt het geen batterijplan; een [virtuele batterij](measuring.md#virtual-batteries) heeft helemaal geen integratie nodig.

## Prijzen {#prices}

Een prijsbron geeft tot drie soorten prijzen (rollen), allemaal **per kWh**:

- **afname**: wat een kWh van het net kost, **all-in** (marktprijs + opslag van de leverancier + energiebelasting + btw). Dit gebruiken de plannen.
- **markt**: de kale marktprijs (EPEX). Alleen nodig voor het tarief *Marktprijs + opslag + energiebelasting, plus btw* en voor de terugleverprijs *kale marktprijs*.
- **teruglevering**: wat een teruggeleverde kWh oplevert op jouw contract.

Gepubliceerde en voorspelde (geschatte) prijzen worden allebei gebruikt; schattingen zijn als zodanig gemarkeerd. Arbitrage handelt op een geschatte prijs alleen als dat minstens de *marge voor geschatte prijzen* (standaard 0,02 per kWh) meer oplevert dan handelen bij een gepubliceerde prijs; kosten en besparing gebruiken de prijzen zelf. Het venster van de plannen eindigt waar de prijzen eindigen, en bij het **eerste gat** erin. Zonder prijzen plant arbitrage nul op de meter en worden kosten en besparing niet getoond.

Eenheden worden omgerekend naar de hoofdvaluta per kWh (ct/kWh, EUR/MWh, öre/kWh, …); een bron zonder eenheid geldt als per kWh.

### DynTarNL (aanbevolen voor Nederland) {#dyntarnl}

[DynTarNL](https://github.com/mvanrijnen/ha-dyntarNL) geeft alle drie de rollen plus een voorspelling van ongeveer 7 dagen. HomeBatteryAssist vindt de sensoren zelf (per DynTarNL-item):

| DynTarNL-sensor (unique id eindigt op) | Attribuut | Gebruikt als |
|---|---|---|
| `_electricity_forecast_total_avg_24h` | `prices` (`[tijd, all-in prijs, "p"/"f"]`: gepubliceerd, dan voorspeld) | **afname** |
| | `forecast_market` | markt (voorspeld deel) |
| | `forecast_export` (DynTarNL ≥ 1.2.0, voorspellingen aan) | teruglevering (voorspeld deel) |
| `_electricity_market_market_current` | `prices` (gepubliceerde marktprijzen) | **markt** |
| | `purchase_fee` | teruglevering bij DynTarNL < 1.2.0 (markt − inkoopvergoeding) |
| `_electricity_feedin_compensation_now` (DynTarNL ≥ 1.2.0) | `prices` (gepubliceerde terugleverprijzen, kunnen negatief zijn) | **teruglevering** |

Instellingen met DynTarNL:

1. **Prijsbron**: *DynTarNL: ⟨jouw item⟩*.
2. **Tarief**: *Zoals de prijsbron en de terugleverinstellingen ze geven*. De afnameprijzen van DynTarNL zijn al all-in, dus een ander tarief zou de kosten dubbel tellen.
3. **Terugleverprijs**: *Terugleverprijs van de prijsbron of sensor(en)*, zonder terugleverprijs-sensoren. Dat is de marktprijs min de inkoopvergoeding van je leverancier, gelijk aan wat je contract betaalt. Gebruik DynTarNL ≥ 1.2.0 met de voorspellingen aan, zodat de terugleverprijs even ver reikt als de afnameprijs.
4. **Extra prijsvoorspelling**: niet nodig; DynTarNL reikt al ongeveer 7 dagen vooruit.
5. **Planningshorizon** (1–7 dagen): de plannen reiken nooit verder dan de prijzen.

### Andere prijsbronnen {#other-price-sources}

- **Nord Pool, EnergyZero, easyEnergy** (niet getest) geven de **kale marktprijs**. Kies het tarief *Marktprijs + opslag + energiebelasting, plus btw* en vul de opslag van je leverancier, de energiebelasting (beide per kWh, excl. btw) en de btw in. Anders ziet arbitrage een rondje laden en ontladen als te goedkoop.
- **Prijssensor**: elke sensor met een prijslijst in zijn attributen (`prices`, `prices_today`/`prices_tomorrow`, `raw_today`/`raw_tomorrow`, `today`/`tomorrow`, …; voor marktprijzen `forecast_market`, `prices_market`, …). Elk item heeft een begin (`start`, `from`, `time`, …) en een prijs nodig; een item zonder einde loopt tot het volgende.

### Prijsverlenging {#price-extension}

Optioneel: een tweede bron die verder vooruit reikt, gebruikt **na** de laatste prijs van de prijsbron en altijd als geschat geteld (EpexPredictor, stroomprijsprognose.nl, of een andere driver). Een bron met alleen marktprijzen wordt eerst op het niveau van je afnameprijzen gebracht (gekalibreerd op de overlap).

### Terugleverprijs {#export-price}

Wat teruggeleverde energie oplevert. Er wordt uitgegaan van **geen salderen** (dat stopt in Nederland op 1 januari 2027): een teruggeleverde kWh levert alleen de terugleverprijs op. De instelling *Terugleverprijs* heeft drie keuzes:

- **Terugleverprijs van de prijsbron of sensor(en)**: zonder *terugleverprijs-sensoren* van de prijsbron als die een terugleverprijs heeft (DynTarNL: markt − inkoopvergoeding; aanbevolen op een dynamisch contract); met die sensoren van die sensoren (bij overlappende perioden wint de eerste).
- **Kale marktprijs (EPEX)** (standaard): van de prijsbron, of van de gekozen sensoren.
- **Inkoopprijs x factor** (factor *Vergoeding teruglevering*, standaard 0,25; 1,0 = salderen). De factor geldt ook waar de gekozen bron geen prijs geeft.

## PV-voorspelling {#pv-forecast}

Van elke integratie die de **zonnevoorspelling van het Energie-dashboard** ondersteunt (Forecast.Solar, Solcast, …). Meerdere (bijvoorbeeld één per dakvlak) worden opgeteld. Per uur in Wh. Ze wordt gebruikt in de plannen, voor de nachtreserve (nacht = buiten het eerste tot het laatste zonne-uur van een dag), en ze begrenst het planningsvenster. Ze wordt gecorrigeerd met wat je panelen echt deden (geleerd), met een vaste marge, beide, of niet ([PV-correctie](forecasting.md#pv-correction)). Zonder PV-voorspelling is er geen nachtreserve (wanneer de zon opkomt is dan onbekend) en rekenen de plannen met geen zon.

## PV-meting {#pv-measurement}

Per PV-bron (een sub-item): een vermogenssensor van de omvormer of een kWh-meter op zijn lijn. Nodig voor het huisverbruik (`huis = net + PV − uitgesloten − batterijen`) en om de PV-correctie te leren. Zonder, met zonnepanelen, is het huisverbruik in de zon te laag.

## Uitgesloten apparaten en verwarming {#excluded-devices-and-heating}

Optionele sub-items. **Uitgesloten apparaten** (een laadpaal, een groot verbruik dat je zelf plant) blijven buiten het huisverbruik en de voorspelling, en de batterijen ontladen er nooit voor. **Verwarming/koeling**-zones (warmtepomp, airco) blijven deel van het huis, maar worden apart vastgelegd voor het temperatuureffect.

## Weer {#weather}

Optioneel. Een **voorspelling van de buitentemperatuur** (weerentiteit, KNMI, Weerlive met een gratis API-sleutel, of Open-Meteo), eventueel met een buitentemperatuursensor. Daarmee leert de verbruiksvoorspelling hoeveel W per graad het huis gebruikt voor verwarming of koeling. Zonder heeft de temperatuur geen effect.

## Historie {#history}

Optioneel, eenmalig: de actie **Verbruikshistorie importeren** vult de historie (tot 28 dagen) uit de statistieken van Home Assistant van de sensoren hierboven. Dan zijn de voorspellingen vanaf dag één goed. Een periode zonder statistieken van het net, een batterij of een uitgesloten apparaat wordt overgeslagen. Zonder import leert HomeBatteryAssist vanaf het moment van installeren.
