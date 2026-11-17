# Meten {#measuring}

## Netaansluiting en meter {#grid-connection-and-meter}

- **Netaansluiting** met 1 of 3 fasen en de grootte ervan (1x10A tot en met 3x80A).
- **Netmeter**, gekozen tijdens de installatie:
  - **rechtstreeks uitgelezen**, ongeveer eens per seconde, alleen lezen (er wordt niets aan de meter veranderd, en de eigen integratie van de meter blijft gewoon werken):
    - HomeWizard P1-meter en kWh-meters (1- en 3-fase), lokale API;
    - SMA Sunny Home Manager 2.0 / Energy Meter, Speedwire (alleen ontvangen: de meter stuurt zijn gegevens toch al over het netwerk);
    - Shelly Pro 3EM / 3EM en Shelly EM / Pro EM, lokale API *(nog niet op een apparaat gecontroleerd)*;
    - Iammeter WEM3080 / WEM3080T, lokale API *(nog niet op een apparaat gecontroleerd)*;

    Meters die al in Home Assistant zitten worden automatisch aangeboden; elk van deze meters kun je ook op IP-adres invoeren;
  - **via de sensoren van zijn integratie** (bijv. een HomeWizard P1 wordt herkend en ingevuld);
  - **je eigen sensoren** per fase: één sensor met plus/min-teken, of aparte sensoren voor afname en teruglevering; vermogen (W) of stroom (A).

Nieuwe meters worden toegevoegd als [drivers](drivers.md).

## Batterijen {#batteries}

Batterijen worden **alleen-lezen** gekoppeld via de entiteiten van hun eigen integratie. Batterijen van **Omnibattery** en **Marstek Modbus** worden herkend en ingevuld, en hun *batterijdriver* voegt temperatuur, spanningen, celspanningen, cycli, de energie van vandaag en het gemeten rendement toe; elke andere batterij kun je handmatig koppelen.

Een batterij kan optioneel een **externe meter** op zijn groep krijgen (bijv. een HomeWizard kWh-meter, rechtstreeks uitgelezen): het vermogen daarvan wordt dan gebruikt in plaats van de vermogenssensor — zie [Drivers](drivers.md).

Per batterij: laadniveau, vermogen, status, opgeslagen/bruikbare energie, tijd tot vol/leeg, geladen/ontladen energie, laatste keer volladen en gerealiseerd rendement, plus totalen over alle batterijen.

Wat een batterij door zijn eigen aansturing doet (laden, leveren, stoppen) wordt als periodes uitgelegd in *Waarom*, vergeleken met het plan — zie [Planning](planning.md#explanation).

## Virtuele batterijen {#virtual-batteries}

Gesimuleerde wat-als-batterijen (capaciteit, vermogen, grenzen voor het laadniveau, verliezen, fase) die het plan live volgen, zodat je ziet wat een (grotere) batterij zou opleveren voordat je er een koopt. Ze laten ook fasebeveiliging en piekafvlakking aan het werk zien.

## PV-bronnen en uitgesloten apparaten {#pv-sources-and-excluded-devices}

**PV-bronnen** en **uitgesloten apparaten** (bijv. een laadpaal): op één fase, op alle fasen (3-fase, gelijk verdeeld) of per fase gemeten met een sensor per fase. Een PV-bron kan ook een rechtstreeks uitgelezen meter zijn (bijv. een HomeWizard kWh-meter op de groep van de omvormer).

Een **uitgesloten apparaat** hoort niet bij het huisverbruik: het zit niet in de verbruiksvoorspelling, en **de batterij ontlaadt er nooit voor** — het net levert het (zonne-overschot wordt nog wel geladen). Zo houd je ook een grote verbruiker met een eigen vermogenssensor (een laadpaal, een sauna, een droger aan een slimme stekker) bij de batterij weg. Of uitgesloten apparaten meetellen voor de piekgrens is een aparte instelling.

**Verwarming/koeling** (optioneel; een warmtepomp, elektrische verwarming of airco): gemeten als een uitgesloten apparaat, maar het verbruik **blijft deel van het huisverbruik**. Het wordt apart vastgelegd, zodat de verbruiksvoorspelling de buitentemperatuur kan volgen. Geef het optioneel de kamertemperatuur (en een eigen buitensensor): het wordt dan een zone, die apart wordt geleerd — zie [Voorspellen](forecasting.md#outdoor-temperature-optional).

## Korte pieken {#short-peaks}

Korte, hoge pieken op willekeurige momenten (een waterkoker, een magnetron, een inductiekookplaat) hebben geen eigen sensor nodig: een **piekfilter**-[module](modules.md) herkent ze in het huisverbruik terwijl ze gebeuren. Instellingensectie *Korte pieken*, beide standaard aan:

- **Niet ontladen voor willekeurige pieken** — nul op de meter ontlaadt niet (extra) voor een herkende piek; het net levert die.
- **Willekeurige pieken niet meetellen in het gemiddelde verbruik** — hun energie wordt apart vastgelegd (`spike_w` in de historie) en buiten de verbruiksvoorspelling en de controle van de nauwkeurigheid gehouden, zodat het batterijplan er niet op rekent.

Het ingebouwde filter (*Korte pieken boven een drempel*): een stijging van minstens **2000 W** boven het gebruikelijke verbruik die binnen **5 minuten** weer voorbij is, is een piek (beide instelbaar). Zolang die duurt wordt er niet voor ontladen; duurt het langer, dan is het gewoon verbruik (bijv. een oven) en wordt het vanaf dan gevolgd — een waterkoker bovenop de oven is dan weer een piek.

Een piek die **regelmatig terugkomt** — op minstens de helft van de dagen van die dag van de week op hetzelfde uur, minstens twee keer in de afgelopen 4 weken (bijv. de koffie elke doordeweekse ochtend) — is niet willekeurig: die blijft in het gemiddelde en de batterij dekt hem.

## Huisverbruik {#house-consumption}

**Huisverbruik** = net + PV − uitgesloten apparaten − laden van de batterij, plus afname/teruglevering van het net, PV-vermogen en de belasting per fase als % van de hoofdzekering.

Het verbruik wordt als historie bewaard (28 dagen) voor de [verbruiksvoorspelling](forecasting.md#consumption); eerder verbruik kun je eenmalig importeren uit de statistieken van Home Assistant.

## Stroom per fase {#current-per-phase}

De hoofdzekering beveiligt tegen **stroom**, niet tegen vermogen: met apparaten op stand-by, laders en motoren (arbeidsfactor onder 1) loopt er meer stroom dan vermogen / 230 V doet vermoeden — 's nachts al snel 1 A op een fase die 30 W gebruikt. Daarom gebruikt HomeBatteryAssist waar het kan de stroom per fase:

- **gemeten**: een rechtstreeks uitgelezen meter die hem doorgeeft (SMA Home Manager, HomeWizard P1, Shelly 3EM, IAMMETER), of de optionele **stroomsensoren** per fase in de instellingen van de netaansluiting (bij je eigen sensoren);
- anders **vermogen / (gemeten spanning × arbeidsfactor)**, met een spanningssensor of een meter die de spanning doorgeeft;
- anders **vermogen / 230 V**.

De historie bewaart de gemeten stroom per fase; daaruit wordt per fase geleerd welke stroom er naast het vermogen loopt, en het batterijplan rekent daarmee voor de komende tijdvakken. Het eigen aandeel van de batterij wordt omgerekend met de gemeten spanning van zijn fase.
