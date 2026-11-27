---
description: "Loont een thuisaccu bij een dynamisch energiecontract zonder salderen? Reken laden uit het net, terugleveren en zon opslaan per kWh uit."
---

# Accu-rekenhulp

!!! warning "Vanaf 1 januari 2027"
    Voor een **dynamisch contract** (prijs per uur of kwartier), **zonder salderen**, dat op 1 januari 2027 stopt. Met salderen (2026) kloppen de uitkomsten niet.

B1, B2 en Bz zijn **kale EPEX-prijzen**: zonder btw, opslag of energiebelasting. Toont je app of integratie de beursprijs inclusief btw, deel die dan eerst door 1,21.

Vul je eigen prijzen, vergoedingen van je leverancier en accu in; de uitkomsten rekenen meteen mee. Alle bedragen zijn per kWh. Er wordt niets verstuurd: de berekening draait in je browser.

Drie scenario's:

- **Net laden → zelf gebruiken:** laden als stroom goedkoop is, zelf gebruiken als hij duur is. Energiebelasting en inkoopvergoeding vallen weg (die betaal je toch); alleen verlies en slijtage tellen.
- **Net laden → terugleveren:** uit het net laden en later terugleveren. Zonder salderen betaal je btw en energiebelasting over de inkoop, maar krijg je alleen de kale beursprijs terug: dat loont bijna nooit.
- **Zon opslaan → zelf gebruiken:** je zonne-overschot kost je alleen de gemiste terugleverprijs; dat loont bijna altijd.

De slijtage per kWh is aanschafprijs ÷ (cycli × bruikbare kWh). Eén cyclus is één keer volledig laden plus ontladen, dus dit is de slijtage van één kWh die erin gaat en er weer uit komt; die tel je één keer. Reken met een realistisch aantal cycli (± 3000), niet de specificatie: bij ± 300 cycli per jaar is een accu eerder op door zijn leeftijd dan door het aantal cycli.

<div id="battery-calculator"></div>
