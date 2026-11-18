# Instellingen

Elk scherm van HomeBatteryAssist met elk veld en de uitleg die je in Home Assistant ziet, gemaakt uit de teksten van de integratie zelf. Voor de achtergrond zie [Meten](measuring.md), [Voorspellen](forecasting.md) en [Planning](planning.md); voor plaatjes van de schermen zie [Screenshots](screenshots.md).

## Installatie en netaansluiting {#setup}

De eerste installatie en **Configureren → Netaansluiting en meter** doorlopen dezelfde stappen.

### Netmeter {#setup-meter}

Deze netmeters zijn gevonden. Een meter die rechtstreeks wordt uitgelezen geeft ongeveer elke seconde een waarde (alleen lezen, er verandert niets aan de meter); een meter van een andere integratie gebruikt zijn sensoren. Of kies zelf de fasen en sensoren. HomeBatteryAssist leest de meter alleen uit.

**Meter**

### Meter rechtstreeks uitlezen {#setup-direct}

Kies het type meter en vul het IP-adres in. HomeBatteryAssist leest hem ongeveer elke seconde uit, alleen lezen; er verandert niets aan de meter. Vul bij een SMA Home Manager / Energy Meter het adres in waarvandaan hij uitzendt.

**Type meter**, **IP-adres**

### Netaansluiting {#setup-user}

Heeft je woning een 1-fase of 3-fase aansluiting op het net?

**Aantal fases**

### Grootte aansluiting {#setup-max-current}

Kies de grootte van je netaansluiting (hoofdzekering per fase). Je vindt deze op je energiecontract of op de hoofdzekering in de meterkast.

**Aansluiting**

### Metingen per fase {#setup-sensors}

Kies per fase de sensor die het vermogen (W) of de stroom (A) op die fase meet, meestal afkomstig van je slimme meter (P1). Is deze sensor positief bij afname en negatief bij teruglevering, laat dan de terugleversensor leeg. Heeft je meter aparte sensoren voor afname en teruglevering, kies dan beide. Let op: stroomsensoren kunnen afname en teruglevering meestal niet onderscheiden.

| Veld | Uitleg |
|---|---|
| **Fase L1** |  |
| **Fase L1 teruglevering (optioneel)** |  |
| **Fase L2** |  |
| **Fase L2 teruglevering (optioneel)** |  |
| **Fase L3** |  |
| **Fase L3 teruglevering (optioneel)** |  |
| **Fase L1 stroom (optioneel)** | Optioneel: de stroom (A) per fase, van dezelfde meter. De hoofdzekering ziet stroom; zonder deze sensoren rekent de fasebeveiliging met vermogen / spanning (of / 230 V). De spanning (V) per fase maakt dat preciezer. |
| **Fase L2 stroom (optioneel)** |  |
| **Fase L3 stroom (optioneel)** |  |
| **Fase L1 spanning (optioneel)** |  |
| **Fase L2 spanning (optioneel)** |  |
| **Fase L3 spanning (optioneel)** |  |

## Instellingen {#settings}

**Configureren → Instellingen**: de hoofdvelden, daarna de uitklapbare secties. **Terug naar standaardinstellingen** zet ze terug (waar prijzen en de PV-voorspelling vandaan komen blijft).

### Hoofdvelden {#settings-main}

| Veld | Uitleg |
|---|---|
| **Interval verbruikshistorie** | Een korter interval is nauwkeuriger, maar slaat meer gegevens op. |
| **Maximale planningshorizon** | Hoeveel dagen het systeem maximaal vooruit mag plannen. |
| **Sensor prijsvoorspelling** | Bij de prijsbron 'Prijssensor': een sensor van een andere integratie met de prijsvoorspelling in zijn attributen. |
| **PV-voorspelling** | Integrations die een zonne-opwekvoorspelling leveren (bijv. Forecast.Solar, Solcast). Gekozen voorspellingen worden opgeteld tot het totaal van je woning. |
| **Herberekenen elke** | Hoe vaak de voorspellingen automatisch opnieuw worden berekend. |
| **Modus batterijplan** | Hoe HomeBatteryAssist de batterijen zou aansturen (voorlopig alleen advies). Alle modi worden altijd ter vergelijking doorgerekend. Eigen planningsmodules uit /config/homebatteryassist/planners verschijnen hier ook (na herladen). |
| **Prijsbron** | Waar de stroomprijzen vandaan komen. In Home Assistant gevonden bronnen staan in de lijst (* = nog niet getest op een echte installatie); 'Prijssensor' gebruikt de sensor die je hieronder kiest. |
| **Extra prijsvoorspelling** | Optioneel: een tweede bron die verder vooruit kijkt (bijv. een meerdaagse voorspelling), gebruikt na de prijzen van de prijsbron; telt altijd als voorspeld. |
| **Verbruiksvoorspeller** | Hoe het huisverbruik voorspeld wordt. De nauwkeurigheid van elke voorspeller staat naast elkaar op het dashboard. Eigen voorspellers uit /config/homebatteryassist/forecasters verschijnen hier ook (na herladen). |
| **Tarief** | Hoe de prijzen van de prijsbron worden omgezet in wat een kWh echt kost en oplevert. Eigen tarieven uit /config/homebatteryassist/tariffs verschijnen hier ook (na herladen). |

### Terugleverprijs {#settings-export}

Wat teruggeleverde stroom oplevert.

| Veld | Uitleg |
|---|---|
| **Terugleverprijs** | Wat stroom die je teruglevert oplevert: de inkoopprijs x factor (hieronder), de kale marktprijs (EPEX, uit de gekozen sensoren of uit marktprijs-attributen van de prijssensor), of de terugleverprijs: van de prijsbron als die er een heeft (DynTarNL: de marktprijs min de inkoopvergoeding van je leverancier), anders uit de gekozen sensoren. Waar die niet reiken, geldt inkoopprijs x factor. |
| **Terugleverprijs-sensoren** | Eén of meer sensoren met prijzen (status en/of prijslijst in attributen), bijv. een marktprijssensor voor vandaag/morgen plus een voorspellingssensor voor de dagen daarna. Bij overlap wint de eerste sensor. |
| **Vergoeding teruglevering** | Bij 'Inkoopprijs x factor', en overal waar de terugleverprijs-sensoren geen prijs geven. De berekeningen gaan uit van geen saldering (in Nederland afgeschaft per 1 januari 2027): teruglevering levert alleen deze vergoeding op. Standaard 0,25 (een kwart van de inkoopprijs); 1,0 staat gelijk aan salderen. |

### Zonvoorspelling {#settings-solar}

Correctie van de zonvoorspelling, en wat er gebeurt als de zon ervan afwijkt.

| Veld | Uitleg |
|---|---|
| **Correctie zonvoorspelling** | Hoe de zonvoorspelling vóór het plannen wordt gecorrigeerd: automatisch (geleerd uit hoe goed eerdere voorspellingen waren), met een vaste marge (hieronder), beide, of niet. |
| **PV-correctie** | Bij 'automatisch': welke correctiemodule leert van eerdere voorspellingen. 'Per vooruitzicht, uur en niveau' (standaard) leert ook per uur van de dag (schaduw, dakrichting) en per niveau (somber of zonnig uur); 'Per vooruitzicht' is de oorspronkelijke. Eigen correcties uit /config/homebatteryassist/pv_corrections staan hier ook (na herladen). Het tabblad Nauwkeurigheid vergelijkt ze. |
| **Marge op de zonvoorspelling** | Bij 'vaste marge' en 'beide': de plannen rekenen op zoveel minder zonnestroom, als buffer tegen te optimistische voorspellingen. |
| **Meer of minder zon dan verwacht: vanaf dit verschil** | Is er minstens zoveel meer zonnestroom over dan voor dit uur voorspeld (en was minder dan de helft ervan voorspeld), dan slaan de batterijen het bovenop het plan op. Was er minstens zoveel voorspeld en is er minder dan de helft van, dan laden ze alleen wat er echt over is: het net vult de ontbrekende zon niet aan. Standaard 300 W. |
| **Meer of minder zon dan verwacht: melden na** | Waarom meldt het (en stuurt een melding, bij 'Onverwacht zonne-overschot of -tekort') zodra het zo lang duurt, zodat een voorbijtrekkende wolk of opklaring geen bericht geeft. De batterijen reageren meteen. Standaard 5 min. |

### Planning {#settings-planning}

Hoe de plannen kosten en prijzen afwegen, en de vaste standen.

| Veld | Uitleg |
|---|---|
| **Slijtagekosten batterij** | Kosten per kWh door de batterij (slijtage), in de prijseenheid; voorkomt laden/ontladen voor minieme winst. |
| **Max. cycli per dag (arbitrage)** | Arbitrage laadt en ontlaadt hoogstens zoveel volledige cycli per dag (ontladen energie / capaciteit), om de batterijen te sparen. 0 = geen grens. |
| **Min. arbitragemarge** | Arbitrage laadt alleen om later te ontladen als dat minstens zoveel per kWh oplevert, bovenop de slijtagekosten. |
| **Pas ontladen vanaf prijs** | Optioneel: de batterijen ontladen alleen als stroom minstens dit kost (ook bij nul op de meter). |
| **Uit het net laden tot prijs** | Optioneel: arbitrage laadt alleen uit het net als stroom hoogstens dit kost (laden met zonne-overschot mag altijd). |
| **Doelnetvermogen (nul op de meter)** | Nul op de meter mikt op dit netvermogen in plaats van precies 0 W, bijv. +50 W zodat er altijd een beetje wordt afgenomen. |
| **Handmatig vermogen** | Gebruikt in de planmodus “Handmatig”: de batterijen laden (positief) of ontladen (negatief) altijd met dit vermogen, binnen hun grenzen. |
| **Laadhysterese** | Eenmaal vol laden de batterijen pas weer als hun laadniveau zoveel onder het maximum is gezakt (minder kleine bijlaadmomenten). 0 = uit. |
| **Vakantiemodus** | Zolang aan, wordt het gemeten huisverbruik niet gebruikt om het gewone verbruik te leren (de voorspelling blijft de normale dagen gebruiken). |
| **Onderschepper (interceptor)** | Jouw laatste woord per batterij voordat een opdracht uitgaat: goedkeuren, beperken (minder, zelfde richting), tegenhouden of vrijgeven. De eigen controle van HomeBatteryAssist komt erna en gaat altijd voor. Standaard geen; eigen onderscheppers uit /config/homebatteryassist/interceptors staan hier ook (na herladen). Voorlopig werkt hij op de virtuele batterijen. |

### Grenzen en reserve {#settings-limits}

Reserve, vermogensgrenzen, piekgrens en fasemarge.

| Veld | Uitleg |
|---|---|
| **Reserve laadniveau** | De plannen gaan nooit onder dit laadniveau (bijv. als noodreserve), bovenop het eigen minimum van elke batterij. Piekafvlakking en fasebeveiliging mogen het nog wel gebruiken. 0 = uit. |
| **Nachtreserve laadniveau** | Vanaf de avond (zon weg) tot de zon weer op is (volgens de PV-voorspelling) gaan de plannen niet onder dit laadniveau. Arbitrage laadt er zo nodig voor uit het net op het goedkoopste moment vóór zonsopkomst; nul op de meter houdt het alleen vast. Piekafvlakking en fasebeveiliging mogen het nog wel gebruiken. 0 = uit. |
| **Max. laadvermogen alle batterijen** | Alle batterijen samen laden nooit met meer dan dit vermogen. 0 = geen grens. |
| **Max. ontlaadvermogen alle batterijen** | Alle batterijen samen ontladen nooit met meer dan dit vermogen. 0 = geen grens. |
| **Minimaal vermogen per batterij** | Onder dit vermogen is het omzetverlies van een batterij hoog: een vraag wordt over zo min mogelijk batterijen verdeeld, die elk minstens dit vermogen draaien, en over meer batterijen als er meer vermogen nodig is. |
| **Balanscontrole elke** | Hoe vaak gekeken wordt of een andere batterij het moet overnemen, zodat de batterijen gelijk gevuld blijven. Daartussen blijven de gebruikte batterijen actief. |
| **Piekgrens netafname** | Piekafvlakking op de totale netafname (alle fasen samen): de arbitrageplannen houden energie achter de hand om hieronder te blijven, en virtuele batterijen vangen de piek op als hij toch wordt overschreden. Naast de beveiliging per fase van de hoofdzekering. 0 = uit. |
| **Piekgrens telt uitgesloten apparaten mee** | Aan: het verbruik van uitgesloten apparaten (bijv. een laadpaal) telt mee voor de piekgrens. |
| **Piekreserve laadniveau** | Onder dit laadniveau ontladen de batterijen alleen nog voor netafname boven de piekgrens, zodat er energie blijft voor pieken. Alleen met een piekgrens. 0 = uit. |
| **Veiligheidsmarge per fase** | Deel van de hoofdzekering dat de batterijen op elke fase altijd vrijlaten (voor alle fasen hetzelfde). Bij 3x25A en 10% houden de batterijen elke fase onder 22,5 A, in het plan en in de simulatie. |

### Korte pieken {#settings-spikes}

Korte, hoge verbruikspieken op willekeurige momenten (waterkoker, magnetron, inductie) worden herkend door een piekfiltermodule. Een piek die regelmatig terugkomt (op de meeste dagen van die weekdag, op hetzelfde uur) telt als normaal verbruik. Apparaten met een eigen vermogenssensor kun je ook als uitgesloten apparaat toevoegen: daarvoor ontlaadt de batterij nooit.

| Veld | Uitleg |
|---|---|
| **Niet ontladen voor willekeurige pieken** | Nul op de meter ontlaadt niet (extra) voor een herkende piek: die komt uit het net. |
| **Willekeurige pieken niet meetellen in het gemiddelde verbruik** | Van de energie van willekeurige pieken wordt niet geleerd: de verbruiksvoorspelling (en het batterijplan) rekent er niet op. |
| **Piek: minstens zoveel boven het gebruikelijke verbruik** | Een stijging van minstens zoveel boven het gebruikelijke verbruik kan een piek zijn. Standaard 2000 W. |
| **Piek: duurt hoogstens** | Een stijging die langer duurt is normaal verbruik (bijvoorbeeld een oven) en wordt vanaf dan gevolgd. Standaard 5 minuten. |
| **Piekfilter** | De module die pieken herkent. Eigen filters uit /config/homebatteryassist/spike_filters staan hier ook (na herladen). |

### Reactie op de meter {#settings-reaction}

Hoe vaak de batterijen de netmeter volgen (nul op de meter, fasebeveiliging). Op fase-overbelasting en de piekgrens wordt altijd direct gereageerd. Voorlopig stuurt dit de virtuele batterijen; later de aansturing.

| Veld | Uitleg |
|---|---|
| **Een ronde elke** | Hoe vaak de batterijen op de meter worden bijgeregeld. Elke seconde levert nauwelijks iets op (de batterijen hebben zelf 1 à 2 seconden nodig); minder vaak betekent minder opdrachten. Standaard 5 seconden. |
| **Rekenen met het gemiddelde over de ronde** | Bijregelen op het gemiddelde van de meter over de afgelopen ronde in plaats van de laatste waarde, zodat één uitschieter niets aanstuurt. |
| **Direct reageren op een grote sprong** | Verandert het net meer dan de sprong hieronder, dan direct een extra ronde (bijv. een oven of laadpaal die aangaat), niet pas bij de volgende ronde. |
| **Grote sprong: minstens** | Standaard 1000 W. |

### Volladen {#settings-full-charge}

Het periodiek volladen van de batterijen.

| Veld | Uitleg |
|---|---|
| **Volledig opladen forceren binnen** | Als een batterij niet binnen zijn interval volledig is opgeladen, wordt een volledige oplading geforceerd op het goedkoopste moment binnen zoveel dagen vóór de deadline. |
| **Voorkeursdag volladen** | Plan het periodiek volladen op deze weekdag als die in de periode past; anders op het goedkoopste moment. |
| **Volladen liefst met zonnestroom** | Tel zonne-overschot als goedkoop (wat terugleveren zou opleveren), zodat volladen op een zonnig moment de voorkeur krijgt boven het net. |

### Temperatuur {#settings-temperature}

Minder vermogen voor warme batterijen (met een temperatuursensor).

| Veld | Uitleg |
|---|---|
| **Temperatuurgrens** | Batterijen met een temperatuursensor laden tot deze temperatuur met vol vermogen. |
| **Afbouwband temperatuur** | Boven de grens gaat het vermogen over zoveel graden omlaag, tot het minimale vermogen. |
| **Minimaal vermogen bij warmte** | Vermogen aan het eind van de afbouwband, in % van het maximum van de batterij. |
| **Ook ontladen terugregelen bij warmte** | Ook het ontlaadvermogen verlagen, niet alleen het laadvermogen. |

### Meldingen {#settings-notifications}

Belangrijke beslissingen als melding ontvangen.

| Veld | Uitleg |
|---|---|
| **Sturen naar** | Notify-diensten (bijv. de companion-app) en/of een melding in Home Assistant zelf. |
| **Over** | Welke beslissingen worden verstuurd. |

### Weer en buitentemperatuur (optioneel) {#settings-weather}

Voor huizen die elektrisch verwarmen of koelen: de verbruiksvoorspelling volgt de weersverwachting. Voeg een apparaat voor verwarming/koeling toe voor een zuiverder signaal.

| Veld | Uitleg |
|---|---|
| **Weerbron** | Waar de temperatuurverwachting vandaan komt (een module): een weer-entiteit naar keuze, de KNMI-integratie (zelf gevonden), Weerlive (KNMI, gratis API-sleutel van weerlive.nl nodig) of Open-Meteo (geen sleutel nodig; beste model of het KNMI-model). Zet de temperatuurstap in de verbruiksvoorspelling aan. |
| **Weer-entiteit** | Bij 'Weer-entiteit': een weer-entiteit met een verwachting (bijv. Buienradar, Met.no, KNMI). Eerst de verwachting per uur, daarna de minimum/maximum per dag voor de dagen erna. |
| **API-sleutel** | Voor Weerlive (verplicht) en Open-Meteo (alleen met een commercieel abonnement). Bewaard in Home Assistant; alleen naar die dienst gestuurd. |
| **Plaats** | Voor Weerlive en Open-Meteo: 'breedtegraad,lengtegraad' (Weerlive kan ook een plaatsnaam). Leeg: de thuislocatie van Home Assistant, afgerond op ongeveer 1 km. |
| **Sensor buitentemperatuur** | Optioneel, nauwkeuriger dan de huidige temperatuur van de weer-entiteit; de geschiedenis ervan wordt gebruikt om meteen te leren. |

### Batterij volgt opdracht {#settings-command-check}

Of elke batterij doet wat haar opgedragen wordt (in deze fase door haar eigen integratie, bijv. Omnibattery), zodat een batterij die niet meer laadt of ontlaadt opvalt.

| Veld | Uitleg |
|---|---|
| **Opdrachten controleren vanaf** | Een opdracht om met minstens dit vermogen te laden of ontladen wordt gecontroleerd: de batterij moet minstens de helft ervan (of van haar maximale vermogen) in die richting doen. Standaard 100 W. |
| **Melden na** | Waarom meldt het (en stuurt een melding, met 'Een batterij volgt haar opdracht niet') zodra het zo lang duurt, zodat opstarten en oplopen geen bericht geven. Vol, leeg, laden/ontladen uitgeschakeld en de hysterese van de batterij worden uitgelegd, niet als probleem gemeld. Standaard 2 min. |

### Begrenzing teruglevering (PV-omvormers) {#settings-export-limit}

Hoeveel er nu maximaal teruggeleverd mag worden, als de sensor Max. teruglevering op de netaansluiting (0 W = niet terugleveren): alleen terugleveren als het na kosten geld oplevert (terugleverprijs van het tarief, min de terugleverkosten van je contract), of een vaste maximum. In deze fase alleen getoond en uitgelegd in Waarom; er wordt niets naar een omvormer gestuurd.

| Veld | Uitleg |
|---|---|
| **Nooit terugleveren** | Optioneel: terugleveren wordt altijd gestopt (Max. teruglevering 0 W), wat de prijs ook is; de batterijen slaan nog op wat ze kunnen, de omvormers zouden niet meer leveren dan huis en batterijen gebruiken. |
| **Niet terugleveren als het te weinig oplevert** | Onder de grensprijs (terugleverprijs min terugleverkosten) is de grens 0 W: de batterijen slaan nog op wat ze kunnen, de omvormers zouden niet meer leveren dan huis en batterijen gebruiken. Uit: alleen een vaste maximum begrenst. |
| **Terugleverkosten (vergoeding of boete)** | Per teruggeleverde kWh, bovenop de terugleverprijs: bijv. de terugleverkosten van een vast contract. Alleen terugleveren als de terugleverprijs min deze kosten boven de grensprijs ligt. Standaard 0. |
| **Grensprijs (netto)** | Alleen terugleveren als de terugleverprijs (na het tarief, min de terugleverkosten) hierboven ligt, per kWh. Standaard 0: alleen als terugleveren geld oplevert; bij een negatieve prijs nooit. |
| **Vaste maximale teruglevering** | Bijv. een grens van de netbeheerder. 0 = geen. |

## Apparaten en tijdvakken {#devices}

Toe te voegen onder de integratie (**+ … toevoegen**) en te wijzigen met het tandwiel ernaast.

### PV-bron {#device-pv-source}

Een meting van zonne-opwek (PV), bijvoorbeeld een omvormer. De opwek wordt bij de netmeting opgeteld om het werkelijke huisverbruik te bepalen.

| Veld | Uitleg |
|---|---|
| **Naam** |  |
| **Sensor** | Sensor die het vermogen (W) of de stroom (A) van dit apparaat meet. |
| **Fase** | De fase waarop dit apparaat is aangesloten, als het één fase gebruikt. |
| **Vermogen L1 (optioneel, 3-fase)** | Voor een 3-fase apparaat: een sensor per fase geeft de precieze verdeling over de fasen. Leeg laten om het totaal gelijk te verdelen (fase 'alle fasen') of de fase hierboven te gebruiken. |
| **Vermogen L2 (optioneel, 3-fase)** |  |
| **Vermogen L3 (optioneel, 3-fase)** |  |
| **Gemeten door** | Een sensor van een andere integratie, of een meter die rechtstreeks wordt uitgelezen (ongeveer elke seconde, alleen lezen), bijv. een HomeWizard kWh-meter op de groep van de omvormer. |
| **IP-adres meter** | Alleen bij een rechtstreeks uitgelezen meter. |
| **Omvormer-driver (begrenzing teruglevering)** | Hoe deze omvormer begrensd zou kunnen worden voor de begrenzing van de teruglevering. Met een Sunny Home Manager 2.0 kies je de Home Manager voor elke SMA-omvormer erachter (de begrenzing gaat dan via de Home Manager). In deze fase wordt niets verstuurd: alleen getoond wat hij zou sturen. |
| **Adres voor de driver** | Waar de gekozen driver naartoe zou sturen: het IP-adres van het apparaat waarmee hij praat, eventueel met poort en unit-id (host:poort/unit). Bij de driver Sunny Home Manager: het IP-adres van de Home Manager (hetzelfde voor elke PV-bron erachter), niet dat van de omvormer. Bij SMA Modbus of SunSpec: het IP-adres van de omvormer (SunSpec op een SMA: bijv. 192.168.1.20:502/126). Zonder driver: leeg laten. |
| **Mogelijk vermogen (optioneel)** | Wat deze PV-bron nu zou kunnen leveren (W), bijv. een register van een SMA-omvormer, ingelezen met de Modbus-integratie van Home Assistant. Waar het hoger is dan het gemeten vermogen, werd PV tegengehouden (begrensd): HomeBatteryAssist leert dan van wat de zon gaf, en toont wat er tegengehouden wordt. |
| **Automaat van de omvormer (A per fase)** | De automaat van de groep van de omvormer (bijv. 20 A): het meeste dat deze omvormer kan leveren (A x 230 V, x 3 als hij op alle fasen zit). Als dit bij elke PV-bron is ingevuld, is Max. teruglevering niet meer dan de omvormers plus de batterijen kunnen leveren, in plaats van het maximum van de netaansluiting. |

### Uitgesloten apparaat {#device-excluded-load}

Een apparaat waarvan het verbruik buiten het huisverbruik wordt gehouden, bijvoorbeeld een laadpaal, zodat het de verbruiksvoorspelling niet verstoort.

| Veld | Uitleg |
|---|---|
| **Naam** |  |
| **Sensor** | Sensor die het vermogen (W) of de stroom (A) van dit apparaat meet. |
| **Fase** | De fase waarop dit apparaat is aangesloten, als het één fase gebruikt. |
| **Vermogen L1 (optioneel, 3-fase)** | Voor een 3-fase apparaat: een sensor per fase geeft de precieze verdeling over de fasen. Leeg laten om het totaal gelijk te verdelen (fase 'alle fasen') of de fase hierboven te gebruiken. |
| **Vermogen L2 (optioneel, 3-fase)** |  |
| **Vermogen L3 (optioneel, 3-fase)** |  |

### Batterij {#device-battery}

Koppel een thuisbatterij via de entiteiten van zijn eigen integratie (voorlopig alleen uitlezen). Het laden en ontladen van de batterij wordt buiten het huisverbruik gehouden.

| Veld | Uitleg |
|---|---|
| **Naam** |  |
| **Sensor vulling** | Sensor met de vulling in %. |
| **Sensor vermogen** | Sensor met het laad-/ontlaadvermogen (W) of de stroom (A) van de batterij. |
| **Richting vermogensensor** | Is de vermogensensor positief tijdens laden of tijdens ontladen? |
| **Bruikbare capaciteit** | Capaciteit van de batterij in kWh (uit de specificaties). |
| **Maximaal laadvermogen** |  |
| **Maximaal ontlaadvermogen** |  |
| **Minimale vulling** | De batterij wordt niet verder ontladen dan dit niveau. |
| **Maximale vulling** | De batterij wordt niet verder geladen dan dit niveau (behalve bij volledig opladen). |
| **Rendement laden en ontladen** | Deel van de geladen energie dat bij ontladen weer terugkomt. |
| **Volledig opladen elke** | Minstens elke zoveel dagen tot 100% laden (balanceren van de cellen). 0 = nooit. |
| **Fase** | De fase waarop de batterij is aangesloten, als hij één fase gebruikt. |
| **Temperatuursensor (optioneel)** | Temperatuur van de batterij; bij warmte rekenen de plannen met minder vermogen (zie de temperatuurinstellingen). |
| **Batterijmeter (optioneel)** | Een direct uit te lezen meter op de lijn van de batterij, bijvoorbeeld een kWh-meter. Het vermogen daarvan (+ de batterij in = laden) wordt dan gebruikt in plaats van de vermogenssensor; voor batterijen waarvan de integratie het eigen vermogen niet geeft, of als controle. |
| **Adres van de batterijmeter** | IP-adres of hostnaam van die meter. |

### Virtuele batterij {#device-virtual-battery}

Een gesimuleerde batterij die live naast je echte batterijen meedraait in de gekozen planmodus, om te zien hoe een (extra) batterij zich zou gedragen en wat hij zou opleveren. Hij telt mee in het batterijplan, nooit in het huisverbruik.

| Veld | Uitleg |
|---|---|
| **Naam** |  |
| **Tweeling van** | Een echte batterij om te kopiëren: de virtuele batterij neemt haar eigenschappen over (de velden hieronder worden dan niet gebruikt, het verlies is haar rendement), begint op haar laadniveau en wordt in haar plaats gepland, op het net zoals het zonder haar zou zijn. De echte batterij valt dan buiten het plan en houdt haar eigen sturing (bijv. Omnibattery), zodat je ze kunt vergelijken. |
| **Capaciteit** |  |
| **Maximaal laadvermogen** |  |
| **Maximaal ontlaadvermogen** |  |
| **Minimale vulling** |  |
| **Maximale vulling** |  |
| **Startvulling** |  |
| **Fase** |  |
| **Minimaal verlies** | Verlies over laden + ontladen; per simulatiestap wordt een willekeurige waarde tussen minimum en maximum gebruikt. |
| **Maximaal verlies** | De planner rekent met het gemiddelde van minimum en maximum. |
| **Volledig opladen elke** | Minstens elke zoveel dagen tot 100% laden (balanceren van de cellen). 0 = nooit. |

### Tijdvak {#device-time-slot}

Wat de batterijen doen tussen twee tijden op de gekozen dagen, in de planmodus “Tijdvakken”. Een tijdvak dat eindigt voordat het begint, loopt over middernacht. Buiten de tijdvakken werken de batterijen als nul op de meter.

| Veld | Uitleg |
|---|---|
| **Naam** |  |
| **Begin** |  |
| **Einde** |  |
| **Dagen** |  |
| **Actie** |  |
| **Vermogen** |  |
| **Tot laadniveau (optioneel)** | Laden tot, of ontladen tot, dit laadniveau. Leeg: de eigen grenzen van de batterijen. |

### Verwarming/koeling {#device-heating-cooling}

Een warmtepomp, elektrische verwarming of airco. Het verbruik blijft deel van het huisverbruik, maar wordt apart gemeten zodat de voorspelling de buitentemperatuur kan volgen (stel een weerbron in bij de instellingen). Voeg de kamertemperatuur (en een eigen buitensensor) toe om dit apparaat als eigen zone te leren.

| Veld | Uitleg |
|---|---|
| **Naam** |  |
| **Sensor** | Sensor die het vermogen (W) of de stroom (A) van dit apparaat meet. |
| **Fase** | De fase waarop dit apparaat is aangesloten, als het één fase gebruikt. |
| **Vermogen L1 (optioneel, 3-fase)** | Voor een 3-fase apparaat: een sensor per fase geeft de precieze verdeling over de fasen. Leeg laten om het totaal gelijk te verdelen (fase 'alle fasen') of de fase hierboven te gebruiken. |
| **Vermogen L2 (optioneel, 3-fase)** |  |
| **Vermogen L3 (optioneel, 3-fase)** |  |
| **Kamertemperatuur (optioneel)** | Een temperatuursensor in de kamer die dit apparaat verwarmt of koelt. Leert de gewenste kamertemperatuur (bijvoorbeeld 's nachts lager) en vanaf wanneer er verwarmd wordt, voor een nauwkeurigere voorspelling. Een apparaat per kamer geeft een zone per kamer. |
| **Eigen buitentemperatuur (optioneel)** | Bijvoorbeeld de sensor van de buitenunit van een airco; anders wordt de buitentemperatuur uit de instellingen gebruikt. |

## Entiteiten {#entities}

Wat HomeBatteryAssist aanmaakt (namen zoals in Home Assistant).

| Naam | Soort |
|---|---|
| Huisverbruik | Sensor |
| Planningshorizon | Sensor |
| Laatste beslissing | Sensor |
| Vulling | Sensor |
| Vermogen | Sensor |
| Status | Sensor |
| Opgeslagen energie | Sensor |
| Bruikbare energie | Sensor |
| Ruimte om te laden | Sensor |
| Vol of leeg om | Sensor |
| Geladen energie | Sensor |
| Ontladen energie | Sensor |
| Laatste volledige oplading | Sensor |
| Capaciteit | Sensor |
| Rendement laden en ontladen (gemeten) | Sensor |
| Vulling batterijen | Sensor |
| Vermogen batterijen | Sensor |
| Opgeslagen energie batterijen | Sensor |
| Bruikbare energie batterijen | Sensor |
| Capaciteit batterijen | Sensor |
| Netvermogen | Sensor |
| Netafname | Sensor |
| Teruglevering | Sensor |
| PV-vermogen | Sensor |
| Vermogen uitgesloten apparaten | Sensor |
| Belasting fase L1 | Sensor |
| Belasting fase L2 | Sensor |
| Belasting fase L3 | Sensor |
| Verwacht verbruik | Sensor |
| Nauwkeurigheid verbruiksvoorspelling | Sensor |
| Nauwkeurigheid PV-voorspelling | Sensor |
| Nauwkeurigheid prijsvoorspelling | Sensor |
| Batterijplan | Sensor |
| Gerealiseerd rendement | Sensor |
| Fase ontladen | Sensor |
| Fase laden (net) | Sensor |
| Fase laden (zon) | Sensor |
| Fase alleen net | Sensor |
| Testbesturing | Sensor |
| Opbrengst vandaag | Sensor |
| Verschil met echte batterij vandaag | Sensor |
| Max. teruglevering | Sensor |
| Herbereken | Knop |
| Test: laden | Knop |
| Test: ontladen | Knop |
| Test: stoppen | Knop |
| Invoer testen | Knop |
| Gelijkzetten met echte batterij | Knop |
| Volgt opdracht niet | binary_sensor |
| Testvermogen | number |
| Testduur | number |

## Acties {#actions}

Aan te roepen vanuit automatiseringen en scripts (zie [Werken met andere integraties](integration.md)).

### Herberekenen {#action-recalculate}

`homebatteryassist.recalculate` — Berekent de voorspellingen van HomeBatteryAssist nu opnieuw, bijvoorbeeld als er nieuwe prijzen of PV-voorspellingen zijn. Alleen de eigen voorspellingen van HomeBatteryAssist worden herberekend; er wordt geen apparaat aangestuurd.

### Verbruikshistorie importeren {#action-import-history}

`homebatteryassist.import_history` — Vult de verbruikshistorie uit de statistieken van Home Assistant, bijvoorbeeld als startgegevens voor de voorspellingen. Standaard wordt het huisverbruik gereconstrueerd uit de ingestelde sensoren (net, PV, uitgesloten apparaten, batterijen). Eigen metingen worden nooit overschreven, tenzij Vervangen aan staat.

| Veld | Uitleg |
|---|---|
| **Dagen** | Hoeveel dagen terug importeren (maximaal de bewaartermijn van 28 dagen). |
| **Verbruikssensor (optioneel)** | Neem het huisverbruik van deze sensor over in plaats van het te reconstrueren, bijvoorbeeld van Omnibattery. |
| **Oudere vermogensensoren batterij (optioneel)** | Eerdere vermogensensoren van de batterij (zelfde richting), gebruikt voor de periode voordat de huidige sensor bestond. |
| **Eigen metingen vervangen** | Laat geïmporteerde waarden eigen metingen in dezelfde perioden vervangen. |

### Verbruiksvoorspelling aanpassen {#action-adjust-forecast}

`homebatteryassist.adjust_forecast` — Past het verwachte huisverbruik aan voor een periode, bijvoorbeeld vanuit een script voor vakantie, gasten of een geplande grote verbruiker. Geef een begin (standaard: nu), een einde of duur, en precies één wijziging: een factor, een extra vermogen in W of een vast vermogen in W. Aanpassingen blijven tot hun einde bewaard.

| Veld | Uitleg |
|---|---|
| **Naam** | Zichtbaar in de voorspelling en het beslissingslog, en bruikbaar om hem weer te verwijderen. |
| **Begin** | Standaard: nu. |
| **Einde** | Einde van de periode (of geef een duur). |
| **Duur** | Lengte van de periode (in plaats van een einde). |
| **Factor** | Vermenigvuldig het verwachte verbruik, bijvoorbeeld 0,3 tijdens vakantie of 1,5 met gasten. |
| **Extra vermogen** | Tel dit vermogen in W erbij op (of met een min eraf), bijvoorbeeld 2000 voor de oven. |
| **Vast vermogen** | Vervang het verwachte verbruik door dit vermogen in W. |

### Aanpassingen voorspelling verwijderen {#action-clear-forecast-adjustments}

`homebatteryassist.clear_forecast_adjustments` — Verwijdert aanpassingen van de verbruiksvoorspelling op id of naam; zonder id of naam worden alle aanpassingen verwijderd.

| Veld | Uitleg |
|---|---|
| **Id** | Id('s) van de aanpassingen die weg moeten. |
| **Naam** | Na(a)m(en) van de aanpassingen die weg moeten. |

### Correctie voorspelling instellen {#action-set-forecast-correction}

`homebatteryassist.set_forecast_correction` — Bepaalt hoe een voorspelling wordt gecorrigeerd op basis van de meelopende nauwkeurigheid: geleerd (standaard), uit (alleen meten) of handmatig met een eigen waarde. Optioneel voor één vooruitzicht en voor een beperkte tijd.

| Veld | Uitleg |
|---|---|
| **Voorspelling** | Welke voorspelling: verbruik, PV, prijs of alle. |
| **Modus** | geleerd: gebruik de meelopende nauwkeurigheid; uit: niet corrigeren; handmatig: gebruik de opgegeven waarde. |
| **Waarde** | Handmatige correctie: een factor voor PV (bijv. 0,85), een afwijking in W voor verbruik, een afwijking in de prijseenheid voor prijzen. |
| **Vooruitzicht** | Alleen voor voorspellingen die zo lang vóór de periode gemaakt zijn (standaard: alle). |
| **Duur** | Na deze tijd terug naar geleerd (standaard: tot het weer gewijzigd wordt). |

### Nauwkeurigheid voorspelling wissen {#action-reset-forecast-accuracy}

`homebatteryassist.reset_forecast_accuracy` — Vergeet wat er over een voorspelling geleerd is (bijv. na het wisselen van PV-voorspeller) en begint opnieuw te meten.

| Veld | Uitleg |
|---|---|
| **Voorspelling** | Welke voorspelling: verbruik, PV, prijs of alle. |

### Modus batterijplan instellen {#action-set-plan-mode}

`homebatteryassist.set_plan_mode` — Kiest de modus van het batterijplan (advies): nul op de meter of arbitrage.

| Veld | Uitleg |
|---|---|
| **Modus** | nom of arbitrage. |

---

*Gemaakt door `scripts/docs_reference.py` uit de teksten van de integratie.*
