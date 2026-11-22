---
description: "HomeBatteryAssist naast Omnibattery, Marstek en integraties voor prijzen en zonnevoorspellingen in Home Assistant."
---

# Samenwerken met andere integraties {#working-with-other-integrations}

HomeBatteryAssist is gebouwd om batterijen zelf aan te sturen. In deze fase van de ontwikkeling stuurt het nog niets aan, uit veiligheid en zodat het kan naast elke batterij- of energie-integratie draaien (bijvoorbeeld Omnibattery) zonder die in de weg te zitten.

## Sensoren {#sensors}

De sensoren hebben een vaste betekenis en kunnen door andere integraties en add-ons worden gebruikt: *Netvermogen* (+ afname / − teruglevering), *Netafname*, *Teruglevering*, *PV-vermogen*, *Huisverbruik*, de batterijsensoren en het *Batterijplan*.

**Planfasen.** Vier sensoren vertellen wat het plan nu en hierna doet: *Fase ontladen*, *Fase laden (net)*, *Fase laden (zon)* en *Fase alleen net* (batterijen in rust, het huis op het net). Hun state is *Nu bezig*, *Gepland* of *Niet gepland*; de attributen geven de huidige en de volgende fase: begin, einde, minuten, kWh (bij de lopende fase: wat er vanaf nu nog over is), gemiddelde prijs (afnameprijs; terugleverprijs bij laden met zon), waarom in gewone taal, en de kWh per batterij. Elk batterijapparaat heeft de drie batterijfasen met een eigen aandeel (het plan geldt voor alle batterijen samen en wordt naar capaciteit over ze verdeeld). Handig voor automatiseringen, bijvoorbeeld "stuur me een melding als het laden van het net begint" of "start de vaatwasser in een fase van laden met zon".

**Uitleg plan.** De sensor *Uitleg plan* zegt in zijn state wat de batterijen nu doen, tot wanneer, de prijs nu en de drempelprijzen (kort: een state bevat hooguit 255 tekens); zijn attributen bevatten de volledige *Nu*-regel met de reden, de volgende verandering, het plan in één regel, de zon, de goedkoopste gepubliceerde prijs en de drempels als getallen (*Gebruiken loont boven*, *Laden loont onder*; alleen bij arbitrage) — handig voor een Markdown-kaart. Zie [Planning](planning.md#explanation).

**Volgt opdracht niet.** Elke echte batterij heeft een probleem-sensor die aan staat zolang de batterij de opdracht van de integratie die haar aanstuurt niet volgt, zonder verklaring (zie [Meten](measuring.md#does-the-battery-follow-its-command)); attributen: de opdracht, het vermogen van de batterij, de reden als het verklaarbaar is, en sinds wanneer.

**Testbesturing.** Het apparaat van elke echte batterij heeft ook de [testbesturing](architecture.md#control-layer-built-not-active) (knoppen *Test: laden / ontladen / stoppen*, *Testvermogen*, *Testduur*, status *Testbesturing*; zie [Meten](measuring.md#test-control-switched-off-for-now)). In deze fase staat die uit: de knoppen versturen niets.

## Acties {#actions}

| Actie | Wat het doet |
|---|---|
| `homebatteryassist.recalculate` | Bereken de voorspellingen en plannen nu opnieuw (ook de knop *Herbereken*). |
| `homebatteryassist.import_history` | Importeer eenmalig het verbruik uit het verleden uit de statistieken van Home Assistant. |
| `homebatteryassist.adjust_forecast` / `clear_forecast_adjustments` | Pas de verbruiksvoorspelling aan voor een periode (bijvoorbeeld een feest of een vakantie). |
| `homebatteryassist.set_forecast_correction` / `reset_forecast_accuracy` | Beheer de geleerde correcties op de voorspellingen. |
| `homebatteryassist.set_plan_mode` | Kies de planmodus: een ingebouwde of een eigen planner (`custom_<key>`). |
| `homebatteryassist.exclude_consumption_days` | Laat ongewone dagen buiten wat de voorspellingen leren, of neem ze terug. |

`import_history`, `set_forecast_correction`, `reset_forecast_accuracy`, `set_plan_mode` en `exclude_consumption_days` wijzigen instellingen of de geschiedenis: alleen een beheerder kan ze aanroepen. De voorspelling aanpassen en herberekenen kan iedere gebruiker (ook vanuit het dashboard).

## Reparaties {#repairs}

Onder **Instellingen → Reparaties** meldt HomeBatteryAssist: sensoren die het gebruikt maar die de recorder van Home Assistant overslaat (`recorder: exclude:`), omdat hun geschiedenis niet kan worden geïmporteerd of gebruikt om het verleden aan te vullen; en een oude opslagdatabase die bij het verhuizen een half uur niet bereikbaar was (zie [Opslag](#storage)). De melding verdwijnt zodra het is opgelost.

## Gebeurtenissen (events) {#events}

`homebatteryassist_forecast_updated` (na elke voorspellingsronde) en `homebatteryassist_decision` (elke uitgelegde beslissing).

## Waarom deed het dat? Logging {#why-did-it-do-that-logging}

- Sensor **Laatste beslissing**: een korte uitleg in jouw taal van de laatste beslissing of opvallende verandering; het attribuut `recent` bevat de laatste 10. Het dashboard toont ze ook.
- **Diagnostiek**: Instellingen → Apparaten & diensten → HomeBatteryAssist → ⋮ → *Diagnostische gegevens downloaden* geeft de configuratie en de toestand van elke module, handig als je een probleem meldt.
- **Technische logging** per module, bijvoorbeeld in `configuration.yaml`:

  ```yaml
  logger:
    logs:
      custom_components.homebatteryassist: info               # decisions
      custom_components.homebatteryassist.engine.forecast: debug    # forecast details
      custom_components.homebatteryassist.engine.devices.meters.discovery: debug # directly read meters
      custom_components.homebatteryassist.engine.own_modules: debug  # own modules
  ```

## Meldingen {#notifications}

Kies in de instellingen over welke beslissingen je een melding wilt krijgen — wijzigingen in het plan, nieuwe prijzen of een gewijzigd bereik van de voorspelling, fasebeveiliging / limieten / piekafvlakking, volledige oplaadbeurten, een weggevallen of herstelde meting, een onverwacht zonne-overschot of -tekort, een batterij die [haar opdracht niet volgt](measuring.md#does-the-battery-follow-its-command) — en stuur ze naar notify-diensten (bijvoorbeeld de companion-app) en/of als melding in Home Assistant.

**Virtuele batterijen** zeggen dat altijd in hun naam (bijvoorbeeld *Marstek Venus 1 (virtueel)*): HomeBatteryAssist voegt het toe als de naam het niet al doet.

## Opslag {#storage}

HomeBatteryAssist bewaart zijn gegevens in de map `.storage` van Home Assistant. De twee grote delen, de verbruiksgeschiedenis (28 dagen) en de voorspelnauwkeurigheid, worden elke keer helemaal geschreven als JSON-bestanden van ongeveer 0,7 MB. Onder **Instellingen → Opslag** kun je ze in plaats daarvan in een database bewaren; dan wordt alleen geschreven wat veranderd is, wat een SD-kaart veel minder laat slijten:

| Opslag | |
|---|---|
| **JSON-bestanden** (standaard) | Zoals het altijd was. |
| **SQLite** | Een eigen bestand, `/config/homebatteryassist/homebatteryassist.db`. Niets in te stellen. |
| **MySQL / MariaDB** (niet getest) | Een server, via een URL, bijv. `mysql://gebruiker:wachtwoord@core-mariadb/homebatteryassist?charset=utf8mb4` (de MariaDB-add-on). Maak de database eerst aan. |
| **PostgreSQL** (niet getest) | Een server, via een URL, bijv. `postgresql://gebruiker:wachtwoord@host/homebatteryassist`. Maak de database eerst aan. |

Als je de keuze wijzigt, verhuizen de gegevens bij de volgende start mee: van de JSON-bestanden naar de database en terug, of van de ene database naar de andere. Een server wordt gecontroleerd als je de instelling opslaat. Is de database bij een start niet bereikbaar, dan wacht HomeBatteryAssist en probeert het opnieuw (Home Assistant herhaalt de setup) in plaats van verder te gaan met een oude kopie; mislukt het schrijven terwijl het draait, dan blijft alles bewaard in het JSON-bestand en gaat het bij de volgende start alsnog naar de database. Een server wordt alleen opnieuw gecontroleerd als je de opslaginstelling wijzigt, dus een server die plat ligt houdt andere instellingen nooit tegen. Is de oude database voorgoed weg, kies dan een andere opslag: is die een half uur onbereikbaar, dan gaat HomeBatteryAssist verder met de JSON-kopie (van toen de gegevens naar die database gingen) en een reparatiemelding zegt dat. De URL staat niet in de diagnostiek-download.
