---
description: "Hoe HomeBatteryAssist het net per fase meet (HomeWizard P1, SMA Home Manager, Shelly), thuisbatterijen (Marstek), zonnepanelen en het huisverbruik in Home Assistant."
---

# Meten {#measuring}

## Netaansluiting en meter {#grid-connection-and-meter}

De netaansluiting is een eigen apparaat, *Netaansluiting* (model: de rechtstreeks uitgelezen meter; naast het apparaat HomeBatteryAssist, met het netvermogen, afname, teruglevering en de belasting per fase). Ze hoort bij de basisinstallatie, niet bij de sub-items: wijzigen via het tandwiel van HomeBatteryAssist → *Netaansluiting*. De knop **Invoer testen** luistert 10 seconden naar de meter en toont daarna een melding met alles wat HomeBatteryAssist uitleest: de bron en hoeveel waarden die stuurde, per fase vermogen, stroom, spanning, arbeidsfactor en belasting, de energiestromen die daaruit volgen, en elke uitgelezen sensor (net, PV-bronnen, uitgesloten apparaten, verwarming/koeling, batterijen) met de waarde nu — handig na het instellen, of als iets niet klopt.

- **Netaansluiting** met 1 of 3 fasen en de grootte ervan (1x10A tot en met 3x80A).
- **Netmeter**, gekozen tijdens de installatie:
  - **rechtstreeks uitgelezen**, ongeveer eens per seconde, alleen lezen (er wordt niets aan de meter veranderd, en de eigen integratie van de meter blijft gewoon werken):
    - HomeWizard P1-meter en kWh-meters (1- en 3-fase), lokale API;
    - SMA Sunny Home Manager 2.0 / Energy Meter, Speedwire (alleen ontvangen: de meter stuurt zijn gegevens toch al over het netwerk; herkend aan het serienummer, dus een nieuw IP-adres verandert niets);
    - Shelly Pro 3EM / 3EM en Shelly EM / Pro EM, lokale API *(nog niet op een apparaat gecontroleerd)*;
    - Iammeter WEM3080 / WEM3080T, lokale API *(nog niet op een apparaat gecontroleerd)*;

    Meters die al in Home Assistant zitten worden automatisch aangeboden; elk van deze meters kun je ook op IP-adres invoeren;
  - **via de sensoren van zijn integratie** (bijv. een HomeWizard P1 wordt herkend en ingevuld);
  - **je eigen sensoren** per fase: één sensor met plus/min-teken, of aparte sensoren voor afname en teruglevering, in vermogen (W); een stroomsensor (A) heeft geen teken en hoort daarom alleen in de optionele stroomvelden (fasebeveiliging).

Nieuwe meters worden toegevoegd als [drivers](drivers.md).

## Batterijen {#batteries}

Batterijen worden **alleen-lezen** gekoppeld via de entiteiten van hun eigen integratie. Batterijen van **Omnibattery** en **Marstek Modbus** worden herkend en ingevuld, en hun *batterijdriver* voegt temperatuur, spanningen, celspanningen, cycli, de energie van vandaag en het gemeten rendement toe; elke andere batterij kun je handmatig koppelen.

Een batterij kan optioneel een **externe meter** op zijn groep krijgen (bijv. een HomeWizard kWh-meter, rechtstreeks uitgelezen): het vermogen daarvan wordt dan gebruikt in plaats van de vermogenssensor — zie [Drivers](drivers.md).

Per batterij: laadniveau, vermogen, status, opgeslagen/bruikbare energie, tijd tot vol/leeg, geladen/ontladen energie, laatste keer volladen en gerealiseerd rendement (na slijtage: de cycluskosten per kWh door de batterij, zoals het plan rekent; attributen `before_wear` en `wear`), plus totalen over alle batterijen.

### Vandaag en gemeten rendement {#today-and-measured-efficiency}

HomeBatteryAssist houdt per batterij eigen energietellers bij (uit het vermogen, aan de AC-kant van de batterij), ook voor de virtuele batterijen. Daaruit komen:

- **Geladen / ontladen vandaag** — sinds middernacht; voor elke batterij hetzelfde, wat haar integratie ook biedt.
- **Rendement laden en ontladen (gemeten)** — van een echte batterij: (ontladen + opgeslagen energie nu − opgeslagen energie toen) / geladen, over hoogstens de afgelopen 30 dagen. Wordt getoond zodra er minstens één volle capaciteit is geladen en de opgeslagen energie daartegen weinig veranderde (zodat de schatting van wat er nog in zit nauwelijks uitmaakt). Bewoog de batterij terwijl haar vermogen niet werd geteld (Home Assistant herstartte, haar vermogenssensor was weg), dan begint de meting opnieuw vanaf de volgende dag, zodat energie die de tellers nooit zagen haar niet scheeftrekt. Ook als sensor per batterij (*Rendement laden en ontladen (gemeten)*, met de dagen en kWh waarop het gebaseerd is). Het eigen cijfer van de batterij, als haar integratie dat heeft, staat ernaast als *rendement (volgens de batterij)*.

De batterijkaart toont ook het **celverschil** nu (hoogste − laagste celspanning) als de driver de cellen uitleest.

### Volgt de batterij haar opdracht? {#does-the-battery-follow-its-command}

Wie een batterij aanstuurt, draagt haar op om met een vermogen te laden of ontladen — in deze fase haar eigen integratie (bijv. Omnibattery), later HomeBatteryAssist. De batterijdriver leest die **opdracht** uit (bij Omnibattery en Marstek Modbus: RS485-besturing, force mode en het laad-/ontlaadvermogen) en HomeBatteryAssist controleert elke 15 seconden of de batterij die volgt: minstens de helft van het opgedragen vermogen (of van haar maximale vermogen, als dat lager is), in die richting.

- Volgt ze de opdracht **2 minuten** niet (instelling *Melden na*, sectie *Batterij volgt opdracht*; opdrachten vanaf **100 W**, instelling *Opdrachten controleren vanaf*), dan meldt *Waarom* dat; opstarten en oplopen geven dus geen bericht.
- **Verklaarbaar** — de batterij is vol of bijna vol (bij laden: vanaf 5 % onder haar maximum verlaagt haar BMS zelf het laadvermogen), koud (bij laden onder 5 °C, met een temperatuursensor), zit op haar minimum (bij ontladen), laden/ontladen staat uit op de batterij, of haar hysterese houdt laden tegen na volladen — dan zegt *Waarom* dat met de reden. Dat is geen probleem: geen alarm, geen melding.
- **Niet verklaarbaar** — een **probleem**: *Waarom* meldt het, de probleem-sensor *Volgt opdracht niet* van de batterij gaat aan (attributen: de opdracht, het vermogen van de batterij, sinds wanneer), de batterijkaart toont het in rood, en er gaat een melding uit als je *Een batterij volgt haar opdracht niet* hebt gekozen. Volgt ze een minuut lang weer, dan zegt *Waarom* dat ook.

De batterijkaart toont de opdracht die ze nu heeft (*Opdracht*: laden / ontladen met een vermogen, of stoppen). Een batterij die zichzelf aanstuurt (geen externe besturing) heeft geen opdracht en wordt niet gecontroleerd.

Wat een batterij door zijn eigen aansturing doet (laden, leveren, stoppen) wordt als periodes uitgelegd in *Waarom*, vergeleken met het plan — zie [Planning](planning.md#explanation).

### Testbesturing (staat voorlopig uit) {#test-control-switched-off-for-now}

Om het aansturen van een batterij met de hand te testen — voordat HomeBatteryAssist haar ooit automatisch aanstuurt — heeft het apparaat van elke echte batterij een **testbesturing**. **Standaard staat die uit**: de knoppen versturen niets; *Waarom* meldt alleen dat de testbesturing uit staat. Zet hem aan met de instelling *Testbesturing aan* (onderdeel *Testbesturing*), alleen terwijl je erbij bent.

| Entiteit | Wat het is |
|---|---|
| *Test: laden* / *Test: ontladen* (knoppen) | Een test starten: laden of ontladen met het testvermogen gedurende de testduur. |
| *Test: vol laden* (knop) | Laden met het maximale laadvermogen van de batterij tot ze vol is, dan nog even door zodat de cellen balanceren (tot ze minder dan 100 W opneemt, hoogstens 30 min); in totaal hoogstens 6 uur. Telt als volledige oplading. |
| *Test: stoppen* (knop) | De test meteen stoppen; de batterij gaat terug naar haar eigen sturing. |
| *Testvermogen* (getal) | Het vermogen van een test, 50 W tot het maximale vermogen van de batterij. Standaard 300 W. |
| *Testduur* (getal) | Hoe lang een test duurt, 1–30 minuten. Standaard 5 min. |
| *Testbesturing* (sensor) | *Uitgeschakeld (alleen lezen)*, *Niet mogelijk* (haar integratie kan niet worden aangestuurd), *Gereed*, *Laden (test)* of *Ontladen (test)*; attributen: de testinstellingen, en de lopende test (vermogen, sinds, tot). |

Staat hij eenmaal aan, dan doet een test het volgende:

1. **eerst controleren**: het laadniveau moet bekend zijn, een laadtest start niet als de batterij vol is, een ontlaadtest niet op of onder haar laagst toegestane laadniveau (max(min. laadniveau, reserve));
2. **de opdracht over de [directe verbinding](drivers.md#direct-battery-drivers) van de batterij sturen** als ze die heeft — bij een Marstek Venus: RS485-besturing aan, het laad- of ontlaadvermogen en de geforceerde modus in haar registers — **en anders via de eigen integratie van de batterij** — bij Omnibattery: de handmatige modus van de batterij met het laad- of ontlaadvermogen — via de beveiligingslaag die elke toekomstige besturing gebruikt (een watchdog, altijd teruggeven, hoogstens één nieuwe opdracht per 5 s, vermogensgrenzen);
3. **vanzelf stoppen** als de tijd om is, als de batterij vol raakt of haar laagst toegestane laadniveau bereikt, als ze [de opdracht niet volgt](#does-the-battery-follow-its-command), als een opdracht mislukt, met *Test: stoppen* en als HomeBatteryAssist stopt of herlaadt;
4. **de batterij altijd teruggeven** aan haar eigen sturing (direct: vermogen 0, geforceerde modus uit, RS485-besturing uit; via Omnibattery: Omnibattery neemt het weer over), en in *Waarom* vertellen waarom hij stopte en hoeveel er geladen en ontladen is.

Gebruik hem de eerste keer op een echte installatie terwijl er iemand bij is.

## Virtuele batterijen {#virtual-batteries}

Gesimuleerde wat-als-batterijen (capaciteit, vermogen, grenzen voor het laadniveau, verliezen, fase) die het plan live volgen, zodat je ziet wat een (grotere) batterij zou opleveren voordat je er een koopt. Ze laten ook fasebeveiliging en piekafvlakking aan het werk zien.

Elke batterij heeft **Opbrengst vandaag** (gerealiseerde opbrengst sinds middernacht, na slijtage), ook de virtuele.

### Tweeling van een echte batterij {#twin-of-a-real-battery}

Om HomeBatteryAssist te vergelijken met de integratie die je batterij nu aanstuurt (bijv. Omnibattery), maak je een virtuele batterij de **tweeling** van die batterij (veld *Tweeling van* bij toevoegen of wijzigen):

- hij neemt de eigenschappen van de echte batterij over (capaciteit, vermogen, grenzen voor het laadniveau, rendement als verlies, fase, volledige ladingen); zijn eigen velden worden dan niet gebruikt;
- hij **begint op het laadniveau van de echte batterij** (ook als een bestaande virtuele batterij een tweeling wordt); de knop **Gelijkzetten met echte batterij** zet hem op elk moment weer op het echte laadniveau (*Waarom* meldt het). Hij wordt niet vanzelf gelijkgezet, zodat beide vanaf dezelfde start hun eigen gang gaan;
- hij wordt **in de plaats van de echte batterij gepland**: de echte batterij valt buiten het plan (en buiten *plan gevolgd*) en houdt haar eigen sturing;
- hij werkt op het net **zoals het zonder de echte batterij zou zijn**: het vermogen van de echte batterij gaat van het net en haar fase af, dus waar de echte batterij het zonne-overschot al opslaat, ziet de tweeling dat overschot ook. Zijn opbrengst wordt net zo geteld, die van de echte batterij op het net zoals gemeten.

De sensor **Verschil met echte batterij vandaag** op de tweeling = zijn opbrengst vandaag − die van de echte batterij (positief: het plan van HomeBatteryAssist deed het beter), met attributen voor beide opbrengsten, beide laadniveaus en hoeveel meer de tweeling sinds middernacht heeft opgeslagen (energie die er nog in zit is morgen wat waard, kijk dus naar allebei). Het overzicht toont dan alleen de tweeling (zijn kaart met het laadniveau en vermogen van de echte batterij en het verschil vandaag; de fasen met *met de tweeling ervoor in de plaats*): HomeBatteryAssist is alleen met de tweeling gekoppeld. Een echte batterij kan één tweeling hebben. Andere virtuele batterijen draaien als extra wat-als-batterijen bovenop.

## PV-bronnen en uitgesloten apparaten {#pv-sources-and-excluded-devices}

**PV-bronnen** en **uitgesloten apparaten** (bijv. een laadpaal): op één fase, op alle fasen (3-fase, gelijk verdeeld) of per fase gemeten met een sensor per fase. Een PV-bron kan ook een rechtstreeks uitgelezen meter zijn (bijv. een HomeWizard kWh-meter op de groep van de omvormer).

Een **uitgesloten apparaat** hoort niet bij het huisverbruik: het zit niet in de verbruiksvoorspelling, en **de batterij ontlaadt er nooit voor** — het net levert het (zonne-overschot wordt nog wel geladen). Zo houd je ook een grote verbruiker met een eigen vermogenssensor (een laadpaal, een sauna, een droger aan een slimme stekker) bij de batterij weg. Of uitgesloten apparaten meetellen voor de piekgrens is een aparte instelling.

**Verwarming/koeling** (optioneel; een warmtepomp, elektrische verwarming of airco): gemeten als een uitgesloten apparaat, maar het verbruik **blijft deel van het huisverbruik**. Het wordt apart vastgelegd, zodat de verbruiksvoorspelling de buitentemperatuur kan volgen. Geef het optioneel de kamertemperatuur (en een eigen buitensensor): het wordt dan een zone, die apart wordt geleerd — zie [Voorspellen](forecasting.md#outdoor-temperature-optional).

## Korte pieken {#short-peaks}

Korte, hoge pieken op willekeurige momenten (een waterkoker, een magnetron, een inductiekookplaat) hebben geen eigen sensor nodig: een **piekfilter**-[module](modules.md) herkent ze in het huisverbruik terwijl ze gebeuren. Instellingensectie *Korte pieken*, beide standaard aan:

- **Niet ontladen voor willekeurige pieken** — nul op de meter ontlaadt niet (extra) voor een herkende piek; het net levert die.
- **Willekeurige pieken niet meetellen in het gemiddelde verbruik** — hun energie wordt apart vastgelegd (`spike_w` in de historie) en buiten de verbruiksvoorspelling en de controle van de nauwkeurigheid gehouden, zodat het batterijplan er niet op rekent.

Het ingebouwde filter (*Korte pieken boven een drempel*): een stijging van minstens **2000 W** boven het gebruikelijke verbruik die binnen **5 minuten** weer voorbij is, is een piek (beide instelbaar). Zolang die duurt wordt er niet voor ontladen; duurt het langer, dan is het gewoon verbruik (bijv. een oven) en wordt het vanaf dan gevolgd — een waterkoker bovenop de oven is dan weer een piek. Een sprong korter dan 15 seconden is geen piek maar sensortiming (net-, PV- en batterijsensoren werken niet op hetzelfde moment bij) en telt niet mee.

Een piek die **regelmatig terugkomt** — op minstens de helft van de dagen van die dag van de week op hetzelfde uur, minstens twee keer in de afgelopen 4 weken (bijv. de koffie elke doordeweekse ochtend) — is niet willekeurig: die blijft in het gemiddelde en de batterij dekt hem.

## Huisverbruik {#house-consumption}

**Huisverbruik** = net + PV − uitgesloten apparaten − laden van de batterij, plus afname/teruglevering van het net, PV-vermogen en de belasting per fase als % van de hoofdzekering.

Heeft het net, een batterij, een uitgesloten apparaat of een PV-bron die de laatste 30 minuten (terwijl de zon op is) stroom gaf geen waarde, dan is het huisverbruik op dat moment onbekend (niet met 0 W geteld, dat zou verkeerd verbruik vastleggen). Een omvormer die 's nachts onbereikbaar is, of na zonsopkomst nog slaapt, telt als 0 W. Een verwarmings-/koelsensor zonder waarde maakt alleen de verwarming onbekend.

Het verbruik wordt als historie bewaard (28 dagen) voor de [verbruiksvoorspelling](forecasting.md#consumption); eerder verbruik kun je eenmalig importeren uit de statistieken van Home Assistant.

## Stroom per fase {#current-per-phase}

De hoofdzekering beveiligt tegen **stroom**, niet tegen vermogen: met apparaten op stand-by, laders en motoren (arbeidsfactor onder 1) loopt er meer stroom dan vermogen / 230 V doet vermoeden — 's nachts al snel 1 A op een fase die 30 W gebruikt. Daarom gebruikt HomeBatteryAssist waar het kan de stroom per fase:

- **gemeten**: een rechtstreeks uitgelezen meter die hem doorgeeft (SMA Home Manager, HomeWizard P1, Shelly 3EM, IAMMETER), of de optionele **stroomsensoren** per fase in de instellingen van de netaansluiting (bij je eigen sensoren);
- anders **vermogen / (gemeten spanning × arbeidsfactor)**, met een spanningssensor of een meter die de spanning doorgeeft;
- anders **vermogen / 230 V**.

De historie bewaart de gemeten stroom per fase; daaruit wordt per fase geleerd welke stroom er naast het vermogen loopt, en het batterijplan rekent daarmee voor de komende tijdvakken. Het eigen aandeel van de batterij wordt omgerekend met de gemeten spanning van zijn fase.

De **eindcontrole** die de batterijen binnen de fasegrens houdt (de laatste stap voordat een vermogen wordt gebruikt, na het plan, de beveiliging en een onderschepper) rekent met het **slechtste geval** van wat er gemeten is, zodat de stroom onder de grens blijft wat de precieze waarden ook zijn:

- een gemeten stroom in hele ampères (veel meters ronden af, bijvoorbeeld een P1-poort) kan tot een halve ampère hoger zijn;
- zonder gemeten spanning rekent hij met **207 V**, de laagst toegestane netspanning (230 V − 10 %): elke W van het huis en van een batterij telt dan voor de meeste stroom;
- zonder gemeten stroom of arbeidsfactor is het blinde deel niet te kennen; dan dekt alleen de fasemarge het.

Vlak bij de grens krijgen de batterijen daardoor iets minder ruimte dan de precieze waarden zouden laten; met een meter of sensoren die **stroom en spanning** per fase doorgeven is dat het minst.
