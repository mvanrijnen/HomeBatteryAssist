# Planning (advies) {#planning-advice}

HomeBatteryAssist plant wat de batterijen het beste kunnen doen binnen het [planningsvenster](forecasting.md#planning-window). **Voorlopig is dat advies**: in deze fase van de ontwikkeling wordt geen echte batterij aangestuurd; virtuele batterijen volgen het plan, als simulatie. Het plan is zo opgezet dat het 1-op-1 batterijopdrachten kan worden.

## Planmodi {#plan-modes}

Elke planmodus is een [planner (planningsmodule)](modules.md); ze worden allemaal elke ronde berekend, met de verwachte besparing vergeleken met geen batterij:

- **Minder verbruik dan voorspeld**: gepland ontladen gaat niet verder dan het huis nu nodig heeft, dus batterijstroom gaat nooit het net op tenzij het plan die teruglevering koos.
- **Meer of minder zon dan verwacht**: in elke modus volgen de batterijen het zonne-overschot dat er echt is — een onverwacht overschot wordt bovenop het plan opgeslagen, ontbrekende zon wordt niet uit het net gehaald. Zie [Als de zon afwijkt van de voorspelling](#when-the-sun-differs-from-the-forecast).
- **Nul op de meter (NOM)**: laden met overtollige zonnestroom, het huis voeden bij een tekort — niet de uitgesloten apparaten (bijv. een laadpaal) en, als dat aanstaat, niet willekeurige [korte pieken](measuring.md#short-peaks).
- **Arbitrage** (eigen gebruik): laden als stroom goedkoop is, het huis voeden als stroom duur is.
- **Arbitrage volledig**: zoals arbitrage, maar mag ook ontladen naar het net als de terugleverprijs dat de moeite waard maakt.
- **Tijdvakken**: je eigen tijdvakken (dagen, tijden, laden/ontladen/niets doen, vermogen, tot een laadniveau), daarbuiten nul op de meter.
- **Handmatig**: een vast laad- of ontlaadvermogen.
- **Je eigen planner**: zie [Modules](modules.md).

Kies de modus in de instellingen, op het dashboard of met de actie `set_plan_mode`. HomeBatteryAssist controleert elk plan achteraf (vermogen, fasen, laadniveau, prijsregels) — zie [het laatste woord](modules.md#homebatteryassist-keeps-the-final-say).

## Als de zon afwijkt van de voorspelling {#when-the-sun-differs-from-the-forecast}

Een plan wordt gemaakt met de voorspelde zonnestroom en het voorspelde verbruik per tijdvak. Doet de zon iets anders — een wolk, of een zonnige periode die niemand voorspelde — dan volgen de batterijen wat er **echt gemeten** wordt, niet de voorspelling.

HomeBatteryAssist vergelijkt het **overschot** nu (PV − huis − uitgesloten apparaten: wat de batterijen zouden kunnen opslaan) met het **verwachte** overschot voor dit uur (de zonvoorspelling, gecorrigeerd, min de verbruiksvoorspelling):

| | Meer zon dan verwacht | Minder zon dan verwacht |
|---|---|---|
| **Wanneer** | minstens **300 W** over, en minder dan de helft daarvan was voorspeld | minstens **300 W** voorspeld, en er is minder dan de helft van over |
| **Nul op de meter** | opgeslagen, zoals elk overschot | minder op te slaan; bij een tekort leveren de batterijen het huis stroom uit wat ze hebben |
| **Arbitrage en andere plannen per tijdvak** | **bovenop** het geplande vermogen opgeslagen — nooit meer dan het overschot, dus nooit uit het net | het deel van gepland laden dat **van de zon** moest komen, wordt alleen geladen voor zover het overschot er echt is: het net vult de ontbrekende zon niet aan; gepland laden **uit het net** gaat door |
| **Een geplande ontlading** | gevolgd zoals gepland | gevolgd zoals gepland |
| **Waarom** | na **5 minuten**: *Onverwacht zonne-overschot* | na **5 minuten**: *Minder zon dan verwacht* |

!!! example "Voorbeeld"
    Arbitrage plande tussen 12:00 en 13:00 te laden met 1.000 W zonnestroom.

    - **Een wolk**: er is maar 200 W over. De batterij laadt 200 W — niet 1.000 W waarvan 800 W uit het net.
    - **Meer zon**: er is 2.500 W over terwijl 1.000 W voorspeld was. De batterij laadt 2.500 W (voor zover hij kan en niet vol is).
    - Had het plan 2.000 W geladen bij een lage prijs, waarvan 800 W van de zon, dan wordt dat bij de wolk 1.200 W uit het net + 200 W van de zon.

Wat er daarna gebeurt:

1. **Meteen**: de batterijen reageren bij hun volgende ronde (standaard elke 5 s). Alleen het bericht in *Waarom* wacht, zodat een voorbijtrekkende wolk of opklaring geen bericht geeft.
2. **Na 5 minuten**: *Waarom* meldt het — hoeveel er over is, wat er voorspeld was, en wat het betekent voor de batterijen. Kan ook als [melding](integration.md#notifications) worden verstuurd (soort *Onverwacht zonne-overschot of -tekort*).
3. **Elk kwartier**: het plan wordt opnieuw berekend met de echte vulling, zodat een batterij die voller of leger is dan gepland een passend plan krijgt (bijv. minder laden uit het net vannacht).
4. **Als het voorbij is** (10 minuten zonder): een tweede bericht geeft de energie die over was en hoeveel er voorspeld was.
5. **Achteraf**: de [PV-correctie](forecasting.md#pv-correction) vergelijkt de voorspelling met wat er gemeten is en stelt voorspellingen bij die steeds afwijken.

Beide waarden zijn in te stellen onder **Instellingen → Zonvoorspelling**: *Meer of minder zon dan verwacht: vanaf dit verschil* (standaard 300 W) en *Meer of minder zon dan verwacht: melden na* (standaard 5 min). Hiervoor zijn een gemeten [PV-bron](measuring.md) en een zonvoorspelling nodig; zonder die wordt een plan gevolgd zoals het is.

In deze ontwikkelfase doen de [virtuele batterijen](measuring.md#virtual-batteries) dit; je echte batterijen worden aangestuurd door hun eigen integratie. Zodra HomeBatteryAssist batterijen aanstuurt, gebruikt het dezelfde regel.

## Regels en grenzen {#rules-and-limits}

- **Max. cycli per dag** voor arbitrage, om de batterijen te sparen.
- **Je eigen regels**: een reserve-laadniveau (noodstroom), max. laad-/ontlaadvermogen van alle batterijen samen, een doelvermogen op het net voor nul op de meter, pas ontladen vanaf een prijs, alleen van het net laden tot een prijs, een minimale arbitragemarge en een laadhysterese.
- **Warme batterijen**: met een optionele temperatuursensor per batterij gebruiken de plannen minder vermogen boven een temperatuurgrens.
- **Negatieve prijzen**: laden als de afnameprijs negatief is, ruimte maken vóór een negatieve terugleverprijs.
- **Nachtreserve**: vanaf de avond (de zon is weg) tot de zon weer op is (volgens de PV-voorspelling) worden de batterijen niet onder dit laadniveau ontladen. Arbitrage laadt daarvoor zo nodig van het net op het goedkoopste moment vóór zonsopgang; nul op de meter houdt het alleen vast. Zonder PV-voorspelling doet het niets.
- **Piekafvlakking** op de totale afname van het net: het plan houdt energie achter de hand voor pieken; virtuele batterijen vlakken ze live af. Met een **piekreserve** ontladen de batterijen alleen voor de afname boven de piekgrens zodra ze onder dat laadniveau zitten.
- **Fasegrenzen**: het plan laat een fase nooit boven de hoofdzekering uitkomen (met een instelbare veiligheidsmarge). Het aandeel van elke fase wordt geleerd uit je geschiedenis.
- **Fasebeveiliging** (virtuele batterijen): als een fase overbelast is, halen batterijen op die fase binnen enkele seconden belasting eraf. De belasting per fase is de **stroom** (wat de hoofdzekering ziet): gemeten als de meter die doorgeeft (een SMA Home Manager doet dat, met spanning en arbeidsfactor), anders vermogen / (gemeten spanning × arbeidsfactor), anders vermogen / 230 V. Fasebeveiliging en piekafvlakking kunnen niet door een [onderschepper](#interceptor-your-last-say) ongedaan worden gemaakt. Zonder netmeting (meter 10 s weg) doen de batterijen niets tot die terug is; *Waarom* meldt dat.
- **Verdeling over meerdere batterijen**: zo weinig mogelijk batterijen op een zinnig minimumvermogen, in balans gehouden.

## Begrenzing teruglevering (PV-omvormers) {#export-limit-pv-inverters}

Als het zonne-overschot niet meer in de batterijen kan, gaat het naar het net. Bij een negatieve terugleverprijs kost dat geld; en een netbeheerder kan de teruglevering begrenzen. De sensor **Max. teruglevering** op het apparaat *Netaansluiting* zegt hoeveel er nu teruggeleverd mag worden:

- **0 W** — niet terugleveren, want het levert geen geld op: de terugleverprijs van het tarief (bij een dynamisch contract de marktprijs min de opslag van de leverancier) min de **terugleverkosten** van je contract (instelling *Terugleverkosten*, bijv. de terugleverkosten of -boete van een vast contract) ligt onder de *grensprijs* (standaard 0). Dus: een zeer lage of negatieve prijs, of een vast contract met hogere terugleverkosten dan het oplevert, betekent niet terugleveren. De batterijen slaan nog op wat ze kunnen; de omvormers zouden niet meer leveren dan huis en batterijen gebruiken. *Niet terugleveren als het te weinig oplevert* zet dit uit.
- **altijd 0 W** met de instelling **Nooit terugleveren** (optioneel): terugleveren wordt helemaal gestopt, wat de prijs ook is;
- **een vaste maximum** (instelling *Vaste maximale teruglevering*, bijv. de grens van de netbeheerder; 0 = geen);
- anders het **meeste dat teruggeleverd kan worden**: het maximum van de netaansluiting (fasen × zekering × 230 V), of minder als bij elke PV-bron de *automaat van de omvormer* is ingevuld (A per fase × 230 V, × 3 op alle fasen; in te stellen per PV-bron) — dan niet meer dan door de automaten van de omvormers kan, bijv. een 3-fase omvormer op 3 × 20 A = 13,8 kW bij een aansluiting van 3 × 25 A (17,25 kW). Niet begrensd.

Attributen: *begrensd*, de reden, de grens als stroom per fase, de terugleverprijs, de teruglevering nu, wat nu en vandaag begrensd zou worden, en per PV-bron wat de omvormer-driver zou sturen. Met een [tweeling](measuring.md#twin-of-a-real-battery) wordt de teruglevering geteld zoals met de tweeling in plaats van de echte batterij.

**Vooruit:** als het plan duidelijk teruglevering verwacht terwijl terugleveren geld kost (of minder oplevert dan de grensprijs), zodat terugleveren gestopt zou worden (minstens een uur, minstens 0,5 kWh die de batterijen niet kunnen opslaan, bijv. een zonnige middag met negatieve prijzen), meldt *Waarom* dat één keer vooraf: van wanneer tot wanneer, de laagste netto terugleverprijs en de kWh; het attribuut *verwachte begrenzingen* van de sensor toont deze periodes.

**Geen garantie op nul teruglevering:** een grens wordt achteraf gevolgd (een meting, de reactie van de omvormer, voorbijtrekkende wolken), dus af en toe wordt er altijd even iets teruggeleverd.

**Wat een omvormer zou krijgen.** Een Sunny Home Manager begrenst zelf de *teruglevering*, dus hij krijgt de grens voor teruglevering (bijv. 0 W). Een losse omvormer (SunSpec, SMA Modbus) begrenst zijn *opwek*: hij mag leveren wat huis en batterijen nu gebruiken plus de toegestane teruglevering (PV + net + grens), dus bij 0 W teruglevering krijgt het huis nog steeds zonnestroom. Plus wat de echte batterijen bovenop hun huidige laden nog zouden kunnen opnemen (anders krijgt een batterij met eigen nul-op-de-meter-sturing nooit meer). Met meerdere van zulke omvormers wordt dat verdeeld naar wat elk nu levert (een beschaduwde kan geen groter deel gebruiken), elk hooguit zijn automaat, de rest naar de andere. Het attribuut *Opwekgrens (omvormers)* van de sensor toont het totaal.

**In deze fase wordt niets naar een omvormer gestuurd.** *Waarom* meldt wanneer de teruglevering begrensd zou worden (tot hoeveel, waarom, hoeveel minder de omvormers zouden leveren) en wanneer dat voorbij is (minuten, kWh niet teruggeleverd, wat dat waard was tegen de terugleverprijs). Instellingen, sectie *Begrenzing teruglevering (PV-omvormers)*. Welke omvormer begrensd zou kunnen worden kies je per PV-bron (*Omvormer-driver*, *Adres voor de driver*: het IP-adres van het apparaat waarmee de driver praat — met een Sunny Home Manager het adres van de Home Manager, hetzelfde voor elke SMA-omvormer erachter; anders dat van de omvormer) — zie [Drivers](drivers.md#pv-inverters--enginedevicesinverters).

**Mogelijk vermogen.** Een PV-bron kan een sensor krijgen met wat hij nu zou kunnen leveren (*Mogelijk vermogen*, bijv. een register van een SMA-omvormer, ingelezen met de [Modbus-integratie](https://www.home-assistant.io/integrations/modbus/) van Home Assistant; het register verschilt per model). Waar dat hoger is dan het gemeten vermogen, wordt PV tegengehouden: de geschiedenis, de PV-correctie en de nauwkeurigheid van de voorspelling leren dan van wat de zon gaf (niet van het begrensde vermogen), en *Max. teruglevering* toont de PV die nu wordt tegengehouden. Het huisverbruik blijft gemeten.

## Periodiek volladen {#periodic-full-charge}

Per batterij (voor de kalibratie van het batterijbeheer), om de zoveel dagen, op het goedkoopste moment, eventueel op een voorkeursdag van de week en bij voorkeur met zonnestroom; batterijen laden tegelijk vol als de netaansluiting dat toelaat. Het volladen wordt vóór het plannen ingepland en altijd door de eindcontrole van HomeBatteryAssist aan het plan toegevoegd, welke planner ook gekozen is (geen prijsregel houdt het tegen): laadniveau, net en kosten van het plan rekenen ermee, en wat daarna niet meer past wordt niet geladen.

## Reactie op de meter {#reaction-on-the-meter}

Instellingensectie *Reactie op de meter*: de batterijen worden **elke 5 seconden** (instelbaar, 1–60 s) bijgestuurd op de netmeter, standaard op het **gemiddelde over die ronde**, zodat één uitschieter niets stuurt. Met **Direct reageren op een grote sprong** (standaard aan, 1000 W) krijgt een oven of laadpaal die aangaat meteen een extra ronde. Op fase-overbelasting en de piekgrens wordt altijd direct gereageerd. Elke seconde zou nauwelijks iets opleveren: de batterijen doen er zelf 1–2 seconden over, en een paar seconden vertraging bij een sprong van 2 kW is ongeveer 2 Wh. Als aansturing later wordt aangezet, gaat er hoogstens elke 5 seconden een nieuw vermogen naar een batterij; naar niets doen gaan wordt nooit tegengehouden; een wissel tussen laden en ontladen houdt zich aan dezelfde 5 seconden en dode band (geen heen-en-weer rond 0 W). Voorlopig stuurt dit de virtuele batterijen.

## Onderschepper (jouw laatste woord) {#interceptor-your-last-say}

Voordat een opdracht naar een batterij zou gaan, krijgt de gekozen **onderschepper**-[module](modules.md#interceptor--enginecontrolinterceptorsbasepy) het voorstel per batterij — met de batterijen, fasen, het net, de prijzen en het plan — en mag die het goedkeuren, **beperken** (minder vermogen, zelfde richting), **tegenhouden** (0 W) of de batterij **vrijgeven** (terug naar haar eigen aansturing); wat wordt tegengehouden kunnen de andere batterijen overnemen. Hij kan alleen onderscheppen, nooit meer vragen. Daarna komt de eigen eindcontrole van HomeBatteryAssist (fasegrenzen, vermogen en laadniveau), die altijd wint. Standaard geen (instellingensectie *Planning*); *Waarom* en het overzicht vertellen wat hij tegenhoudt of beperkt. Voorlopig werkt hij op de virtuele batterijen.

## Uitleg {#explanation}

Het plan wordt in gewone taal uitgelegd, als periodes — wat er gebeurt tot wanneer, en waarom — en vergeleken met geen batterij, bijv.:

> *Tot 17:00 ontladen de batterijen niet en draait het huis op het net, omdat stroom nu niet duur genoeg is (€ 0,31 per kWh): ze bewaren hun energie voor ma 17:00-20:00, als stroom € 0,46 per kWh kost.*

Wat elke echte batterij uit zichzelf doet, wordt ook als periodes uitgelegd — sinds wanneer ze laadt of levert, waarmee (zonnestroom of het net), tot wanneer dat naar verwachting doorgaat en wat er gebeurt als ze stopt — en of dat bij het plan past.

## Plancontrole {#plan-check}

Achteraf wordt het plan per dag vergeleken met wat er echt gebeurde (dashboard, tab *Rendement*).

**Plan gevolgd**: per kwartier hoe dicht het vermogen van de batterijen bij hun deel van het plan lag (100 % = precies; niets doen zoals gepland telt als gevolgd), apart voor de **virtuele** en de **echte** batterijen; het plan geldt voor alle batterijen samen, het deel van elke groep is haar deel van de capaciteit. Per dag in de plancontrole en over de afgelopen 7 dagen op het tabblad *Nauwkeurigheid*.

- **Virtuele batterijen** volgen het plan: lager betekent dat ze tegen een grens aanliepen (vol, leeg, een fase) of dat de zon afweek van de voorspelling.
- **Echte batterijen** worden in deze fase door hun eigen integratie aangestuurd: hun cijfer laat zien hoe dicht die bij het plan van HomeBatteryAssist komt.
