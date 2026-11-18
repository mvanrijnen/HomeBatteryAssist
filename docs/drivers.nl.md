# Drivers: een apparaat aansluiten {#drivers-connecting-a-device}

**Drivers** verbinden HomeBatteryAssist met fysieke *apparaten*: batterijen en meters (laag 1, `engine/devices/`, zie [Architectuur](architecture.md)). Al het andere dat je kunt verwisselen — planners, verbruiksvoorspellers, prijsbronnen, tarieven, bronnen voor PV-voorspellingen — is een [module](modules.md).

Drivers zijn onderdeel van de integratie: een nieuwe driver wordt aan de code toegevoegd en via een pull request met iedereen gedeeld.

## Regels {#rules}

- Voorlopig **leest** een driver **alleen**: states en registers van Home Assistant, een lokale API die alleen lezen toestaat, of gegevens die een apparaat toch al uitzendt. Hij wijzigt nooit een instelling en opent nooit een verbinding die zou kunnen concurreren met de eigen integratie van het apparaat (een Marstek Venus staat bijvoorbeeld maar één Modbus TCP-client toe).
- Batterijdrivers *beschrijven* al hoe een batterij wordt aangestuurd (schrijfmethoden); in deze fase van de ontwikkeling roept HomeBatteryAssist die nog niet aan.
- Markeer een driver pas als **geverifieerd** nadat je hem op een echte installatie hebt getest.

## Batterijen — `engine/devices/batteries/` {#batteries-enginedevicesbatteries}

Een batterijdriver bestaat uit twee delen (`base.py`):

1. **Model** — wat de batterij *is*, via overerving **merk → typereeks → type**:

   ```
   marstek/__init__.py     class Marstek(BatteryModel)          brand = "Marstek"
   marstek/venus.py        class MarstekVenus(Marstek)          range = "Venus"
   marstek/venus_e_v3.py   class MarstekVenusEV3(MarstekVenus)  type = "Venus E v3", 5.12 kWh, 2500 W, …
   ```

   Een type legt alleen vast wat het zeker weet: capaciteit, laad-/ontlaadvermogen, bruikbaar deel, nominale cycli, garantie, en de modelnamen die integraties ervoor melden (`models`). Als een batterij wordt gekoppeld, zijn dit beginwaarden voor wat de integratie ervan niet vertelt. Voeg een nieuw type toe aan `MODELS` in `__init__.py`.
2. **Lezer (reader)** — hoe de batterij wordt *uitgelezen*, één per integratie in `integrations/`: het `profile` herkent de batterijen van die integratie (sensor voor laadniveau en vermogen, beginwaarden) en `telemetry` voegt live details toe (temperatuur, spanningen, celspanningen, cycli, energie vandaag, rendement). Een lezer geeft ook aan of hij **als meter van de batterij dient** (`is_meter`): of zijn integratie het eigen vermogen van de batterij geeft. Omnibattery en Marstek Modbus doen dat (`ac_power`); een batterij waarvan de integratie dat niet doet, heeft een externe meter nodig. Voeg een nieuwe lezer toe aan `READERS` in `integrations/__init__.py`.

**Batterijmeter:** een batterij kan ook een externe meter krijgen (instelling *Batterijmeter* in het formulier van de batterij, met het adres ervan): het vermogen daarvan (+ de batterij in = laden) wordt dan gebruikt in plaats van de vermogenssensor — voor een batterij waarvan de integratie niet als meter dient, of als controle. Heeft de meter even geen waarde, dan telt de vermogenssensor weer.

Eén batterijtype kan via meerdere integraties worden uitgelezen; het model en de lezer worden los van elkaar gekozen. `template.py` laat beide zien. De **virtuele batterij** (`virtual.py`) is een gesimuleerd apparaat dat het plan volgt.

### Directe batterijdrivers — voorbereid, niet gebruikt {#direct-battery-drivers--prepared-not-used}

Naast de lezers (die via een andere integratie gaan) kan elk merk een **directe driver** hebben: de eigen verbinding van HomeBatteryAssist met de batterij, voor de dag dat het batterijen zelf aanstuurt in plaats van bijvoorbeeld Omnibattery. Ze zijn **uitgeschakeld** (`enabled = False`): nooit aangeboden, maken nooit verbinding, en hun schrijfmethoden worden nooit aangeroepen. Veel batterijen staan maar één verbinding toe, en die is nu van een andere integratie.

Generieke basissen in `direct/` (een merk voegt alleen zijn eigen specifieke zaken toe): `modbus_driver.py` (een registermap als gegevens, uitgelezen in blokken die nooit over ongedefinieerde registers heen gaan; een eigen kleine Modbus TCP-client in `engine/devices/transports/modbus_tcp.py`), `http_driver.py` (lokale JSON-API) en `mqtt_driver.py` (via de MQTT-integratie van Home Assistant).

| Merk | Driver | Types (modellen) | Verbinding |
|---|---|---|---|
| Marstek | `marstek/venus_direct_modbus.py` | Venus E v2, Venus E v3, Venus A, Venus D | Modbus TCP |
| Anker | `anker/solarbank_direct_modbus.py` | SOLIX Solarbank Max AC, XE AC, E5000 Pro, Max, XE | Modbus TCP |
| Huawei | `huawei/sun2000_direct_modbus.py` | LUNA2000 (via de SUN2000-omvormer) | Modbus TCP |
| Zendure | `zendure/solarflow_direct_http.py` | SolarFlow 800, 800 Plus, 800 Pro, 1600 AC+, 2400 AC+, 2400 Pro | lokale HTTP |
| Sessy | `sessy/sessy_direct_http.py` | Sessy thuisbatterij | lokale HTTP |
| Indevolt | `indevolt/flex_direct_http.py` | SolidFlex/PowerFlex 1200, 2000, 3000, SolidFlex 3600, BK1600 | lokale HTTP |
| Hoymiles | `hoymiles/smiles_direct_mqtt.py` | MS-A2, HiBattery 1920 AC, 4020 X, 4020 AC | MQTT |

Geen ervan is al op een apparaat geverifieerd. De apparaatfeiten (registers, endpoints, schalen, tekens, stuurvolgordes) komen uit de drivers van Omnibattery (GPL-3.0) en, waar beschikbaar, uit de eigen documentatie van de fabrikanten — alleen feiten; de code is van HomeBatteryAssist zelf. Elke driver geeft ook aan hoe hij moet worden aangestuurd (`refresh_s`, `min_interval_s`, `deadband_w`, `idle_is_release`, limieten), wat de stuurlaag afdwingt — zie [Architectuur](architecture.md#control-layer-built-not-active).

## Meters — `engine/devices/meters/` {#meters-enginedevicesmeters}

Eén bestand per merk, die samen `direct_reading.py` gebruiken (ongeveer één keer per seconde uitlezen; een waarde ouder dan 10 s telt als onbekend):

| Bestand | Meters | Status |
|---|---|---|
| `homewizard.py` | HomeWizard P1-meter en kWh-meters (1/3 fasen), lokale API v1 | geverifieerd |
| `sma.py` | SMA Sunny Home Manager 2.0 / Energy Meter, Speedwire (alleen ontvangen) | geverifieerd |
| `shelly.py` | Shelly Pro 3EM / 3EM / EM / Pro EM, lokale API | uit de API-documentatie |
| `iammeter.py` | Iammeter WEM3080 / WEM3080T, lokale API | uit de API-documentatie |

Naast het vermogen per fase leest elke meterdriver ook de **stroom, spanning en arbeidsfactor per fase** als de meter die geeft (SMA Home Manager: stroom, spanning en arbeidsfactor, geverifieerd; HomeWizard P1: stroom en spanning; Shelly 3EM: stroom, spanning en arbeidsfactor; IAMMETER: stroom en spanning), voor de fasebeveiliging: de hoofdzekering ziet stroom, geen vermogen. `discovery.py` vindt deze meters in Home Assistant en maakt de juiste lezer aan; `__init__.py` somt ze op (`DRIVERS`). Meters kunnen ook worden uitgelezen via de sensoren van hun eigen integratie (`via_ha_integration.py`, HomeWizard P1 wordt herkend). `template.py` is een voorbeeld van een nieuwe meter. Dezelfde drivers dienen elke rol: de netaansluiting, een PV-bron (een kWh-meter op de lijn van de omvormer) en een batterij (een kWh-meter op de lijn van de batterij, zie hierboven). De rol is een instelling; de map volgt merk en type.

## PV-omvormers — `engine/devices/inverters/` {#pv-inverters--enginedevicesinverters}

Hoe het vermogen van een omvormer begrensd zou kunnen worden voor de [begrenzing van de teruglevering](planning.md#export-limit-pv-inverters). **Voorbereid, niet gebruikt**: elke driver heeft `enabled = False`, `async_set_limit` wordt nooit aangeroepen, en HomeBatteryAssist maakt in deze fase geen verbinding met een omvormer; de sensor *Max. teruglevering* toont alleen wat een driver zou sturen. `base.py` = `InverterDriver` (`points`: de instellingen die hij zou schrijven, `{limit_w}` = de grens in W; `limits`: het eigen vermogen van de omvormer of de teruglevering), `template.py` = een voorbeeld.

- `sma_home_manager.py` — SMA-omvormers met een **Sunny Home Manager 2.0** (samen in ennexOS / Sunny Portal): de grens hoort dan bij de Home Manager, die al zijn SMA-omvormers begrenst; een omvormer mag daarnaast niet rechtstreeks beschreven worden. De Home Manager (softwarepakket ≥ 2.10) is een Modbus TCP-server voor netbeheerdiensten: unit **2**, register **40016** = setpoint in % van de PMAX van de installatie. Hij houdt rekening met het huisverbruik, dus hij begrenst de **teruglevering**. Aanzetten in Sunny Portal / ennexOS: *Netbeheerdiensten via Ethernet-communicatie* en *Begrenzing van de teruglevering* (*Alleen externe setpoints uitvoeren*). Een setpoint geldt 60 minuten, daarna valt hij terug naar 100 %. De Home Manager wordt al uitgelezen als [meter](#meters-enginedevicesmeters).
- `sma_modbus.py` — oudere SMA-types (Sunny Boy TL-21, Sunny Tripower TL-10/-20/-30) **zonder** Home Manager: register **40023** = grens in % × 100 van WMax (unit 3). Het terugvallen stel je in de webinterface van de omvormer in (*Use fallback setting*); anders houdt hij de laatste grens vast.
- `sma_storage_x.py` — SMA Sunny Tripower Storage X / Sunny Island X zonder Home Manager: 40210 = 1077 (handmatig in W), 40212 = grens in W, terugvallen 41193 = 2507 met time-out 41195 (unit 3).
- `sunspec_modbus.py` — **elke omvormer met SunSpec Modbus** (SMA, Fronius, SolarEdge, Kostal, Huawei, ABB / FIMER, ...): de merkonafhankelijke registerindeling. Die begint op 40000 (`SunS`), gevolgd door een keten van modellen waarvan de adressen per apparaat verschillen; de driver loopt die keten dus af. De begrenzing gaat via model **123** (*Immediate Controls*): `WMaxLimPct` (offset 3, % van `WMax` uit model 121, geschaald met `WMaxLimPct_SF`), `WMaxLimPct_RvrtTms` (offset 5: na 60 s zonder nieuwe opdracht gaat de omvormer zelf terug naar vol vermogen) en `WMaxLim_Ena` (offset 7, 1 = aan). Adres `host[:poort][/unit]`; het unit-id verschilt per merk (SMA 126, Fronius en SolarEdge 1). Nieuwere apparaten met model 704 (SunSpec 2018 / IEEE 1547) worden nog niet ondersteund. Uit de SunSpec-specificatie. Met een Sunny Home Manager geldt de SHM-driver, niet deze.

Alles uit de documentatie van de fabrikanten en ervaringen van gebruikers, *niet geverifieerd op een apparaat*.

### SMA per type {#sma-per-type}

| Type | Driver | Begrenzing | Terugvallen als de setpoints stoppen | SunSpec |
|---|---|---|---|---|
| Elke SMA-omvormer met een **Sunny Home Manager 2.0** | `sma_home_manager` | unit 2, 40016 = % van PMAX (teruglevering) | na 60 min terug naar 100 % | — |
| Sunny Boy 3.0–6.0-1AV-40/41 | `sunspec_modbus` | model 123 `WMaxLimPct` (unit 126) | `WMaxLimPct_RvrtTms` | 1AV-41 vanaf firmware 4.00.23.R |
| Sunny Tripower 3.0–10.0-3AV-40 | `sunspec_modbus` | model 123 `WMaxLimPct` (unit 126) | `WMaxLimPct_RvrtTms` | vanaf firmware 4.00.02.R |
| Sunny Tripower CORE1 | `sunspec_modbus` | model 123 `WMaxLimPct` (unit 126) | `WMaxLimPct_RvrtTms` | vanaf firmware 3.14 |
| Sunny Boy TL-21, Sunny Tripower TL-10/-20/-30 | `sma_modbus` | 40023 = % × 100 (unit 3) | webinterface: *Use fallback setting* | nee |
| Sunny Tripower Storage X, Sunny Island X | `sma_storage_x` | 40210 = 1077, 40212 = W (unit 3) | 41193 = 2507, time-out 41195 | — |
| Sunny Tripower X (STP 12–25-50), Sunny Boy Smart Energy | — (registers nog niet gepubliceerd; SunSpec op de STP X na een firmware-update) | | | |

- **Modbus staat standaard uit**: zet het aan in de omvormer (poort 502). Het unit-id van SMA is 3; SunSpec is het SMA-unit + 123 (126).
- **Flashgeheugen**: schrijf alleen netbeheerwaarden herhaaldelijk (SunSpec model 123, de %-setpoints, 40016 van de Home Manager). Gewone instellingen zoals `WMax` (40915) staan in flash; SMA waarschuwt dat ze herhaaldelijk wijzigen het flashgeheugen kapotmaakt.
- **Mogelijk vermogen**: SMA publiceert geen register met wat de panelen nu zouden kunnen leveren; *Mogelijk vermogen* van een PV-bron heeft een eigen sensor nodig (bijv. uit het DC-vermogen per string). Een begrensde omvormer levert alleen wat gevraagd wordt.
- Bronnen: de Modbus-documenten van SMA (*SMA-Modbus-general-TI*, *SunSpecModbus-TI*, *SMAModbus-ennexOS-TI*, *SMAModbus-STPS-X-SI-X-TI*, *HM-20-Modbus-NSD-TI*, op files.sma.de) en ervaringen van gebruikers voor de TL-types.

## Nu ondersteund {#supported-now}

- **Batterijen**: Marstek Venus E v3 (model); uitgelezen via Omnibattery of Marstek Modbus (geverifieerd). Elke andere batterij kun je handmatig koppelen via de entiteiten ervan.
- **Meters**: zie de tabel hierboven.
