# Planning (advies) {#planning-advice}

HomeBatteryAssist plant wat de batterijen het beste kunnen doen binnen het [planningsvenster](forecasting.md#planning-window). **Voorlopig is dat advies**: in deze fase van de ontwikkeling wordt geen echte batterij aangestuurd; virtuele batterijen volgen het plan, als simulatie. Het plan is zo opgezet dat het 1-op-1 batterijopdrachten kan worden.

## Planmodi {#plan-modes}

Elke planmodus is een [planner (planningsmodule)](modules.md); ze worden allemaal elke ronde berekend, met de verwachte besparing vergeleken met geen batterij:

- **Onverwacht zonne-overschot**: in elke modus slaan de batterijen ook zonnestroom op waar het plan niet op rekende — minstens 300 W over (PV − huis − uitgesloten apparaten) terwijl er voor dit uur minder dan de helft van voorspeld was — bovenop het geplande vermogen (niet meer dan het overschot, dus nooit van het net; een geplande ontlading wordt gewoon gevolgd). *Waarom* meldt het ([Voorspellen](forecasting.md#unexpected-solar-surplus)).
- **Nul op de meter (NOM)**: laden met overtollige zonnestroom, het huis voeden bij een tekort — niet de uitgesloten apparaten (bijv. een laadpaal) en, als dat aanstaat, niet willekeurige [korte pieken](measuring.md#short-peaks).
- **Arbitrage** (eigen gebruik): laden als stroom goedkoop is, het huis voeden als stroom duur is.
- **Arbitrage volledig**: zoals arbitrage, maar mag ook ontladen naar het net als de terugleverprijs dat de moeite waard maakt.
- **Tijdvakken**: je eigen tijdvakken (dagen, tijden, laden/ontladen/niets doen, vermogen, tot een laadniveau), daarbuiten nul op de meter.
- **Handmatig**: een vast laad- of ontlaadvermogen.
- **Je eigen planner**: zie [Modules](modules.md).

Kies de modus in de instellingen, op het dashboard of met de actie `set_plan_mode`. HomeBatteryAssist controleert elk plan achteraf (vermogen, fasen, laadniveau, prijsregels) — zie [het laatste woord](modules.md#homebatteryassist-keeps-the-final-say).

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

## Periodiek volladen {#periodic-full-charge}

Per batterij (voor de kalibratie van het batterijbeheer), om de zoveel dagen, op het goedkoopste moment, eventueel op een voorkeursdag van de week en bij voorkeur met zonnestroom; batterijen laden tegelijk vol als de netaansluiting dat toelaat. Het volladen wordt altijd **na** de planner ingevoegd, welke planner ook gekozen is.

## Reactie op de meter {#reaction-on-the-meter}

Instellingensectie *Reactie op de meter*: de batterijen worden **elke 5 seconden** (instelbaar, 1–60 s) bijgestuurd op de netmeter, standaard op het **gemiddelde over die ronde**, zodat één uitschieter niets stuurt. Met **Direct reageren op een grote sprong** (standaard aan, 1000 W) krijgt een oven of laadpaal die aangaat meteen een extra ronde. Op fase-overbelasting en de piekgrens wordt altijd direct gereageerd. Elke seconde zou nauwelijks iets opleveren: de batterijen doen er zelf 1–2 seconden over, en een paar seconden vertraging bij een sprong van 2 kW is ongeveer 2 Wh. Als aansturing later wordt aangezet, gaat er hoogstens elke 5 seconden een nieuw vermogen naar een batterij; een wissel tussen laden, ontladen en niets doen wordt nooit tegengehouden. Voorlopig stuurt dit de virtuele batterijen.

## Onderschepper (jouw laatste woord) {#interceptor-your-last-say}

Voordat een opdracht naar een batterij zou gaan, krijgt de gekozen **onderschepper**-[module](modules.md#interceptor--enginecontrolinterceptorsbasepy) het voorstel per batterij — met de batterijen, fasen, het net, de prijzen en het plan — en mag die het goedkeuren, **beperken** (minder vermogen, zelfde richting), **tegenhouden** (0 W) of de batterij **vrijgeven** (terug naar haar eigen aansturing); wat wordt tegengehouden kunnen de andere batterijen overnemen. Hij kan alleen onderscheppen, nooit meer vragen. Daarna komt de eigen eindcontrole van HomeBatteryAssist (fasegrenzen, vermogen en laadniveau), die altijd wint. Standaard geen (instellingensectie *Planning*); *Waarom* en het overzicht vertellen wat hij tegenhoudt of beperkt. Voorlopig werkt hij op de virtuele batterijen.

## Uitleg {#explanation}

Het plan wordt in gewone taal uitgelegd, als periodes — wat er gebeurt tot wanneer, en waarom — en vergeleken met geen batterij, bijv.:

> *Tot 17:00 ontladen de batterijen niet en draait het huis op het net, omdat stroom nu niet duur genoeg is (€ 0,31 per kWh): ze bewaren hun energie voor ma 17:00-20:00, als stroom € 0,46 per kWh kost.*

Wat elke echte batterij uit zichzelf doet, wordt ook als periodes uitgelegd — sinds wanneer ze laadt of levert, waarmee (zonnestroom of het net), tot wanneer dat naar verwachting doorgaat en wat er gebeurt als ze stopt — en of dat bij het plan past.

## Plancontrole {#plan-check}

Achteraf wordt het plan per dag vergeleken met wat er echt gebeurde (dashboard, tab *Rendement*).
