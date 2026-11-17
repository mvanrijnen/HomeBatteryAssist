# Samenwerken met andere integraties {#working-with-other-integrations}

In deze fase van de ontwikkeling stuurt HomeBatteryAssist niets aan, dus het kan naast elke batterij- of energie-integratie draaien (bijvoorbeeld Omnibattery) zonder die in de weg te zitten.

## Sensoren {#sensors}

De sensoren hebben een vaste betekenis en kunnen door andere integraties en add-ons worden gebruikt: *Netvermogen* (+ afname / − teruglevering), *Netafname*, *Teruglevering*, *PV-vermogen*, *Huisverbruik*, de batterijsensoren en het *Batterijplan*.

**Planfasen.** Vier sensoren vertellen wat het plan nu en hierna doet: *Fase ontladen*, *Fase laden (net)*, *Fase laden (zon)* en *Fase alleen net* (batterijen in rust, het huis op het net). Hun state is *Nu bezig*, *Gepland* of *Niet gepland*; de attributen geven de huidige en de volgende fase: begin, einde, minuten, kWh, gemiddelde prijs (afnameprijs; terugleverprijs bij laden met zon), waarom in gewone taal, en de kWh per batterij. Elk batterijapparaat heeft de drie batterijfasen met een eigen aandeel (het plan geldt voor alle batterijen samen en wordt naar capaciteit over ze verdeeld). Handig voor automatiseringen, bijvoorbeeld "stuur me een melding als het laden van het net begint" of "start de vaatwasser in een fase van laden met zon".

## Acties {#actions}

| Actie | Wat het doet |
|---|---|
| `homebatteryassist.recalculate` | Bereken de voorspellingen en plannen nu opnieuw (ook de knop *Herbereken*). |
| `homebatteryassist.import_history` | Importeer eenmalig het verbruik uit het verleden uit de statistieken van Home Assistant. |
| `homebatteryassist.adjust_forecast` / `clear_forecast_adjustments` | Pas de verbruiksvoorspelling aan voor een periode (bijvoorbeeld een feest of een vakantie). |
| `homebatteryassist.set_forecast_correction` / `reset_forecast_accuracy` | Beheer de geleerde correcties op de voorspellingen. |
| `homebatteryassist.set_plan_mode` | Kies de planmodus: een ingebouwde of een eigen planner (`custom_<key>`). |

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

Kies in de instellingen over welke beslissingen je een melding wilt krijgen — wijzigingen in het plan, nieuwe prijzen of een gewijzigd bereik van de voorspelling, fasebeveiliging / limieten / piekafvlakking, volledige oplaadbeurten, een weggevallen of herstelde meting, een onverwacht zonne-overschot — en stuur ze naar notify-diensten (bijvoorbeeld de companion-app) en/of als melding in Home Assistant.

**Virtuele batterijen** zeggen dat altijd in hun naam (bijvoorbeeld *Marstek Venus 1 (virtueel)*): HomeBatteryAssist voegt het toe als de naam het niet al doet.
