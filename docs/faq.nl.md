---
description: "Veelgestelde vragen over HomeBatteryAssist, de Home Assistant-integratie voor thuisbatterijen, dynamische prijzen en nul op de meter."
---

# Veelgestelde vragen

## Over HomeBatteryAssist {#about}

??? question "Stuurt HomeBatteryAssist mijn batterij aan?"
    **Nog niet.** In deze ontwikkelfase leest het alleen, voorspelt het en adviseert het; de integratie die je batterij aanstuurt (bijv. Omnibattery) blijft dat ongestoord doen. Zelf batterijen aansturen is het doel: de regellaag en de beveiliging daarvan (vrijgeven bij elke fout, een watchdog, grenzen) zijn gebouwd, maar staan niet aan. Tot die tijd volgen *virtuele batterijen* het plan als simulatie, zodat je ziet wat het zou doen. Elke batterij heeft ook een [testbesturing](measuring.md#test-control-switched-off-for-now) (*Test: laden / ontladen / stoppen*) om aansturen later met de hand te testen; die staat ook uit.

??? question "Kan het naast Omnibattery of de app van mijn batterij draaien?"
    Ja. HomeBatteryAssist leest de batterij via de entiteiten van zijn integratie en maakt nooit een eigen verbinding met de batterij, dus er wordt niets verstoord. Netmeters worden alleen rechtstreeks uitgelezen als dat passief kan of via een alleen-lezen-interface waar meerdere programma's tegelijk bij mogen (HomeWizard P1 API, SMA Speedwire multicast).

??? question "Wat is een virtuele batterij?"
    Een gesimuleerde batterij die live naast je echte batterijen meedraait en de gekozen planmodus volgt, met de echte metingen van je huis: inclusief fasebeveiliging, piekafvlakking en verliezen. Hij heeft dezelfde sensoren en dashboardkaart als een echte batterij. Gebruik hem om te zien wat een (grotere of extra) batterij zou doen en opleveren, of om een planmodus veilig uit te proberen. Zijn naam eindigt altijd op "(virtueel)". Als [tweeling](measuring.md#twin-of-a-real-battery) van je echte batterij draait hij in haar plaats, zodat je het plan van HomeBatteryAssist dag voor dag kunt vergelijken met de eigen sturing van je batterij.

??? question "Welke planmodus moet ik kiezen?"
    - **Nul op de meter**: de batterij slaat je zonne-overschot op en levert het huis stroom bij een tekort; hij laadt nooit bewust uit het net en levert niet bewust terug. Eenvoudig en voorspelbaar.
    - **Arbitrage**: kostenoptimaal voor eigen gebruik; laadt ook uit het net als dat goedkoper is dan later stroom afnemen (bijv. 's nachts voor de avondpiek). Daarvoor zijn dynamische prijzen nodig.
    - **Arbitrage volledig**: als arbitrage, maar levert ook terug aan het net als de terugleverprijs dat de moeite waard maakt.

    Alle modi worden altijd doorgerekend: het tabblad **Rendement** laat zien wat elke modus zou opleveren, zodat je kunt vergelijken voordat je kiest.

## Plannen en voorspellingen {#plans}

??? question "Waarom doet de batterij nu niets?"
    Lees **Waarom** op het tabblad Overzicht: daar staat wat het plan doet tot wanneer, en waarom. Veel voorkomende redenen: de batterij is zo leeg als ingesteld (minimum of reserve), laden loont nu niet (het prijsverschil is te klein na verlies en slijtage), de energie wordt bewaard voor een duurder moment later, of een fase zit aan zijn grens.

??? question "Waarom is het geplande laden verschoven of verdwenen?"
    Het plan wordt elk kwartier opnieuw berekend (en als er nieuwe prijzen binnenkomen). Nieuwe prijzen, een andere verbruiks- of zonvoorspelling, of een andere **planmodus** veranderen het. Nul op de meter laadt nooit uit het net — na overstappen van arbitrage naar nul op de meter verdwijnt het nachtladen. *Waarom* legt elk nieuw plan uit.

??? question "Waarom houdt arbitrage energie dagenlang vast?"
    Als de prijzen later naar verwachting hoger zijn (bijv. in het weekend), is de energie dan meer waard, en is er weinig zon om de batterij bij te vullen. Prijzen verder vooruit zijn vaak *schattingen* (gestippeld in de grafieken); wijken de gepubliceerde prijzen af, dan past het plan zich aan.

??? question "Wat gebeurt er als er ineens meer of minder zon is dan voorspeld?"
    De batterijen volgen het zonne-overschot dat er echt is, niet de voorspelling. Meer zon: het overschot wordt bovenop het plan opgeslagen (nooit uit het net). Minder zon: laden dat het plan van de zon verwachtte, gebeurt alleen voor zover de zon er echt is — het net vult niet aan; gepland laden uit het net gaat door. De batterijen reageren meteen; *Waarom* meldt het na 5 minuten, en het plan wordt elk kwartier opnieuw berekend met de echte vulling. De drempel (300 W) en de wachttijd (5 min) zijn instellingen. Zie [Planning: als de zon afwijkt van de voorspelling](planning.md#when-the-sun-differs-from-the-forecast).

??? question "Wat zijn de gestippelde lijnen in de grafieken?"
    Voorspellingen en schattingen: het verwachte verbruik en de verwachte zonnestroom, het geplande laadniveau en, bij prijzen, geschatte (nog niet gepubliceerde) prijzen. Doorgetrokken lijnen zijn gemeten of gepubliceerde waarden.

??? question "Vlak na een herstart is er geen voorspelling — is er iets mis?"
    Nee. Andere integraties (prijzen, zonvoorspelling) hebben na een herstart soms een minuut nodig; HomeBatteryAssist probeert het elke minuut opnieuw en meldt pas *geen prijzen* als dat langer dan 5 minuten duurt.

??? question "Kan ik met de hand herberekenen?"
    Ja: de knop **Herberekenen** op het dashboard, de knop-entiteit, of de actie `homebatteryassist.recalculate`. Een herberekening met de hand zet altijd het actuele plan in *Waarom*.

??? question "De verbruiksvoorspelling klopt niet. Wat kan ik doen?"
    Geef het tijd: hij leert van je historie en stelt zich bij waar hij steeds afwijkt (zie *Nauwkeurigheid*). Importeer je historie ([Aan de slag, stap 7](getting-started.md#step-7-import-your-history)); voeg grote verbruikers zoals een laadpaal toe als **uitgesloten apparaat**; voeg warmtepompen en airco's toe als **verwarming/koeling** met een weerbron. Voor vakanties of logés: gebruik de **vakantiemodus** of de actie `homebatteryassist.adjust_forecast`.

## Meten {#measuring}

??? question "Het huisverbruik lijkt niet te kloppen."
    Huisverbruik = net (alle fasen) + zonnestroom − uitgesloten apparaten − batterijvermogen. Controleer of elke omvormer is toegevoegd als **PV-bron**, of de **richting van het vermogen** van de batterij goed staat (positief = laden of ontladen), en of elke sensor maar één keer gebruikt wordt.

??? question "Welke netmeter is het beste?"
    Een meter die rechtstreeks wordt uitgelezen (HomeWizard P1, SMA Home Manager, Shelly, Iammeter): ongeveer één waarde per seconde, met stroom en spanning per fase als de meter die stuurt. Sensoren van een andere integratie werken ook, maar worden minder vaak bijgewerkt.

??? question "Waarom rekent de fasebeveiliging met stroom?"
    De hoofdzekering reageert op stroom, niet op vermogen. Bij een lage arbeidsfactor (sluipverbruikers, laders) kan er over een fase meer stroom lopen dan het vermogen doet vermoeden. HomeBatteryAssist gebruikt de gemeten stroom als de meter die stuurt, anders vermogen / spanning, anders vermogen / 230 V.

## Hulp en feedback {#help}

??? question "Waar meld ik een probleem of een idee?"
    Bij de [GitHub-issues](https://github.com/mvanrijnen/HomeBatteryAssist/issues). Voeg de **diagnostische gegevens** toe (integratiepagina → ⋮ → *Diagnostische gegevens downloaden*) en eventueel een screenshot van *Waarom*.

??? question "Hoe ga ik terug naar de standaardinstellingen?"
    **Configureren → Terug naar standaardinstellingen** zet elke instelling terug; waar de prijzen en de zonvoorspelling vandaan komen blijft bewaard.

??? question "In welke talen is HomeBatteryAssist beschikbaar?"
    Engels en Nederlands: de schermen volgen de taal van je Home Assistant-profiel, en deze documentatie volgt je browser (wisselen kan bovenaan).
