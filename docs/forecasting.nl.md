---
description: "Voorspellingen van huisverbruik, zonne-energie (Solcast, Forecast.Solar) en dynamische energieprijzen voor thuisbatterijen in Home Assistant, achteraf gecontroleerd en gecorrigeerd."
---

# Voorspellen {#forecasting}

HomeBatteryAssist voorspelt het verbruik zelf, maar haalt prijzen en zonvoorspellingen uit de integraties die je al hebt — en controleert elke voorspelling achteraf met wat er echt gebeurde.

## Planningsvenster {#planning-window}

Elke voorspelling bepaalt eerst hoe ver vooruit hij kan rekenen: begrensd door je instelling (1–7 dagen) en door hoe ver de prijs- en zonvoorspellingen reiken. Voorbij dat venster wordt niets berekend.

## Verbruik {#consumption}

Het huisverbruik per tijdvak wordt voorspeld door een **verbruiksvoorspeller**-[module](modules.md):

- **Profiel per weekdag en uur** (standaard): het gemiddelde per weekdag en uur uit je eigen geschiedenis, waarbij recente dagen zwaarder tellen; elke dag van de week (maandag … zondag) heeft een eigen profiel — geen splitsing in werkdagen en weekend, want als je thuiswerkt kan een woensdag anders zijn dan een dinsdag; met weinig geschiedenis valt hij terug op het uur van alle dagen, of op het totale gemiddelde.
- **Zelfde tijd in de afgelopen weken**: dezelfde weekdag en tijd in de afgelopen twee weken (elke meting in het tijdvak telt mee). De temperatuurstap vergelijkt de verwachting met het weer van juist die weken.
- **Je eigen voorspeller**, zie [Modules](modules.md).

Alle voorspellers draaien elke ronde; het tabblad *Nauwkeurigheid* vergelijkt ze, zodat je de voorspeller kunt kiezen die bij je huis past. Van verbruik tijdens een **vakantie** (instelling) wordt niet geleerd. Je kunt de voorspelling voor een periode **aanpassen** (bijv. een feestje) met de actie `adjust_forecast`.

**Incidenteel verbruik** (dashboard: knop *Incidenteel verbruik* in de bovenbalk; ook de actie `adjust_forecast` met `energy_kwh`): vertel de voorspelling per dag over verbruik dat hij niet uit de geschiedenis kan weten: een hoeveelheid energie (kWh), optioneel binnen een tijdvenster (zonder venster: verdeeld over de hele dag; een venster dat eindigt vóór het begint loopt over middernacht). Kies:

- **Extra**: bovenop het geleerde verbruik (bijv. gasten, een eenmalige klus, iets groots opladen).
- **Deel van het verwachte verbruik**: het geleerde verbruik van die dag bevat het al, het valt alleen op dat moment (bijv. de wasmachine die elke dag wel eens draait, morgen om 13:00–15:00). Dezelfde energie gaat af van de rest van die dag, naar verhouding van het verwachte verbruik, zodat het dagtotaal gelijk blijft. Dit vraagt een tijdvenster.

Het venster toont ze en voegt ze toe, wijzigt en verwijdert ze; aanpassingen via de actie staan er ook in en kunnen er worden verwijderd. *Waarom* meldt elke wijziging. De voorspelling en de plannen worden één keer herberekend als je het venster sluit, en alleen na een wijziging (anders bij de volgende gewone ronde).

### Buitentemperatuur (optioneel) {#outdoor-temperature-optional}

Een profiel volgt een plotselinge koudegolf pas na dagen. Huizen die elektrisch verwarmen of koelen (warmtepomp, elektrische verwarming, airco) kunnen de voorspelling de **weersverwachting** laten volgen:

1. Kies een **weerbron** in de instellingensectie *Weer en buitentemperatuur*. Daarmee gaat de temperatuurstap aan. De weerbron is een [module](modules.md):
   - **Weer-entiteit** — elke weer-entiteit met een verwachting (Buienradar, Met.no, OpenWeatherMap, KNMI, …), die je eronder kiest.
   - **KNMI-integratie** ([golles/ha-knmi](https://github.com/golles/ha-knmi)) — de weer-entiteit daarvan wordt vanzelf gevonden.
   - **Weerlive** — de KNMI-gegevens van [weerlive.nl](https://weerlive.nl/delen.php) rechtstreeks, zonder integratie. Je hebt een gratis API-sleutel van weerlive.nl nodig (veld *API-sleutel*); maximaal 300 verzoeken per dag voor privégebruik. HomeBatteryAssist vraagt elke 30 minuten (48 per dag); een integratie met dezelfde sleutel (bijv. KNMI) telt mee voor dezelfde limiet.
   - **Open-Meteo** / **Open-Meteo, KNMI-model** — [open-meteo.com](https://open-meteo.com) rechtstreeks, geen sleutel nodig voor niet-commercieel gebruik (gegevens CC BY 4.0, *Weather data by Open-Meteo.com*); per uur voor 7 dagen. Het KNMI-model is HARMONIE voor de eerste dagen, daarna ECMWF.
   - Je eigen module (zie [Modules](modules.md)).

   Weerlive en Open-Meteo gebruiken de **thuislocatie van Home Assistant** (afgerond op ongeveer 1 km); het veld *Plaats* is alleen voor een andere plek (`latitude,longitude`; Weerlive kan ook een plaatsnaam). De verwachting per uur van een weer-entiteit of Weerlive reikt vaak maar 24–48 uur; daarna worden het minimum en maximum per dag omgezet in een verloop per uur (het koudst rond 05:00, het warmst rond 15:00), zodat de verwachting net zo ver reikt als de planning.
2. Optioneel: een **sensor buitentemperatuur** — nauwkeuriger dan de huidige temperatuur van de weerbron, en de geschiedenis ervan in Home Assistant wordt gebruikt om meteen te leren in plaats van na een week. De sensoren van een zone (hieronder) worden ook uit de geschiedenis gevuld, zodat een nieuwe zone meteen wordt geleerd.
3. Optioneel: voeg de warmtepomp of airco toe als **verwarming/koeling**-apparaat (met zijn vermogenssensor). Hij blijft deel van het huisverbruik, maar wordt apart gemeten, wat een zuiverder signaal geeft.
4. Optioneel, per verwarming/koeling-apparaat: de sensor **kamertemperatuur** van de ruimte die het verwarmt of koelt, en een sensor voor de **eigen buitentemperatuur** (bijv. de buitenunit van een airco; zonder die sensor wordt de buitentemperatuur van stap 1–2 gebruikt). Een apparaat met deze sensoren is een **zone**; meerdere apparaten (een airco per kamer) zijn meerdere zones.

Alles is optioneel: zonder weerbron verandert er niets.

**Wat er wordt geleerd.** Elk geschiedenisinterval bewaart de buitentemperatuur (en per zone het vermogen, de kamer- en de buitentemperatuur). Uit hele dagen — dagen in plaats van uren houden het dagritme (koken, slapen) erbuiten — leert HomeBatteryAssist hoeveel W het verbruik stijgt per graad onder het **stookpunt** (verwarmen) en per graad boven 22 °C (koelen, een vaste grens); er zijn minstens 7 dagen met temperatuur nodig, en dagen die nauwelijks verschillen leren niets.

- Het stookpunt is de kamertemperatuur min wat het huis zelf opwarmt (mensen, apparaten, zon). Zonder kamersensor wordt de kamer op 20 °C gezet; de opwarming wordt geleerd (0–8 °C, 4 °C — dus 16 °C buiten — tenzij een andere waarde duidelijk beter bij de dagen past).
- Met een kamersensor wordt ook de **gewenste kamertemperatuur** per uur geleerd (bijv. 21 °C overdag, 17 °C 's nachts), waarbij recente dagen zwaarder tellen (een week geleden telt half, zodat een lagere thermostaat binnen een paar dagen doorwerkt). Dat gebeurt per uur voor de werkdagen samen en het weekend, of per dag van de week (bijv. 22 °C op de donderdagen en vrijdagen dat je thuiswerkt): HomeBatteryAssist kijkt welke van de twee de afgelopen week het best had voorspeld en gebruikt die. De voorspelling gaat daarvan uit: een koude nacht kost minder dan een koude middag als de thermostaat 's nachts lager staat.
- Wat er wordt gefit: per zone het eigen vermogen tegen de eigen temperaturen, de zones bij elkaar opgeteld — zodra elke zone 7 dagen heeft. Tot die tijd, en zonder zones, de verwarming/koeling-apparaten samen, of zonder die apparaten het hele huis.

**Hoe het wordt toegepast.** Per tijdvak telt de stap *W per graad × (voorspelde graden − de gebruikelijke graden op die dag van de week en dat uur, waarbij recente dagen zwaarder tellen)* erbij op: alleen het verschil met het weer dat al in het profiel zit. De stap komt na de voorspeller en vóór de correctie, zodat de nauwkeurigheidscontrole hem meeneemt. Een voorspeller-[module](modules.md) die zelf met temperatuur rekent, zet `uses_temperature = True` en krijgt de verwachting per tijdvak in `temperatures`. Het beslislogboek (*Waarom*) vertelt wat er is geleerd — W per graad, het stookpunt en, met een kamersensor, de kamertemperatuur overdag en 's nachts (per dag van de week als de dagen verschillen); de diagnostiek heeft de details per zone.

**De kamertemperatuur per dagdeel is een samenvatting.** De voorspelling rekent altijd met de geleerde kamertemperatuur *per uur* (van de werkdagen of van die dag van de week), overdag en 's nachts. De getallen *overdag* (07:00–23:00) en *'s nachts* (23:00–07:00) in *Waarom*, de diagnostiek en het dashboard zijn alleen het gemiddelde van die uurwaarden, en verbergen allebei hoe de temperatuur binnen dat dagdeel verloopt: een koele ochtend (18,5 °C) en een warme avond (20,3 °C) geven 19,3 °C overdag, en een nacht die afkoelt van 19,5 naar 18,7 °C geeft ongeveer 19 °C 's nachts — waarden die bij geen enkel uur passen; de voorspelling gebruikt om 10:00 toch 18,5 °C en om 20:00 20,3 °C. Het getoonde stookpunt (de buitentemperatuur waaronder verwarmd wordt) is dat daggemiddelde min de geleerde opwarming van het huis; per uur is het de kamertemperatuur van dat uur min de opwarming.

## Prijzen {#prices}

Uit een prijsbron naar keuze (*prijs-[drivers](drivers.md)*): [DynTarNL](https://github.com/mvanrijnen/ha-dyntarNL) (getest; Nederlandse dynamische tarieven met een prijsvoorspelling voor de komende dagen), Nord Pool, EnergyZero, easyEnergy, ENTSO-e, EPEX Spot, Frank Energie, Zonneplan, of elke sensor met prijzen in zijn attributen; optioneel daarna een extra, langere voorspelling. Geschatte (voorspelde) prijzen zijn als zodanig gemarkeerd. Prijzen worden vanuit de eenheid van de bron omgerekend naar een prijs per kWh in de hoofdmunt (ct/kWh, EUR/MWh, öre/kWh, ...); een bron zonder bekende eenheid geldt als per kWh. Centen zonder eigen munt (c, ct, cent) zijn honderdsten van de valuta van Home Assistant, en bedragen in meldingen en het paneel gebruiken die valuta.

Publiceert een bron prijzen die het plan alleen als schatting had, en wijkt een gepubliceerde prijs minstens 0,08 per kWh én een kwart van de prijs af van de schatting waar het plan mee rekende, dan meldt *Waarom* dat één keer: hoeveel tijdvakken, het grootste verschil (geschat en gepubliceerd) en dat het plan nu met de gepubliceerde prijzen rekent. Zo'n moment verklaart een plotselinge wijziging van het plan (in Nederland bijvoorbeeld rond 13:00 voor de volgende dag).

### Terugleverprijs en geen salderen {#export-price-and-no-net-metering}

Elke berekening (plannen, vergelijkingen en de gerealiseerde waarde van de batterijen) gaat ervan uit dat er **geen salderingsregeling** is (in Nederland stopt die op 1 januari 2027). Afgenomen stroom kost de inkoopprijs; teruggeleverde stroom levert alleen de terugleverprijs op. Laden met zonnestroom kost dus wat die stroom had opgeleverd, en ontladen bespaart alleen de inkoopprijs voor stroom die het huis anders had gekocht.

De terugleverprijs is de kale marktprijs (EPEX, standaard), de terugleverprijs — van de prijsbron als die er een heeft, anders uit een of meer sensoren — of de inkoopprijs × factor (standaard 0,25; 1,0 staat gelijk aan salderen). Bij een dynamisch contract trekt de leverancier voor teruggeleverde stroom meestal een inkoopvergoeding van de marktprijs af (bijv. Essent ongeveer € 0,025/kWh); met DynTarNL als prijsbron geeft *Terugleverprijs van de prijsbron of sensor(en)* precies dat. Vanaf DynTarNL 1.2.0 worden de terugleverprijzen rechtstreeks gelezen — de gepubliceerde uit *export price now* (attribuut `prices`), daarna de voorspelde (`forecast_export`, als de voorspellingen van DynTarNL aan staan) na het laatste gepubliceerde uur; negatieve terugleverprijzen blijven staan (terugleveren kost dan geld). Oudere versies van DynTarNL werken ook: de marktprijs min de inkoopvergoeding die DynTarNL doorgeeft.

### Tarief {#tariff}

Een **tarief**-[module](modules.md) zet deze prijzen om in wat een kWh echt kost en oplevert — bijvoorbeeld voor een contract met terugleverkosten of eigen toeslagen. Het ingebouwde tarief *Zoals de prijsbron ze geeft* gebruikt ze zoals ze zijn. Voor een bron met kale marktprijzen (Nord Pool, EnergyZero, easyEnergy: zonder energiebelasting en opslag) kies je het ingebouwde tarief *Marktprijs + opslag + energiebelasting, plus btw* (niet getest) en vul je de bedragen in onder *Tariefkosten* (in euro per kWh, bijv. 0,0916; voor periodes zonder marktprijs, zoals een langere geschatte voorspelling, is de marktprijs de prijs van de bron min het gebruikelijke verschil tussen die twee, zodat er nooit twee keer btw bij komt); anders ziet arbitrage de verliezen van een rondje laden/ontladen te goedkoop. Het sjabloon laat een dynamisch contract zien dat is opgebouwd uit de marktprijs.

## PV {#pv}

Uit een **zonvoorspellingsbron**-[module](modules.md): standaard elke integratie die de zonvoorspelling van het Energie-dashboard ondersteunt (bijv. Forecast.Solar, Solcast); meerdere voorspellingen (bijv. een per dak) worden opgeteld. Forecast.Solar zet elke hoeveelheid op het eind van haar periode (19:00 = 18:00-19:00); HomeBatteryAssist zet die in het juiste uur. Automatisch gecorrigeerd (geleerd), met een vaste veiligheidsmarge, allebei, of helemaal niet.

### PV-correctie {#pv-correction}

Elk uur wordt de zonvoorspelling vergeleken met de PV die achteraf is gemeten. De automatische correctie is een **PV-correctie**-[module](modules.md), die je kiest in de instellingensectie *Zonvoorspelling*:

- **Per vooruitzicht, uur en niveau** (standaard): de factor per vooruitzicht (hieronder), en daarbovenop wat typisch is voor jouw installatie:
  - **per uur van de dag** — bijv. schaduw in de ochtend of een dak op het westen: de voorspelling is 's ochtends te hoog en 's middags te laag;
  - **per niveau** — hoeveel de voorspelling op dat uur belooft vergeleken met het meeste dat hij de laatste tijd op dat uur beloofde (ongeveer een heldere hemel). Voorspellingen zitten op sombere dagen vaak relatief verder ernaast dan op zonnige; *sombere*, *wisselende* en *zonnige* uren krijgen elk een factor.

  Beide worden geleerd uit de afgelopen weken (recente dagen tellen zwaarder) en tellen minder mee zolang er weinig dagen zijn; de gecombineerde factor blijft tussen 0,3 en 2. Zonder geschiedenis is hij gelijk aan de oorspronkelijke.
- **Per vooruitzicht** (de oorspronkelijke, altijd beschikbaar): één factor per vooruitzicht (0–1 u … 5 dagen+), gemeten / voorspelde energie, tussen 0,5 en 1,5.
- **Je eigen correctie**, zie [Modules](modules.md) — bijv. een aangepaste kopie van een ingebouwde.

Alle correcties worden elke ronde berekend; het tabblad *Nauwkeurigheid* vergelijkt ze met elkaar en met de ongecorrigeerde voorspelling. De diagnostiek laat zien wat de gekozen correctie heeft geleerd (factoren per uur en niveau). Een correctie die met de hand is ingesteld of is uitgezet (actie `set_forecast_correction`) wordt gevolgd zoals ingesteld.

### Onverwacht zonne-overschot of -tekort {#unexpected-solar-surplus-or-shortage}

De correctie werkt achteraf; *Waarom* meldt het ook terwijl het gebeurt. Als er duidelijk meer zonnestroom over is dan voorspeld — het gemeten overschot (PV − huis − uitgesloten apparaten) is minstens 300 W en minder dan de helft ervan was voorspeld voor dit uur (zonvoorspelling, gecorrigeerd, min de verbruiksvoorspelling), 5 minuten aan één stuk — dan meldt *Waarom* een **onverwacht zonne-overschot**; was er minstens 300 W voorspeld en is er minder dan de helft van, dan meldt *Waarom* **minder zon dan verwacht**. Elk bericht zegt hoeveel, wat er was voorspeld, en wat het betekent voor de batterijen. Als het 10 minuten voorbij is, geeft een tweede bericht de energie die over was en hoeveel daarvan was voorspeld. Beide waarden zijn instellingen (sectie *Zonvoorspelling*). Hiervoor zijn een gemeten PV-bron en een zonvoorspelling nodig. Kan ook als melding worden verstuurd (soort *Onverwacht zonne-overschot of -tekort*). Wat de batterijen doen: [Planning: als de zon afwijkt van de voorspelling](planning.md#when-the-sun-differs-from-the-forecast).

## Nauwkeurigheid {#accuracy}

Elke voorspelling wordt achteraf gecontroleerd per vooruitzicht (0–1 u … 5 dagen+): verbruik tegen het gemeten verbruik, PV tegen de gemeten PV, geschatte prijzen tegen de prijzen die later zijn gepubliceerd. Geleerde correcties worden automatisch toegepast, of met de hand ingesteld (actie `set_forecast_correction`). Bij prijzen verschuift één wilde periode (een piek die niemand zag aankomen) niet alle latere schattingen: voor de geleerde correctie telt een fout hoogstens 3x de gebruikelijke (mediaan) fout van zijn vooruitzicht (minstens 0,02 per kWh); de fout in de nauwkeurigheidstabel blijft de echte.

Worden verwarmings-/koelapparaten apart gemeten en is het temperatuureffect geleerd, dan wordt ook het **verwarmings-/koeldeel** apart gecontroleerd: het vermogen dat de [temperatuurstap](#outdoor-temperature-optional) per tijdvak verwachtte tegen wat de apparaten echt gebruikten (rij *waarvan verwarming/koeling* op het tabblad *Nauwkeurigheid*). Dat wordt alleen gemeten, niet gebruikt om iets te corrigeren.
