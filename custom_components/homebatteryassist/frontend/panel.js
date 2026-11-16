// HomeBatteryAssist status panel.
// Plain web component without dependencies: asks `homebatteryassist/status`
// which entities exist, then renders their live states from `hass.states`.

const TEXT = {
  en: {
    title: "HomeBatteryAssist",
    flows: "Now",
    pv: "Solar",
    expected: "expected",
    notMeasured: "not measured",
    grid: "Grid",
    priceNow: "Power price",
    priceFrom: "from {time}: {price}",
    exportPrice: "export {price}",
    ownSensors: "own sensors",
    directly: "read directly",
    viaIntegration: "via its integration",
    importing: "Importing",
    exporting: "Exporting",
    house: "House",
    batteries: "Batteries",
    excluded: "Excluded",
    charging: "Charging",
    discharging: "Discharging",
    idle: "Idle",
    unavailable: "Unavailable",
    battery: "Batteries",
    virtual: "virtual",
    noBatteries: "No batteries linked yet. Add one under Settings → Devices & services → HomeBatteryAssist.",
    stored: "Stored",
    usable: "Usable",
    fullAt: "Full at",
    emptyAt: "Empty at",
    fullExpected: "Full at (plan)",
    emptyExpected: "Empty at (plan)",
    fullNom: "Full at (zero on the meter)",
    emptyNom: "Empty at (zero on the meter)",
    reachInfo: "Now: at the current power. Plan: following the selected plan with the consumption and solar forecast. Zero on the meter: if the battery just covers the house's forecast consumption.",
    phases: "Grid connection",
    phase: "Phase",
    detail: {
      temperature_c: ["Temperature", "°C", 1],
      voltage_v: ["Voltage", "V", 1],
      cell_min_v: ["Cell min.", "V", 3],
      cell_max_v: ["Cell max.", "V", 3],
      cell_delta_v: ["Cell difference", "V", 3],
      cycles: ["Cycles", "", 0],
      charged_today_kwh: ["Charged today", "kWh", 2],
      discharged_today_kwh: ["Discharged today", "kWh", 2],
      efficiency_pct: ["Efficiency (measured)", "%", 1],
    },
    allPhases: "all phases",
    withVirtual: "with virtual batteries",
    phaseLimit: "limit {a} A (fuse with {m}% margin)",
    fromGrid: "from the grid",
    phaseTotal: "Total",
    phaseTotalOf: "net, of 3 × {a} A",
    toGrid: "to the grid",
    relief: "phase protection: batteries take {w} off",
    limitedNow: "batteries held back by the limit",
    peakNow: "peak shaving: {w} taken off (limit {l})",
    peakSet: "peak limit {l}",
    idle: "idle",
    planning: "Planning",
    planningUntil: "Can plan {hours} h ahead, until {end}",
    noPlanning: "No planning possible",
    limit: {
      setting: "limited by the configured maximum",
      price: "limited by the price forecast",
      pv: "limited by the PV forecast",
      no_price: "the price forecast has no upcoming prices",
      no_pv: "the PV forecast has no data",
    },
    decisions: "Why — recent decisions",
    noDecisions: "No decisions yet.",
    error: "Could not load the status",
    recalculate: "Recalculate",
    consumption: "Consumption",
    last7: "Last 7 days (average per hour)",
    avgDay: "Average day",
    allHistory: "All history",
    weekOf: "Week {week} ({from} – {to})",
    olderWeek: "Previous week",
    newerWeek: "Next week",
    allAverage: "dashed: average of all history",
    last7Info:
      "What the house itself used, averaged per hour: grid import + solar production − excluded devices − battery charging (+ battery discharging). Excluded devices (e.g. an EV charger) are not in the house line and are not forecast. Hover over the line for the exact hour and value.",
    avgDayInfo:
      "The same house consumption, averaged per hour of the day over all history (up to 28 days), for weekdays (Mon–Fri) and the weekend separately. This is the typical day pattern; the consumption forecast uses it per weekday, with recent days counting more. Use ◀ ▶ to see a single week next to the overall average (dashed) and spot changes.",
    weekday: "Weekdays",
    weekend: "Weekend",
    daysOfData: "{days} days of history",
    imported: "incl. imported",
    noHistory: "No consumption history yet.",
    houseLine: "House",
    forecastTitle: "Expected consumption (past 24 h checked, next 48 h)",
    measured: "Measured",
    predicted: "Was expected",
    expectedLine: "Expected",
    houseMeasured: "House",
    houseExpected: "House expected",
    deviation: "Forecast deviation",
    usualHouse: "Usual deviation house",
    usualPv: "Usual deviation PV",
    pvMeasured: "PV",
    pvExpected: "PV expected",
    batteryLine: "Battery (+ charging / − discharging)",
    gridMeasured: "Grid (+ import / − export)",
    gridExpected: "Grid expected",
    batteryExpected: "Battery plan",
    planModes: { nom: "NOM", arbitrage: "arbitrage", arbitrage_full: "full arbitrage", time_slots: "time slots", manual: "manual" },
    planInfo: "Battery plan ({mode}, advice): expected saving {saving}",
    planOther: "{mode}: {saving}",
    socExpected: "Expected state of charge",
    socTitle: "State of charge of the batteries",
    socTotal: "Total",
    socPlan: "Total (plan)",
    realized: "Realised return",
    notYet: "no charging or discharging yet",
    expectedReturn: "Expected return",
    vsNoBattery: "vs no battery",
    vsMode: "{mode} vs {other}",
    modeNames: { nom: "Zero on the meter", arbitrage: "Arbitrage", arbitrage_full: "Full arbitrage", time_slots: "Time slots", manual: "Manual" },
    compareTitle: "Return compared",
    tabs: { overview: "Overview", forecast: "Forecast", value: "Return", batteries: "Batteries", check: "Accuracy" },
    compareShow: "Return overview ▾",
    compareHide: "Hide overview ▴",
    realizedShort: "realised so far",
    checkTitle: "Plan versus reality (per day)",
    checkDay: "Day",
    checkPlanned: "Planned saving",
    checkRealized: "Realised",
    checkDiff: "Difference",
    checkDev: "Avg. power deviation",
    checkNote: "Per slot the plan when the slot started, compared with what all batteries (also virtual) really did and brought. Collected from now on.",
    checkEmpty: "No complete slots measured yet.",
    modeLabel: "Plan mode",
    modeSwitching: "switching…",
    vsNone: "vs no battery",
    selected: "selected",
    realizedRow: "Realised ({mode})",
    compareNote: "Expected until {date}. Energy still in the batteries at the end counts at the average price (after losses); using it at a cheaper moment therefore costs money.",
    since: "since {date}",
    until: "until {date}",
    advantageUntil: "Advantage of arbitrage over NOM until here",
    vsNoneUntil: "Advantage over no battery until here",
    arbVsNom: "arbitrage vs. NOM: {diff} in the planning window",
    batteryNote: "The battery plan is how HomeBatteryAssist would control the batteries; for now it is advice only.",
    flowTitle: "Energy flows and expected consumption",
    navStart: "To the first measurement",
    navBack: "Back",
    navNow: "Auto follow",
    navNowTitle: "Follow the current time",
    navFwd: "Forward",
    navEnd: "To the end of the forecast",
    spans: { 24: "1 day", 72: "3 days", 168: "7 days" },
    now: "now",
    accuracy: "Average deviation (shortest lead time): {mae} ({mape}%)",
    notVerified: "Not checked yet: measured slots are compared with the forecast as time passes.",
    noForecast: "No consumption forecast yet.",
    reachTitle: "How far the forecasts reach",
    accTitle: "Forecast accuracy (running, last weeks)",
    accHelp: "Per lead time: average deviation, and the correction applied to new forecasts.",
    accKinds: { consumption: "Consumption", pv: "PV", price: "Prices" },
    accModes: { learned: "learned", off: "off", manual: "manual" },
    accNoData: "No comparisons yet: forecasts are checked as soon as the real values are known.",
    leads: { "0-1h": "0-1 h", "1-6h": "1-6 h", "6-24h": "6-24 h", "1-2d": "1-2 d", "2-3d": "2-3 d", "3-5d": "3-5 d", "5d+": "5+ d" },
    reachConsumption: "Consumption",
    reachPrice: "Prices",
    reachPv: "PV",
    reachUntil: "until {end} ({hours} h)",
    reachNone: "no data",
    reachOff: "not configured",
    excludedLine: "Excluded devices",
    recalculating: "Recalculating…",
    notLoaded: "HomeBatteryAssist is not set up yet. Add it under Settings → Devices & services → Add integration → HomeBatteryAssist.",
  },
  nl: {
    title: "HomeBatteryAssist",
    flows: "Nu",
    pv: "Zon",
    expected: "verwacht",
    notMeasured: "niet gemeten",
    grid: "Net",
    priceNow: "Stroomprijs",
    priceFrom: "vanaf {time}: {price}",
    exportPrice: "teruglevering {price}",
    ownSensors: "eigen sensoren",
    directly: "rechtstreeks",
    viaIntegration: "via integratie",
    importing: "Afname",
    exporting: "Teruglevering",
    house: "Huis",
    batteries: "Batterijen",
    excluded: "Uitgesloten",
    charging: "Laden",
    discharging: "Ontladen",
    idle: "Rust",
    unavailable: "Niet beschikbaar",
    battery: "Batterijen",
    virtual: "virtueel",
    noBatteries: "Nog geen batterijen gekoppeld. Voeg er een toe via Instellingen → Apparaten & diensten → HomeBatteryAssist.",
    stored: "Opgeslagen",
    usable: "Bruikbaar",
    fullAt: "Vol om",
    emptyAt: "Leeg om",
    fullExpected: "Vol om (plan)",
    emptyExpected: "Leeg om (plan)",
    fullNom: "Vol om (nul op de meter)",
    emptyNom: "Leeg om (nul op de meter)",
    reachInfo: "Nu: bij het huidige vermogen. Plan: volgens het gekozen plan met de verbruiks- en zonnevoorspelling. Nul op de meter: als de batterij alleen het voorspelde verbruik van het huis dekt.",
    phases: "Netaansluiting",
    phase: "Fase",
    detail: {
      temperature_c: ["Temperatuur", "°C", 1],
      voltage_v: ["Spanning", "V", 1],
      cell_min_v: ["Cel min.", "V", 3],
      cell_max_v: ["Cel max.", "V", 3],
      cell_delta_v: ["Celverschil", "V", 3],
      cycles: ["Cycli", "", 0],
      charged_today_kwh: ["Geladen vandaag", "kWh", 2],
      discharged_today_kwh: ["Ontladen vandaag", "kWh", 2],
      efficiency_pct: ["Rendement (gemeten)", "%", 1],
    },
    allPhases: "alle fasen",
    withVirtual: "met virtuele batterijen",
    phaseLimit: "grens {a} A (zekering met {m}% marge)",
    fromGrid: "van het net",
    phaseTotal: "Totaal",
    phaseTotalOf: "saldo, van 3 × {a} A",
    toGrid: "naar het net",
    relief: "fasebeveiliging: batterijen nemen {w} over",
    limitedNow: "batterijen teruggeschroefd door de grens",
    peakNow: "piekafvlakking: {w} opgevangen (grens {l})",
    peakSet: "piekgrens {l}",
    idle: "rust",
    planning: "Planning",
    planningUntil: "Kan {hours} uur vooruit plannen, tot {end}",
    noPlanning: "Geen planning mogelijk",
    limit: {
      setting: "begrensd door het ingestelde maximum",
      price: "begrensd door de prijsvoorspelling",
      pv: "begrensd door de PV-voorspelling",
      no_price: "de prijsvoorspelling bevat geen komende prijzen",
      no_pv: "de PV-voorspelling levert geen gegevens",
    },
    decisions: "Waarom — recente beslissingen",
    noDecisions: "Nog geen beslissingen.",
    error: "Status kon niet worden geladen",
    recalculate: "Herbereken",
    consumption: "Verbruik",
    last7: "Afgelopen 7 dagen (gemiddeld per uur)",
    avgDay: "Gemiddelde dag",
    allHistory: "Alle geschiedenis",
    weekOf: "Week {week} ({from} – {to})",
    olderWeek: "Vorige week",
    newerWeek: "Volgende week",
    allAverage: "gestippeld: gemiddelde van alle geschiedenis",
    last7Info:
      "Wat het huis zelf verbruikte, gemiddeld per uur: afname van het net + zonne-opwek − uitgesloten apparaten − laden van de batterij (+ ontladen). Uitgesloten apparaten (bijv. een laadpaal) zitten niet in de huislijn en worden niet voorspeld. Wijs de lijn aan voor het precieze uur en de waarde.",
    avgDayInfo:
      "Hetzelfde huisverbruik, gemiddeld per uur van de dag over alle geschiedenis (tot 28 dagen), apart voor werkdagen (ma–vr) en het weekend. Zo zie je het vaste dagpatroon; de verbruiksvoorspelling gebruikt dit per weekdag, waarbij recente dagen zwaarder tellen. Met ◀ ▶ blader je per week; het gemiddelde van alle geschiedenis staat dan gestippeld ernaast, zodat je veranderingen ziet.",
    weekday: "Werkdagen",
    weekend: "Weekend",
    daysOfData: "{days} dagen historie",
    imported: "incl. geïmporteerd",
    noHistory: "Nog geen verbruikshistorie.",
    houseLine: "Huis",
    forecastTitle: "Verwacht verbruik (afgelopen 24 uur gecontroleerd, komende 48 uur)",
    measured: "Gemeten",
    predicted: "Was verwacht",
    expectedLine: "Verwacht",
    houseMeasured: "Huis",
    houseExpected: "Huis verwacht",
    deviation: "Afwijking voorspelling",
    usualHouse: "Gebruikelijke afwijking huis",
    usualPv: "Gebruikelijke afwijking PV",
    pvMeasured: "PV",
    pvExpected: "PV verwacht",
    batteryLine: "Batterij (+ laden / − ontladen)",
    gridMeasured: "Net (+ afname / − teruglevering)",
    gridExpected: "Net verwacht",
    batteryExpected: "Batterijplan",
    planModes: { nom: "NOM", arbitrage: "arbitrage", arbitrage_full: "arbitrage volledig", time_slots: "tijdvakken", manual: "handmatig" },
    planInfo: "Batterijplan ({mode}, advies): verwachte besparing {saving}",
    planOther: "{mode}: {saving}",
    socExpected: "Verwachte vulling",
    socTitle: "Vulling batterijen",
    socTotal: "Totaal",
    socPlan: "Totaal (plan)",
    realized: "Gerealiseerd rendement",
    notYet: "nog niet geladen of ontladen",
    expectedReturn: "Verwacht rendement",
    vsNoBattery: "t.o.v. geen batterij",
    vsMode: "{mode} t.o.v. {other}",
    modeNames: { nom: "Nul op de meter", arbitrage: "Arbitrage", arbitrage_full: "Arbitrage volledig", time_slots: "Tijdvakken", manual: "Handmatig" },
    compareTitle: "Rendement vergeleken",
    tabs: { overview: "Overzicht", forecast: "Voorspelling", value: "Rendement", batteries: "Batterijen", check: "Nauwkeurigheid" },
    compareShow: "Rendement overzicht ▾",
    compareHide: "Overzicht verbergen ▴",
    realizedShort: "tot nu gerealiseerd",
    checkTitle: "Plan tegen werkelijkheid (per dag)",
    checkDay: "Dag",
    checkPlanned: "Verwachte besparing",
    checkRealized: "Gerealiseerd",
    checkDiff: "Verschil",
    checkDev: "Gem. afwijking vermogen",
    checkNote: "Per kwartier het plan bij de start ervan, vergeleken met wat alle batterijen (ook virtuele) echt deden en opleverden. Wordt vanaf nu verzameld.",
    checkEmpty: "Nog geen volledige kwartieren gemeten.",
    modeLabel: "Planmodus",
    modeSwitching: "wisselen…",
    vsNone: "t.o.v. geen batterij",
    selected: "gekozen",
    realizedRow: "Gerealiseerd ({mode})",
    compareNote: "Verwacht tot {date}. Energie die aan het eind nog in de batterijen zit telt mee tegen de gemiddelde prijs (na verlies); die gebruiken op een goedkoper moment kost dus geld.",
    since: "sinds {date}",
    until: "tot {date}",
    advantageUntil: "Voordeel arbitrage t.o.v. NOM tot hier",
    vsNoneUntil: "Voordeel t.o.v. geen batterij tot hier",
    arbVsNom: "arbitrage t.o.v. NOM: {diff} in het planningsvenster",
    batteryNote: "Het batterijplan is hoe HomeBatteryAssist de batterijen zou aansturen; voorlopig alleen advies.",
    flowTitle: "Energiestromen en verwacht verbruik",
    navStart: "Naar de eerste meting",
    navBack: "Terug",
    navNow: "Auto volgen",
    navNowTitle: "Grafiek loopt mee met de tijd",
    navFwd: "Vooruit",
    navEnd: "Naar het einde van de voorspelling",
    spans: { 24: "1 dag", 72: "3 dagen", 168: "7 dagen" },
    now: "nu",
    accuracy: "Gemiddelde afwijking (kortste vooruitzicht): {mae} ({mape}%)",
    notVerified: "Nog niet gecontroleerd: gemeten tijdvakken worden in de loop van de tijd met de voorspelling vergeleken.",
    noForecast: "Nog geen verbruiksvoorspelling.",
    reachTitle: "Hoe ver de voorspellingen reiken",
    accTitle: "Nauwkeurigheid voorspellingen (meelopend, afgelopen weken)",
    accHelp: "Per vooruitzicht: gemiddelde afwijking, en de correctie die op nieuwe voorspellingen wordt toegepast.",
    accKinds: { consumption: "Verbruik", pv: "PV", price: "Prijzen" },
    accModes: { learned: "geleerd", off: "uit", manual: "handmatig" },
    accNoData: "Nog geen vergelijkingen: voorspellingen worden gecontroleerd zodra de werkelijke waarden bekend zijn.",
    leads: { "0-1h": "0-1 u", "1-6h": "1-6 u", "6-24h": "6-24 u", "1-2d": "1-2 d", "2-3d": "2-3 d", "3-5d": "3-5 d", "5d+": "5+ d" },
    reachConsumption: "Verbruik",
    reachPrice: "Prijzen",
    reachPv: "PV",
    reachUntil: "tot {end} ({hours} uur)",
    reachNone: "geen gegevens",
    reachOff: "niet ingesteld",
    excludedLine: "Uitgesloten apparaten",
    recalculating: "Bezig met herberekenen…",
    notLoaded: "HomeBatteryAssist is nog niet ingesteld. Voeg hem toe via Instellingen → Apparaten & diensten → Integratie toevoegen → HomeBatteryAssist.",
  },
};

const STYLE = `
  :host { display: block; background: var(--primary-background-color); min-height: 100vh; color: var(--primary-text-color); }
  .toolbar { display: flex; align-items: center; height: 56px; padding: 0 12px; gap: 8px;
    background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff);
    font-size: 20px; }
  .toolbar .title { flex: 1; }
  .toolbar button { display: flex; align-items: center; gap: 6px; font: inherit; font-size: 14px; cursor: pointer;
    color: inherit; background: rgba(255, 255, 255, 0.15); border: 1px solid rgba(255, 255, 255, 0.4);
    border-radius: 18px; padding: 6px 14px; }
  .toolbar button:disabled { opacity: .6; cursor: default; }
  .toolbar button ha-icon { --mdc-icon-size: 18px; }
  .content { max-width: 1200px; margin: 0 auto; padding: 16px; display: grid; gap: 16px; }
  .tabs { display: flex; gap: 4px; overflow-x: auto; overflow-y: hidden; scrollbar-width: none; border-bottom: 1px solid var(--divider-color); }
  .tabs button { font: inherit; font-size: 14px; cursor: pointer; background: none; border: none; white-space: nowrap;
    color: var(--secondary-text-color); padding: 10px 14px; border-bottom: 2px solid transparent; margin-bottom: -1px; }
  .tabs button.active { color: var(--primary-color); border-bottom-color: var(--primary-color); font-weight: 500; }
  .card { background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px);
    box-shadow: var(--ha-card-box-shadow, none); border: 1px solid var(--divider-color); padding: 16px; }
  h2 { margin: 0 0 12px; font-size: 16px; font-weight: 500; color: var(--secondary-text-color); }
  .flows { display: flex; flex-wrap: wrap; gap: 10px; }
  .flows > .flow { flex: 1 1 0; min-width: 112px; }
  .flow { display: flex; flex-direction: column; gap: 4px; padding: 12px; border-radius: 10px;
    background: var(--secondary-background-color); }
  .flow ha-icon { --mdc-icon-size: 28px; color: var(--state-icon-color, var(--primary-color)); }
  .flow .value { font-size: 22px; font-weight: 500; white-space: nowrap; }
  .flow .label { color: var(--secondary-text-color); font-size: 12px; }
  .flow .value small { font-size: 60%; font-weight: 400; margin-left: 2px; }
  .pv ha-icon { color: var(--warning-color, #f4b400); }
  .export .value { color: var(--success-color, #43a047); }
  .import .value { color: var(--error-color, #db4437); }
  .batteries { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
  .battery { padding: 12px; border-radius: 10px; background: var(--secondary-background-color); display: grid; gap: 8px; }
  .battery .head { display: flex; justify-content: space-between; align-items: baseline; }
  .battery .name { font-weight: 500; }
  .status { font-size: 13px; padding: 2px 8px; border-radius: 10px; background: var(--divider-color); }
  .status.charging { background: var(--success-color, #43a047); color: #fff; }
  .status.discharging { background: var(--warning-color, #f4b400); color: #000; }
  .bar { position: relative; height: 18px; border-radius: 9px; background: var(--divider-color); overflow: hidden; }
  .bar .fill { position: absolute; inset: 0 auto 0 0; background: var(--primary-color); }
  .bar .fill.export { background: var(--success-color, #43a047); }
  .bar .mark.zero { left: calc(50% - 1px); opacity: .7; }
  .bar .fill.warn { background: var(--warning-color, #f4b400); }
  .bar .fill.alert { background: var(--error-color, #db4437); }
  .bar .mark { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--primary-text-color); opacity: .5; }
  .bar .text { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 500; color: var(--primary-text-color); }
  .row { display: flex; justify-content: space-between; font-size: 14px; color: var(--secondary-text-color); }
  .row b { color: var(--primary-text-color); font-weight: 500; }
  .phases { display: grid; gap: 10px; }
  table.compare { border-collapse: collapse; width: 100%; max-width: 640px; margin-bottom: 8px; }
  table.compare td { padding: 6px 8px; border-bottom: 1px solid var(--divider-color); }
  table.compare td.num, table.compare th.num { text-align: right; white-space: nowrap; }
  table.compare th { text-align: left; font-weight: 500; padding: 6px 8px; color: var(--secondary-text-color); }
  table.compare tr.sel td { font-weight: 500; }
  table.compare small { color: var(--secondary-text-color); margin-left: 4px; }
  .phase { display: grid; grid-template-columns: 40px 1fr 190px; gap: 8px; align-items: center; font-size: 14px; }
  .phase.total { border-top: 1px solid var(--divider-color); padding-top: 8px; font-weight: 500; }
  .phase b { color: var(--primary-text-color); font-weight: 500; }
  .phase .who { grid-column: 2 / 4; display: flex; flex-wrap: wrap; gap: 6px; font-size: 12px; }
  .phase .who span { padding: 1px 8px; border-radius: 10px; background: var(--secondary-background-color); }
  .phase .who span.virtual { border: 1px dashed var(--secondary-text-color); background: none; }
  ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; }
  li { display: grid; grid-template-columns: 90px 1fr; gap: 8px; font-size: 14px; }
  li time { color: var(--secondary-text-color); }
  ul.decisions { gap: 0; }
  ul.decisions li { padding: 8px 0; border-bottom: 1px solid var(--divider-color); line-height: 1.45; }
  ul.decisions li:last-child { border-bottom: none; }
  ul.decisions li > div > div + div { margin-top: 2px; }
  ul.decisions .lead { font-weight: 500; }
  .muted { color: var(--secondary-text-color); }
  .small { font-size: 0.85em; margin-top: 4px; }
  .charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
  .chart h3 { margin: 0 0 6px; font-size: 14px; font-weight: 500; }
  .chart svg { width: 100%; height: auto; display: block; }
  .chart .grid { stroke: var(--divider-color); stroke-width: 1; }
  .chart .axis { fill: var(--secondary-text-color); font-size: 11px; }
  .chart .line { fill: none; stroke-width: 2; stroke-linejoin: round; }
  .chart .line.dashed { stroke-dasharray: 5 4; stroke-width: 1.5; }
  .chart .head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
  .chart .head h3 { margin: 0; }
  .nav { display: flex; gap: 4px; flex-wrap: wrap; }
  .nav button { font: inherit; font-size: 12px; cursor: pointer; color: var(--primary-text-color);
    background: var(--secondary-background-color); border: 1px solid var(--divider-color); border-radius: 12px; padding: 2px 10px; }
  button.toggle { font: inherit; font-size: 13px; cursor: pointer; color: var(--primary-color);
    background: none; border: 1px solid var(--primary-color); border-radius: 12px; padding: 2px 12px; }
  .nav button:disabled { opacity: 0.4; cursor: default; }
  .nav button.active { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  .chart .zero { stroke: var(--secondary-text-color); stroke-width: 1; opacity: .6; }
  .chart .now { stroke: var(--secondary-text-color); stroke-width: 1; stroke-dasharray: 2 3; }
  .chart.wide { grid-column: 1 / -1; }
  .chart { position: relative; }
  .chart svg { touch-action: pan-y; cursor: crosshair; }
  .chart .cursor { stroke: var(--secondary-text-color); stroke-width: 1; }
  .tip { position: absolute; top: 28px; pointer-events: none; z-index: 2; min-width: 120px;
    background: var(--card-background-color); color: var(--primary-text-color);
    border: 1px solid var(--divider-color); border-radius: 8px; padding: 6px 8px; font-size: 12px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, .2); }
  .tip .t { font-weight: 500; margin-bottom: 2px; }
  .tip .r { display: flex; justify-content: space-between; gap: 12px; }
  .tip i { display: inline-block; width: 8px; height: 8px; border-radius: 4px; margin-right: 6px; }
  .reach { display: grid; gap: 8px; margin-top: 12px; }
  .acc { width: 100%; border-collapse: collapse; font-size: 13px; }
  .acc th, .acc td { padding: 6px 4px; text-align: right; border-bottom: 1px solid var(--divider-color); }
  .acc th:first-child, .acc td:first-child { text-align: left; }
  .acc td small { display: block; color: var(--secondary-text-color); }
  .acc-wrap { overflow-x: auto; }
  .reach .row { display: grid; grid-template-columns: 90px 1fr 170px; gap: 8px; align-items: center; }
  .reach .bar { height: 12px; }
  .legend { display: flex; gap: 16px; font-size: 13px; color: var(--secondary-text-color); margin-top: 4px; }
  .legend i { display: inline-block; width: 12px; height: 3px; border-radius: 2px; margin-right: 6px; vertical-align: middle; }
`;

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

class HomeBatteryAssistPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._status = null;
    this._error = null;
    this._loading = false;
    this._pending = false;
    this._busy = false;
    this._history = null;
    this._historyAt = 0;
    this._charts = {};
    try {
      this._tab = localStorage.getItem("homebatteryassist-tab") || "overview";
    } catch (err) {
      this._tab = "overview";
    }
    this._hover = null;
    this._flowSpan = 72; // hours in view
    this._flowEnd = null; // ms; null = follow "now"
    this._dayWeek = null; // index in profile_weeks; null = all history
  }

  async _setMode(mode) {
    if (this._modeBusy || !this._hass || mode === this._history?.value?.mode) return;
    this._modeBusy = true;
    this._scheduleRender();
    try {
      await this._hass.callService("homebatteryassist", "set_plan_mode", { mode });
      // The integration reloads and plans again with the new mode.
      await new Promise((resolve) => setTimeout(resolve, 8000));
    } catch (err) {
      this._error = err?.message || String(err);
    }
    this._modeBusy = false;
    this._historyAt = 0;
    await this._load();
  }

  async _recalculate() {
    if (this._busy || !this._hass) return;
    this._busy = true;
    this._scheduleRender();
    try {
      await this._hass.callService("homebatteryassist", "recalculate", {});
    } catch (err) {
      this._error = err?.message || String(err);
    }
    this._busy = false;
    this._historyAt = 0;
    await this._load();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._status && !this._loading) this._load();
    this._scheduleRender();
  }

  set narrow(narrow) {
    this._narrow = narrow;
    this._scheduleRender();
  }

  connectedCallback() {
    this._timer = setInterval(() => this._load(), 60000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  get _t() {
    const lang = (this._hass?.language || "en").split("-")[0];
    return TEXT[lang] || TEXT.en;
  }

  async _load() {
    if (!this._hass) return;
    this._loading = true;
    try {
      this._status = await this._hass.callWS({ type: "homebatteryassist/status" });
      this._error = null;
      if (Date.now() - this._historyAt > 5 * 60000) {
        this._history = await this._hass.callWS({ type: "homebatteryassist/history", days: 7 });
        this._historyAt = Date.now();
      }
    } catch (err) {
      this._status = null;
      this._error = err?.code === "not_loaded" ? "not_loaded" : err?.message || String(err);
    }
    this._loading = false;
    this._scheduleRender();
  }

  _scheduleRender() {
    if (this._pending) return;
    this._pending = true;
    requestAnimationFrame(() => {
      this._pending = false;
      this._render();
    });
  }

  _num(entityId) {
    const state = entityId && this._hass.states[entityId];
    const value = state ? parseFloat(state.state) : NaN;
    return Number.isNaN(value) ? null : value;
  }

  _str(entityId) {
    const state = entityId && this._hass.states[entityId];
    return state && !["unknown", "unavailable"].includes(state.state) ? state.state : null;
  }

  _power(watts) {
    if (watts === null) return "–";
    const abs = Math.abs(watts);
    return abs >= 1000 ? `${(watts / 1000).toFixed(2)} kW` : `${Math.round(watts)} W`;
  }

  _axisPower(watts) {
    // Short labels for the y-axis: "-1 kW", "2.5 kW", "500 W".
    const abs = Math.abs(watts);
    if (abs < 1000) return `${Math.round(watts)} W`;
    const kw = watts / 1000;
    return `${Number.isInteger(kw) ? kw : kw.toFixed(abs < 10000 ? 1 : 0)} kW`;
  }

  _kwh(value) {
    return value === null ? "–" : `${value.toFixed(2)} kWh`;
  }

  _time(iso) {
    if (!iso) return "–";
    const date = new Date(iso);
    const sameDay = date.toDateString() === new Date().toDateString();
    const opts = sameDay ? { hour: "2-digit", minute: "2-digit" } : { weekday: "short", hour: "2-digit", minute: "2-digit" };
    return date.toLocaleString(this._hass.locale?.language || this._hass.language, opts);
  }

  _flow(cls, icon, label, value, sub = "") {
    return `<div class="flow ${cls}"><ha-icon icon="${icon}"></ha-icon>
      <div class="value">${value}</div><div class="label">${esc(label)}${sub ? ` · ${esc(sub)}` : ""}</div></div>`;
  }

  _flows(s, t) {
    const e = s.entities;
    const grid = this._num(e.grid_power);
    const parts = [];
    parts.push(this._flow("house", "mdi:home", t.house, this._power(this._num(e.house_consumption))));
    parts.push(
      this._flow(
        grid !== null && grid < 0 ? "export" : "import",
        "mdi:transmission-tower",
        t.grid,
        this._power(grid === null ? null : Math.abs(grid)),
        grid === null ? "" : grid < 0 ? t.exporting : t.importing,
      ),
    );
    // Which meter measures the grid (brand/type, and how it is read).
    const m = s.meter;
    if (m && typeof m === "object") {
      const how = m.name ? (m.direct ? t.directly : t.viaIntegration) : "";
      const text = [m.name || t.ownSensors, how].filter(Boolean).join(", ");
      parts[parts.length - 1] = parts[parts.length - 1].replace(
        "</div></div>",
        `</div><div class="label meter" title="${esc(m.address || "")}">${esc(text)}</div></div>`,
      );
    }
    // Current and next power price (≈ = estimated), and the export price now.
    if (s.prices) {
      const p = s.prices;
      const lang = this._hass.locale?.language || this._hass.language;
      const fmt = (v, est) =>
        v == null ? "–" : `${est ? "≈ " : ""}${new Intl.NumberFormat(lang, { style: "currency", currency: p.currency || "EUR", minimumFractionDigits: 2, maximumFractionDigits: 3 }).format(v)}`;
      const subs = [];
      if (p.next != null) {
        const time = new Date(p.next_start).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });
        subs.push(t.priceFrom.replace("{time}", time).replace("{price}", fmt(p.next, p.next_estimated)));
      }
      if (p.export_now != null) subs.push(t.exportPrice.replace("{price}", fmt(p.export_now)));
      const cls = p.next == null ? "price" : p.next > p.now ? "price up" : "price down";
      parts.push(this._flow(cls, "mdi:currency-eur", t.priceNow, `${fmt(p.now, p.now_estimated)}<small>/kWh</small>`, subs.join(" · ")));
    }
    if (s.has_pv || s.has_pv_forecast) {
      const expected = s.pv_forecast_now_w == null ? "" : `${t.expected} ${this._power(s.pv_forecast_now_w)}`;
      const value = s.has_pv ? this._power(this._num(e.pv_power)) : "–";
      const sub = [s.has_pv ? "" : t.notMeasured, expected].filter(Boolean).join(" · ");
      parts.push(this._flow("pv", "mdi:solar-power", t.pv, value, sub));
    }
    if (s.batteries.length) {
      let power = this._num(e.batteries_power);
      let soc = this._num(e.batteries_soc);
      let label = t.batteries;
      if (power === null && soc === null) {
        // Only virtual batteries: add them up here.
        let cap = 0, stored = 0, sum = 0, known = false;
        for (const b of s.batteries) {
          const p = this._num(b.entities.battery_power);
          const c = this._num(b.entities.battery_soc);
          if (p !== null) { sum += p; known = true; }
          if (c !== null) { stored += (c * b.capacity_kwh) / 100; cap += b.capacity_kwh; }
        }
        power = known ? sum : null;
        soc = cap ? (stored / cap) * 100 : null;
        if (s.batteries.every((b) => b.virtual)) label = `${t.batteries} (${t.virtual})`;
      }
      const mode = power === null ? "" : power > 20 ? t.charging : power < -20 ? t.discharging : t.idle;
      parts.push(
        this._flow("battery", "mdi:home-battery", label, this._power(power === null ? null : Math.abs(power)),
          [mode, soc === null ? "" : `${Math.round(soc)}%`].filter(Boolean).join(" · ")),
      );
    }
    if (s.has_excluded) parts.push(this._flow("excluded", "mdi:ev-station", t.excluded, this._power(this._num(e.excluded_power))));
    return `<div class="card"><h2>${esc(t.flows)}</h2><div class="flows">${parts.join("")}</div></div>`;
  }

  _compare(s, t) {
    // Every mode compared with no battery, and arbitrage compared with NOM.
    const value = this._history?.value;
    if (!value || !s.batteries.length || !value.by_mode) return "";
    const lang = this._hass.locale?.language || this._hass.language;
    const money = (v) =>
      v == null ? "–" : new Intl.NumberFormat(lang, { style: "currency", currency: value.currency || "EUR" }).format(v);
    const signed = (v) => (v == null ? "–" : `${v > 0 ? "+" : ""}${money(v)}`);
    const name = (m) => t.modeNames[m] || m;
    // Time slots without slots and manual at 0 W only repeat NOM / nothing.
    const shown = (m) =>
      m === value.mode || (m === "time_slots" ? value.time_slots > 0 : m === "manual" ? value.manual_w !== 0 : true);
    const rows = Object.entries(value.by_mode).filter(([m]) => shown(m)).map(
      ([mode, saving]) =>
        `<tr${mode === value.mode ? ' class="sel"' : ""}><td>${esc(name(mode))}${mode === value.mode ? ` <small>${esc(t.selected)}</small>` : ""}</td><td>${esc(t.vsNone)}</td><td class="num">${esc(signed(saving))}</td></tr>`,
    );
    const nom = value.by_mode.nom;
    for (const [mode, saving] of Object.entries(value.by_mode)) {
      if (!mode.startsWith("arbitrage") || nom == null || saving == null) continue;
      rows.push(
        `<tr><td>${esc(name(mode))}</td><td>${esc(t.vsMode.replace("{mode}", "").replace("{other}", name("nom").toLowerCase()).trim())}</td><td class="num"><b>${esc(signed(saving - nom))}</b></td></tr>`,
      );
    }
    rows.push(
      `<tr><td>${esc(t.realizedRow.replace("{mode}", name(value.mode).toLowerCase()))}</td><td>${esc(t.vsNone)}</td><td class="num">${esc(signed(value.realized))}</td></tr>`,
    );
    const date = value.until
      ? new Date(value.until).toLocaleString(lang, { weekday: "short", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" })
      : "–";
    // Choose the plan mode here (the integration reloads with it).
    const modes = Object.keys(t.modeNames).filter((m) => m in value.by_mode || m === value.mode);
    const buttons = modes
      .map(
        (m) =>
          `<button data-mode="${esc(m)}" class="${m === value.mode ? "active" : ""}" ${this._modeBusy ? "disabled" : ""}>${esc(name(m))}</button>`,
      )
      .join("");
    const open = true;
    const selected = value.by_mode[value.mode];
    const summary = `${name(value.mode)} ${t.vsNone}: ${signed(selected)} · ${t.realizedShort}: ${signed(value.realized)}`;
    return `<div class="card"><div class="chart"><div class="head"><h2>${esc(t.compareTitle)}</h2>
      <div class="nav"><span class="muted">${esc(this._modeBusy ? t.modeSwitching : t.modeLabel)}:</span>${buttons}</div></div></div>
      <div class="head"><span>${esc(summary)}</span></div>
      ${open ? `<table class="compare">${rows.join("")}</table>
      <div class="muted">${esc(t.compareNote.replace("{date}", date))}</div>` : ""}</div>`;
  }

  _planCheck(s, t) {
    const days = this._history?.plan_check;
    if (!days || !s.batteries.length) return "";
    const lang = this._hass.locale?.language || this._hass.language;
    const currency = this._history?.value?.currency || "EUR";
    const money = (v) => new Intl.NumberFormat(lang, { style: "currency", currency }).format(v);
    const signed = (v) => `${v > 0 ? "+" : ""}${money(v)}`;
    const rows = days.map((d) => {
      const day = new Date(`${d.day}T12:00:00`).toLocaleDateString(lang, { weekday: "short", day: "numeric", month: "numeric" });
      const diff = d.realized - d.planned;
      return `<tr><td>${esc(day)}</td><td class="num">${esc(money(d.planned))}</td><td class="num">${esc(money(d.realized))}</td>
        <td class="num"><b>${esc(signed(diff))}</b></td><td class="num">${esc(this._power(d.power_deviation_w))}</td></tr>`;
    });
    const head = `<tr><th>${esc(t.checkDay)}</th><th class="num">${esc(t.checkPlanned)}</th><th class="num">${esc(t.checkRealized)}</th><th class="num">${esc(t.checkDiff)}</th><th class="num">${esc(t.checkDev)}</th></tr>`;
    const body = rows.length ? `<table class="compare">${head}${rows.join("")}</table>` : `<div class="muted">${esc(t.checkEmpty)}</div>`;
    return `<div class="card"><h2>${esc(t.checkTitle)}</h2>${body}<div class="muted">${esc(t.checkNote)}</div></div>`;
  }

  _battery(b, t) {
    const e = b.entities;
    const soc = this._num(e.battery_soc);
    const power = this._num(e.battery_power);
    const status = this._str(e.battery_status);
    const target = this._str(e.battery_time_to_target);
    const fill = soc === null ? 0 : soc;
    const cls = soc !== null && soc <= b.min_soc ? "alert" : soc !== null && soc < b.min_soc + 10 ? "warn" : "";
    return `<div class="battery">
      <div class="head"><span class="name">${esc(b.name)}${b.virtual ? ` <small class="muted">(${esc(t.virtual)})</small>` : ""}</span>
        <span class="status ${esc(status || "")}">${esc(status ? t[status] || status : t.unavailable)}</span></div>
      <div class="bar"><div class="fill ${cls}" style="width:${fill}%"></div>
        <div class="mark" style="left:${b.min_soc}%"></div><div class="mark" style="left:${b.max_soc}%"></div>
        <div class="text">${soc === null ? "–" : `${Math.round(soc)}%`}</div></div>
      <div class="row"><span>${esc(t.stored)}</span><b>${this._kwh(this._num(e.battery_stored_energy))} / ${b.capacity_kwh} kWh</b></div>
      <div class="row"><span>${esc(t.usable)}</span><b>${this._kwh(this._num(e.battery_usable_energy))}</b></div>
      ${this._status?.phases === 3 ? `<div class="row"><span>${esc(t.phase)}</span><b>${esc(b.phase && b.phase !== "none" ? b.phase.toUpperCase() : t.allPhases)}</b></div>` : ""}
      <div class="row"><span>${esc(status === "discharging" ? t.discharging : t.charging)}</span><b>${this._power(power === null ? null : Math.abs(power))}</b></div>
      ${target ? `<div class="row" title="${esc(t.reachInfo)}"><span>${esc(status === "charging" ? t.fullAt : t.emptyAt)}</span><b>${this._time(target)}</b></div>` : ""}
      ${b.expected_full ? `<div class="row" title="${esc(t.reachInfo)}"><span>${esc(t.fullExpected)}</span><b>${this._time(b.expected_full)}</b></div>` : ""}
      ${b.expected_empty ? `<div class="row" title="${esc(t.reachInfo)}"><span>${esc(t.emptyExpected)}</span><b>${this._time(b.expected_empty)}</b></div>` : ""}
      ${b.nom_full && b.nom_full !== b.expected_full ? `<div class="row" title="${esc(t.reachInfo)}"><span>${esc(t.fullNom)}</span><b>${this._time(b.nom_full)}</b></div>` : ""}
      ${b.nom_empty && b.nom_empty !== b.expected_empty ? `<div class="row" title="${esc(t.reachInfo)}"><span>${esc(t.emptyNom)}</span><b>${this._time(b.nom_empty)}</b></div>` : ""}
      ${Object.entries(b.details || {})
        .filter(([k]) => t.detail[k])
        .map(([k, v]) => {
          const [label, unit, digits] = t.detail[k];
          const lang = this._hass.locale?.language || this._hass.language;
          const text = Number(v).toLocaleString(lang, { maximumFractionDigits: digits, minimumFractionDigits: digits });
          return `<div class="row"><span>${esc(label)}</span><b>${esc(text)}${unit ? ` ${unit}` : ""}</b></div>`;
        })
        .join("")}
    </div>`;
  }

  _batteries(s, t) {
    const body = s.batteries.length
      ? `<div class="batteries">${s.batteries.map((b) => this._battery(b, t)).join("")}</div>`
      : `<div class="muted">${esc(t.noBatteries)}</div>`;
    return `<div class="card"><h2>${esc(t.battery)}</h2>${body}</div>`;
  }

  _phases(s, t) {
    const rows = [];
    for (let i = 1; i <= s.phases; i++) {
      const id = s.entities[`phase_l${i}_load`];
      const load = this._num(id);
      const attrs = id && this._hass.states[id] ? this._hass.states[id].attributes : {};
      const current = attrs.current ?? null;
      const power = attrs.power ?? null;
      const cls = load !== null && load >= 90 ? "alert" : load !== null && load >= 75 ? "warn" : "";
      // Batteries on this phase (a battery without a phase is spread over all).
      const share = (b) => (s.phases === 1 || b.phase === `l${i}` ? 1 : !b.phase || b.phase === "none" ? 1 / s.phases : 0);
      const here = s.batteries.filter((b) => share(b) > 0);
      let virtualW = 0;
      const who = here.map((b) => {
        const p = this._num(b.entities.battery_power);
        if (b.virtual && p !== null) virtualW += p * share(b);
        const what = p === null ? "–" : Math.abs(p) < 1 ? t.idle : `${p > 0 ? t.charging : t.discharging} ${this._power(Math.abs(p * share(b)))}`;
        return `<span class="${b.virtual ? "virtual" : ""}">${esc(b.name)}${share(b) < 1 ? " (⅓)" : ""}: ${esc(what.toLowerCase())}</span>`;
      });
      let withVirtual = "";
      if (virtualW && power !== null) {
        const amps = Math.abs(power + virtualW) / 230;
        const wcls = amps >= s.phase_limit_a ? "alert" : amps >= 0.75 * s.max_current ? "warn" : "";
        withVirtual = `<span class="${wcls}">${esc(t.withVirtual)}: <b>${amps.toFixed(1)} A</b></span>`;
      }
      rows.push(`<div class="phase"><span>L${i}</span>
        ${this._phaseBar(load, power, cls, t)}
        <span class="muted"><b>${this._power(power)}</b> · ${current == null ? "–" : `${current} A`} / ${s.max_current} A</span>
        ${who.length || withVirtual || this._protectNote(s, i, t) ? `<div class="who">${who.join("")}${withVirtual}${this._protectNote(s, i, t)}</div>` : ""}</div>`);
    }
    if (s.phases === 3) {
      // Net exchange over all phases, against three fuses.
      const powers = [1, 2, 3].map((i) => {
        const id = s.entities[`phase_l${i}_load`];
        return id && this._hass.states[id] ? this._hass.states[id].attributes.power ?? null : null;
      });
      const known = powers.filter((p) => p !== null);
      const total = known.length ? known.reduce((a, b) => a + b, 0) : null;
      const load = total === null ? null : (Math.abs(total) / (3 * s.max_current * 230)) * 100;
      rows.push(`<div class="phase total"><span>${esc(t.phaseTotal)}</span>
        ${this._phaseBar(load, total, "", t)}
        <span class="muted"><b>${this._power(total)}</b> · ${esc(t.phaseTotalOf.replace("{a}", s.max_current))}</span></div>`);
    }
    const prot = s.protection;
    const peak =
      prot && prot.peak_limit_w > 0
        ? `<div class="muted">${esc(
            prot.peak_w > 0
              ? t.peakNow.replace("{w}", this._power(prot.peak_w)).replace("{l}", this._power(prot.peak_limit_w))
              : t.peakSet.replace("{l}", this._power(prot.peak_limit_w)),
          )}</div>`
        : "";
    rows.push(peak);
    const limit = s.phase_limit_a ? ` <small class="muted">· ${esc(t.phaseLimit.replace("{a}", s.phase_limit_a).replace("{m}", s.phase_margin ?? 10))}</small>` : "";
    return `<div class="card"><h2>${esc(t.phases)} · ${s.phases}x${s.max_current}A${limit}</h2><div class="phases">${rows.join("")}</div></div>`;
  }

  _phaseBar(load, power, cls, t) {
    // Zero in the middle: export (to the grid) fills to the left in green,
    // import (from the grid) to the right in blue; each half is the fuse.
    const half = Math.min(load ?? 0, 100) / 2;
    const exporting = power !== null && power < 0;
    const style = exporting ? `left:${50 - half}%;width:${half}%` : `left:50%;width:${half}%`;
    const dir = power === null || Math.abs(power) < 1 ? "" : ` ${exporting ? t.toGrid : t.fromGrid}`;
    return `<div class="bar center"><div class="fill ${cls || (exporting ? "export" : "")}" style="${style}"></div>
      <div class="mark zero"></div>
      <div class="text">${load === null ? "–" : `${dir && exporting ? "← " : ""}${Math.round(load)}%${dir}${dir && !exporting ? " →" : ""}`}</div></div>`;
  }

  _protectNote(s, i, t) {
    // Phase protection / limit on this phase right now (virtual batteries).
    const prot = s.protection;
    if (!prot) return "";
    const phase = `L${i}`;
    if (prot.relief?.[phase]) return `<span class="alert">${esc(t.relief.replace("{w}", this._power(prot.relief[phase])))}</span>`;
    if (prot.limited?.includes(phase)) return `<span class="warn">${esc(t.limitedNow)}</span>`;
    return "";
  }

  _planning(s, t) {
    const w = s.window;
    const text =
      w.hours > 0
        ? t.planningUntil.replace("{hours}", Math.round(w.hours)).replace("{end}", this._time(w.end))
        : t.noPlanning;
    const r = s.reach || {};
    const start = new Date(w.start).getTime();
    const span = Math.max(new Date(r.max_end || w.end).getTime() - start, 1);
    const row = (label, end, configured) => {
      let fill = 0;
      let info = configured ? t.reachNone : t.reachOff;
      if (configured && end) {
        const ms = new Date(end).getTime() - start;
        fill = Math.max(0, Math.min(100, (ms / span) * 100));
        info = t.reachUntil.replace("{end}", this._time(end)).replace("{hours}", Math.max(0, Math.round(ms / 3600e3)));
      }
      return `<div class="row"><span>${esc(label)}</span>
        <div class="bar"><div class="fill" style="width:${fill}%"></div></div>
        <span class="muted">${esc(info)}</span></div>`;
    };
    const reach = `<h2 style="margin-top:16px">${esc(t.reachTitle)}</h2><div class="reach">
      ${row(t.reachConsumption, r.consumption_end, true)}
      ${row(t.reachPrice, r.price_end, r.has_price)}
      ${row(t.reachPv, r.pv_end, r.has_pv_forecast)}</div>`;
    return `<div class="card"><h2>${esc(t.planning)}</h2><div>${esc(text)}</div>
      <div class="muted">${esc(t.limit[w.limited_by] || w.limited_by)}</div>${reach}</div>`;
  }

  _niceMax(value) {
    if (!value || value <= 0) return 100;
    const step = 10 ** Math.floor(Math.log10(value));
    for (const m of [1, 2, 2.5, 5, 10]) if (value <= m * step) return m * step;
    return 10 * step;
  }

  _chart(id, series, xMin, xMax, ticks, gapLimit, markers = [], xFmt = (v) => this._time(new Date(v).toISOString()), yFmt = null) {
    // Full-width charts get a wider canvas so they are as high as the others.
    // The full-width flow chart gets a wider and higher canvas.
    const wide = id === "forecast" || id === "soc";
    const W = wide ? 1232 : 600, H = id === "forecast" ? 300 : 190, L = 58, R = 8, T = 8, B = 24;
    const all = series.flatMap((s) => s.points.map((p) => p[1])).filter((v) => v != null);
    const yMax = this._niceMax(Math.max(...all, 0));
    const low = Math.min(...all, 0);
    const yMin = low < 0 ? -this._niceMax(-low) : 0;
    const x = (v) => L + ((v - xMin) / (xMax - xMin || 1)) * (W - L - R);
    const y = (v) => T + (1 - (v - yMin) / (yMax - yMin)) * (H - T - B);
    let svg = `<clipPath id="clip-${id}"><rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}"/></clipPath>`;
    const steps = 4;
    for (let i = 0; i <= steps; i++) {
      const v = yMin + ((yMax - yMin) / steps) * i;
      svg += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`;
      svg += `<text class="axis" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${esc(yFmt ? yFmt(v) : this._axisPower(v))}</text>`;
    }
    if (yMin < 0) svg += `<line class="zero" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}"/>`;
    for (const [v, label] of ticks) {
      svg += `<text class="axis" x="${x(v)}" y="${H - 6}" text-anchor="middle">${esc(label)}</text>`;
    }
    for (const s of series) {
      let d = "";
      let prev = null;
      for (const [px, py] of s.points) {
        if (py == null) { prev = null; continue; }
        const jump = prev === null || (gapLimit && px - prev > gapLimit);
        d += `${jump ? "M" : "L"}${x(px).toFixed(1)},${y(py).toFixed(1)}`;
        prev = px;
      }
      svg += `<path class="line${s.dashed ? " dashed" : ""}" d="${d}" stroke="${s.color}" clip-path="url(#clip-${id})"/>`;
    }
    for (const [v, label] of markers) {
      svg += `<line class="now" x1="${x(v)}" x2="${x(v)}" y1="${T}" y2="${H - B}"/>`;
      svg += `<text class="axis" x="${x(v) + 4}" y="${T + 10}">${esc(label)}</text>`;
    }
    svg += `<g class="hover" style="display:none"><line class="cursor" y1="${T}" y2="${H - B}"/>
      ${series.map((s, i) => `<circle r="3.5" data-i="${i}" style="fill:${s.color}"/>`).join("")}</g>`;
    this._charts[id] = { series, xMin, xMax, yMin, yMax, W, H, L, R, T, B, gapLimit, xFmt, yFmt };
    return `<svg data-chart="${id}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">${svg}</svg>
      <div class="tip" data-tip="${id}" hidden></div>`;
  }

  _money(value, h) {
    const unit = h.price_unit?.split("/")[0] || "";
    return value == null ? "–" : `${value.toFixed(2)} ${unit}`.trim();
  }

  _planText(h, t) {
    const money = (v) => (v == null ? "–" : `${v.toFixed(2)} ${h.price_unit?.split("/")[0] || ""}`.trim());
    const plan = h.plans?.[h.plan_mode];
    const name = (mode) => t.planModes[mode] || mode;
    const others = Object.entries(h.plans || {})
      .filter(([mode]) => mode !== h.plan_mode)
      .map(([mode, p]) => t.planOther.replace("{mode}", name(mode)).replace("{saving}", money(p.saving)));
    const main = t.planInfo.replace("{mode}", name(h.plan_mode)).replace("{saving}", money(plan?.saving));
    let text = others.length ? `${main} (${others.join(", ")})` : main;
    const arb = h.plans?.arbitrage?.saving;
    const nom = h.plans?.nom?.saving;
    if (arb != null && nom != null) {
      const diff = arb - nom;
      text += ` · ${t.arbVsNom.replace("{diff}", `${diff >= 0 ? "+" : ""}${this._money(diff, h)}`)}`;
    }
    return text;
  }

  _flowNav(t) {
    const spans = Object.entries(t.spans)
      .map(([h, label]) => `<button data-span="${h}" class="${Number(h) === this._flowSpan ? "active" : ""}">${esc(label)}</button>`)
      .join("");
    const nav = [
      ["start", "⏮", t.navStart],
      ["back", "◀", t.navBack],
      ["now", t.navNow, t.navNowTitle],
      ["fwd", "▶", t.navFwd],
      ["end", "⏭", t.navEnd],
    ]
      .map(
        ([key, label, title]) =>
          `<button data-nav="${key}" title="${esc(title)}" class="${key === "now" && this._flowEnd === null ? "active" : ""}">${esc(label)}</button>`,
      )
      .join("");
    return `<div class="nav">${nav}<span style="width:8px"></span>${spans}</div>`;
  }

  _dayNav(t, weeks, lang) {
    if (!weeks.length) return "";
    const i = this._dayWeek;
    let label = t.allHistory;
    if (i !== null) {
      const w = weeks[i];
      const from = new Date(`${w.start}T12:00:00`);
      const to = new Date(`${w.end}T12:00:00`);
      // ISO week number of the Monday.
      const thursday = new Date(from);
      thursday.setDate(from.getDate() + 3);
      const jan4 = new Date(thursday.getFullYear(), 0, 4);
      const week = 1 + Math.round(((thursday - jan4) / 864e5 - 3 + ((jan4.getDay() + 6) % 7)) / 7);
      const fmt = (d) => d.toLocaleDateString(lang, { day: "numeric", month: "short" });
      label = t.weekOf.replace("{week}", week).replace("{from}", fmt(from)).replace("{to}", fmt(to));
    }
    const older = i === null ? weeks.length - 1 : i - 1;
    const newer = i === null ? null : i + 1 < weeks.length ? i + 1 : null;
    return `<div class="nav">
      <button data-day="${older}" title="${esc(t.olderWeek)}" ${older < 0 ? "disabled" : ""}>◀</button>
      <button data-day="all" class="${i === null ? "active" : ""}">${esc(label)}</button>
      <button data-day="${newer === null ? "all" : newer}" title="${esc(t.newerWeek)}" ${i === null ? "disabled" : ""}>▶</button>
    </div>`;
  }

  _flowShift(key, amount = 0) {
    const b = this._flowBounds;
    if (!b) return;
    const span = this._flowSpan * 3600e3;
    const current = this._flowEnd ?? b.now + (span * 2) / 3;
    const target = {
      start: b.dataMin + span,
      back: current - span / 2,
      now: null,
      fwd: current + span / 2,
      end: b.dataMax,
      wheel: current + amount,
    }[key];
    this._flowEnd = target === null ? null : Math.min(Math.max(target, b.dataMin + span), Math.max(b.dataMax, b.dataMin + span));
    this._hover = null;
    this._scheduleRender();
  }

  _bindFlowNav() {
    for (const button of this.shadowRoot.querySelectorAll(".nav button[data-day]")) {
      button.addEventListener("click", () => {
        this._dayWeek = button.dataset.day === "all" ? null : Number(button.dataset.day);
        this._hover = null;
        this._scheduleRender();
      });
    }
    for (const button of this.shadowRoot.querySelectorAll(".nav button[data-nav]")) {
      button.addEventListener("click", () => this._flowShift(button.dataset.nav));
    }
    for (const button of this.shadowRoot.querySelectorAll(".nav button[data-span]")) {
      button.addEventListener("click", () => {
        this._flowSpan = Number(button.dataset.span);
        this._scheduleRender();
      });
    }
    const svg = this.shadowRoot.querySelector('svg[data-chart="forecast"]');
    svg?.addEventListener(
      "wheel",
      (event) => {
        const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.shiftKey ? event.deltaY : 0;
        if (!delta) return; // plain vertical scroll keeps scrolling the page
        event.preventDefault();
        this._flowShift("wheel", (delta / 600) * this._flowSpan * 3600e3);
      },
      { passive: false },
    );
  }

  _bindCharts() {
    for (const svg of this.shadowRoot.querySelectorAll("svg[data-chart]")) {
      const id = svg.dataset.chart;
      const move = (event) => {
        const point = event.touches ? event.touches[0] : event;
        const rect = svg.getBoundingClientRect();
        this._hover = { id, fx: (point.clientX - rect.left) / rect.width };
        this._showHover();
      };
      svg.addEventListener("mousemove", move);
      svg.addEventListener("touchstart", move, { passive: true });
      svg.addEventListener("touchmove", move, { passive: true });
      const leave = () => {
        this._hover = null;
        this._showHover(id);
      };
      svg.addEventListener("mouseleave", leave);
      svg.addEventListener("touchend", () => {
        clearTimeout(this._touchTimer);
        this._touchTimer = setTimeout(leave, 3000);
      });
    }
  }

  _nearest(points, xv, limit) {
    let best = null;
    for (const p of points) {
      if (p[1] == null) continue;
      if (best === null || Math.abs(p[0] - xv) < Math.abs(best[0] - xv)) best = p;
    }
    return best && (limit == null || Math.abs(best[0] - xv) <= limit) ? best : null;
  }

  _showHover(hideId = null) {
    const id = this._hover?.id ?? hideId;
    const svg = id && this.shadowRoot.querySelector(`svg[data-chart="${id}"]`);
    const tip = id && this.shadowRoot.querySelector(`.tip[data-tip="${id}"]`);
    const c = id && this._charts[id];
    if (!svg || !tip || !c) return;
    const layer = svg.querySelector(".hover");
    const vx = (this._hover?.fx ?? -1) * c.W;
    if (!this._hover || vx < c.L || vx > c.W - c.R) {
      layer.style.display = "none";
      tip.hidden = true;
      return;
    }
    const xv = c.xMin + ((vx - c.L) / (c.W - c.L - c.R)) * (c.xMax - c.xMin);
    const limit = c.gapLimit ?? 0.5;
    const hits = c.series.map((s) => this._nearest(s.points, xv, limit));
    const anchor = hits.find((h) => h) ;
    if (!anchor) {
      layer.style.display = "none";
      tip.hidden = true;
      return;
    }
    const sx = (v) => c.L + ((v - c.xMin) / (c.xMax - c.xMin || 1)) * (c.W - c.L - c.R);
    const sy = (v) => c.T + (1 - (v - c.yMin) / (c.yMax - c.yMin)) * (c.H - c.T - c.B);
    layer.style.display = "";
    const cursor = layer.querySelector(".cursor");
    cursor.setAttribute("x1", sx(anchor[0]));
    cursor.setAttribute("x2", sx(anchor[0]));
    layer.querySelectorAll("circle").forEach((circle) => {
      const hit = hits[Number(circle.dataset.i)];
      circle.style.display = hit ? "" : "none";
      if (hit) {
        circle.setAttribute("cx", sx(hit[0]));
        circle.setAttribute("cy", sy(hit[1]));
      }
    });
    const rows = c.series
      .map((s, i) => (hits[i] ? `<div class="r"><span><i style="background:${s.color}"></i>${esc(s.label || "")}</span>
        <b>${esc(c.yFmt ? c.yFmt(hits[i][1]) : this._power(hits[i][1]))}</b></div>` : ""))
      .join("");
    const extra = c.extra ? c.extra(anchor[0], hits) : "";
    tip.innerHTML = `<div class="t">${esc(c.xFmt(anchor[0]))}</div>${rows}${extra}`;
    tip.hidden = false;
    const box = svg.getBoundingClientRect();
    const parent = svg.parentElement.getBoundingClientRect();
    const px = box.left - parent.left + (sx(anchor[0]) / c.W) * box.width;
    const width = tip.offsetWidth;
    tip.style.left = `${px + 12 + width > parent.width ? Math.max(0, px - width - 12) : px + 12}px`;
  }

  _consumption(t) {
    const h = this._history;
    if (!h) return "";
    if (!h.hourly.length && !h.profile.weekday.some((v) => v != null)) {
      return `<div class="card"><h2>${esc(t.consumption)}</h2><div class="muted">${esc(t.noHistory)}</div></div>`;
    }
    const lang = this._hass.locale?.language || this._hass.language;
    const primary = "var(--primary-color)";
    const accent = "var(--accent-color, #ff9800)";

    // Last 7 days: hourly points, ticks at local midnight.
    const pts = h.hourly.map(([time, house]) => [time, house]);
    const excludedPts = h.hourly.map(([time, , excluded]) => [time, excluded]);
    const excludedColor = "#ab47bc"; // purple: clearly different from PV (yellow)
    const xMin = pts.length ? pts[0][0] : Date.now() - 7 * 864e5;
    const xMax = Date.now();
    const ticks = [];
    const day = new Date(xMin);
    day.setHours(24, 0, 0, 0);
    for (; day.getTime() < xMax; day.setDate(day.getDate() + 1)) {
      ticks.push([day.getTime(), day.toLocaleDateString(lang, { weekday: "short", day: "numeric", month: "numeric" })]);
    }
    const weekSeries = [{ points: pts, color: primary, label: t.houseLine }];
    if (h.has_excluded) weekSeries.push({ points: excludedPts, color: excludedColor, label: t.excludedLine });
    const hourFmt = (v) =>
      new Date(v).toLocaleString(lang, { weekday: "short", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" });
    const week = this._chart("week", weekSeries, xMin, xMax, ticks, 2 * 3600e3, [], hourFmt);
    const weekLegend = h.has_excluded
      ? `<div class="legend"><span><i style="background:${primary}"></i>${esc(t.houseLine)}</span>
         <span><i style="background:${excludedColor}"></i>${esc(t.excludedLine)}</span></div>`
      : "";

    // Average day: 24 local hours, weekdays vs weekend.
    const profilePts = (values) => values.map((v, hour) => [hour, v]);
    const hourTicks = [0, 3, 6, 9, 12, 15, 18, 21].map((hour) => [hour, `${String(hour).padStart(2, "0")}:00`]);
    const two = (n) => String(n).padStart(2, "0");
    const weeks = h.profile_weeks || [];
    if (this._dayWeek !== null && this._dayWeek >= weeks.length) this._dayWeek = null;
    const shown = this._dayWeek === null ? null : weeks[this._dayWeek];
    const daySeries = shown
      ? [
          { points: profilePts(h.profile.weekday), color: primary, dashed: true, label: `${t.weekday} · ${t.allHistory}` },
          { points: profilePts(h.profile.weekend), color: accent, dashed: true, label: `${t.weekend} · ${t.allHistory}` },
          { points: profilePts(shown.weekday), color: primary, label: t.weekday },
          { points: profilePts(shown.weekend), color: accent, label: t.weekend },
        ]
      : [
          { points: profilePts(h.profile.weekday), color: primary, label: t.weekday },
          { points: profilePts(h.profile.weekend), color: accent, label: t.weekend },
        ];
    const avg = this._chart(
      "day",
      daySeries,
      0,
      23,
      hourTicks,
      null,
      [],
      (hour) => `${two(hour)}:00 – ${two((hour + 1) % 24)}:00`,
    );
    // Expected consumption: past 24 h measured vs. predicted, next 48 h forecast.
    const now = Date.now();
    const secondary = "var(--secondary-text-color)";
    const verified = h.verification || [];
    const fc = h.forecast || [];
    let forecastChart;
    const past = h.past || [];
    const pvFc = h.pv_forecast || [];
    const pvColor = "#fbc02d";
    const batteryColor = "var(--success-color, #43a047)";
    const gridColor = "#e53935";
    // Grid = house - PV + excluded devices + battery charging (from the history).
    const gridPast = past.map(([ts, house, excluded, pv, battery]) => [
      ts,
      house == null ? null : Math.round(house - (pv || 0) + (excluded || 0) + (battery || 0)),
    ]);
    // Expected grid: from the battery simulation if there is one, otherwise
    // expected house minus expected PV (per hour).
    const batFc = h.battery_forecast || [];
    const pvByHour = new Map(pvFc.map(([ts, wh]) => [ts, wh]));
    const gridFc = batFc.length
      ? batFc.map(([ts, , , grid]) => [ts, grid])
      : fc.map(([ts, power]) => {
          const hour = Math.floor(ts / 3600e3) * 3600e3;
          return [ts, Math.round(power - (pvByHour.get(hour) || 0))];
        });
    let socChart = "";
    if (!fc.length && !verified.length && !past.length) {
      forecastChart = `<div class="muted">${esc(t.noForecast)}</div>`;
    } else {
      // Visible range: scrollable between the first measurement and the forecast end.
      const span = this._flowSpan * 3600e3;
      const firsts = [past[0]?.[0], verified[0]?.[0]].filter((v) => v != null);
      const lasts = [fc.at(-1)?.[0], pvFc.at(-1)?.[0]].filter((v) => v != null);
      const dataMin = Math.min(now - 24 * 3600e3, ...firsts);
      const dataMax = Math.max(now + 3600e3, ...lasts.map((v) => v + 3600e3));
      this._flowBounds = { dataMin, dataMax, now };
      let fMax = this._flowEnd ?? now + (span * 2) / 3;
      fMax = Math.min(Math.max(fMax, dataMin + span), Math.max(dataMax, dataMin + span));
      const fMin = fMax - span;
      const fTicks = [];
      const step = this._flowSpan <= 24 ? 3 : this._flowSpan <= 72 ? 12 : 24;
      const d = new Date(fMin);
      d.setMinutes(0, 0, 0);
      d.setHours(Math.ceil(d.getHours() / step) * step);
      for (; d.getTime() < fMax; d.setHours(d.getHours() + step)) {
        const midnight = d.getHours() === 0;
        const label = midnight
          ? d.toLocaleDateString(lang, { weekday: "short", day: "numeric", month: "numeric" })
          : `${String(d.getHours()).padStart(2, "0")}:00`;
        fTicks.push([d.getTime(), label]);
      }
      const margin = 2 * 3600e3;
      const inView = (points) => points.filter(([ts]) => ts >= fMin - margin && ts <= fMax + margin);
      const slot = 3600e3;  // verification/forecast points are at most an hour apart
      forecastChart = this._chart(
        "forecast",
        [
          { points: past.map(([ts, house]) => [ts, house]), color: primary, label: t.houseMeasured },
          { points: verified.map(([ts, , predicted]) => [ts, predicted]), color: secondary, dashed: true, label: t.predicted },
          { points: fc.map(([ts, power]) => [ts, power]), color: primary, dashed: true, label: t.houseExpected },
          ...(h.has_pv || pvFc.length
            ? [
                { points: past.map(([ts, , , pv]) => [ts, pv]), color: pvColor, label: t.pvMeasured },
                { points: pvFc, color: pvColor, dashed: true, label: t.pvExpected },
              ]
            : []),
          ...(h.has_battery
            ? [{ points: past.map(([ts, , , , battery]) => [ts, battery]), color: batteryColor, label: t.batteryLine }]
            : []),
          ...(batFc.length
            ? [{ points: batFc.map(([ts, power]) => [ts, power]), color: batteryColor, dashed: true, label: t.batteryExpected }]
            : []),
          { points: gridPast, color: gridColor, label: t.gridMeasured },
          { points: gridFc, color: gridColor, dashed: true, label: t.gridExpected },
          ...(h.has_excluded
            ? [{ points: past.map(([ts, , excluded]) => [ts, excluded || null]), color: excludedColor, label: t.excludedLine }]
            : []),
        ].map((series) => ({ ...series, points: inView(series.points) })),
        fMin,
        fMax,
        fTicks,
        2 * 3600e3,
        now >= fMin && now <= fMax ? [[now, t.now]] : [],
        (v) =>
          new Date(v).toLocaleString(lang, {
            weekday: "short",
            day: "numeric",
            month: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          }),
      );
      this._charts.forecast.gapLimit = slot;

      // State of charge (kWh): measured total + per battery, plan ahead.
      const socBatteries = h.soc?.batteries || [];
      if (socBatteries.length) {
        const capacity = socBatteries.reduce((sum, b) => sum + b.capacity_kwh, 0);
        const totals = new Map();
        for (const b of socBatteries) {
          for (const [ts, kwh] of b.points) totals.set(ts, (totals.get(ts) || 0) + kwh);
        }
        const complete = [...totals.entries()]
          .filter(([ts]) => socBatteries.every((b) => b.points.some(([bts]) => bts === ts)))
          .sort((a, b) => a[0] - b[0]);
        const planned = (h.battery_forecast || []).map(([ts, , soc]) => [ts, (soc / 100) * capacity]);
        const kwhFmt = (v) => `${Number(v).toFixed(1)} kWh`;
        socChart = this._chart(
          "soc",
          [
            { points: inView(complete), color: batteryColor, label: t.socTotal },
            { points: inView(planned), color: batteryColor, dashed: true, label: t.socPlan },
          ],
          fMin,
          fMax,
          fTicks,
          2 * 3600e3,
          now >= fMin && now <= fMax ? [[now, t.now]] : [],
          this._charts.forecast.xFmt,
          kwhFmt,
        );
        const socInfo = this._charts.soc;
        socInfo.gapLimit = 3600e3;
        socInfo.extra = (ts) => {
          const rows = socBatteries.map((b) => {
            let value;
            let approx = "";
            if (ts <= Date.now()) {
              const hit = this._nearest(b.points, ts, 20 * 60e3);
              value = hit ? hit[1] : null;
            } else {
              const plan = this._nearest(planned, ts, 20 * 60e3);
              value = plan ? (plan[1] * b.capacity_kwh) / capacity : null;
              approx = "≈ ";
            }
            if (value == null) return "";
            const pct = Math.round((value / b.capacity_kwh) * 100);
            const name = `${b.name}${b.virtual ? ` (${t.virtual})` : ""}`;
            return `<div class="r muted"><span>${esc(name)}</span><b>${approx}${esc(kwhFmt(value))} · ${pct}%</b></div>`;
          });
          return rows.join("");
        };
      }
      // Tooltip extras: the deviation in the past, the usual deviation ahead.
      const accuracy = h.accuracy || {};
      const leadKey = (ms) => {
        const hours = ms / 3600e3;
        if (hours < 1) return "0-1h";
        if (hours < 6) return "1-6h";
        if (hours < 24) return "6-24h";
        if (hours < 48) return "1-2d";
        if (hours < 72) return "2-3d";
        if (hours < 120) return "3-5d";
        return "5d+";
      };
      const usual = (kind, ts, label, unit) => {
        const key = leadKey(ts - Date.now());
        const b = accuracy[kind]?.lead_times?.[key];
        if (!b || !b.samples || b.mae == null) return "";
        const value = kind === "pv" ? `${Math.round(b.mae)} ${unit}` : this._power(b.mae);
        return `<div class="r muted"><span>${esc(label)} (${esc(t.leads[key])})</span><b>± ${esc(value)}</b></div>`;
      };
      const chart = this._charts.forecast;
      chart.extra = (ts, hits) => {
        let html = "";
        const hit = (label) => hits[chart.series.findIndex((x) => x.label === label)] || null;
        const house = hit(t.houseMeasured);
        const predicted = hit(t.predicted);
        const expected = hit(t.houseExpected);
        const pvExpected = hit(t.pvExpected);
        if (house && predicted && house[0] === predicted[0]) {
          const diff = predicted[1] - house[1];
          const pct = house[1] ? ` (${diff >= 0 ? "+" : ""}${Math.round((diff / house[1]) * 100)}%)` : "";
          html += `<div class="r"><span>${esc(t.deviation)}</span><b>${diff >= 0 ? "+" : ""}${esc(this._power(diff))}${pct}</b></div>`;
        }
        const socHit = batFc.find(([bts]) => Math.abs(bts - ts) < 15 * 60e3);
        if (ts > Date.now() && socHit) {
          const cap = h.battery_capacity_kwh || 0;
          const kwh = cap ? ` · ${((socHit[2] / 100) * cap).toFixed(1)} / ${cap.toFixed(1)} kWh` : "";
          html += `<div class="r"><span><i style="background:${batteryColor}"></i>${esc(t.socExpected)}</span><b>${Math.round(socHit[2])}%${esc(kwh)}</b></div>`;
        }
        const none = (h.selected_vs_none || []).find(([cts]) => Math.abs(cts - ts) < 15 * 60e3);
        if (ts > Date.now() && none) {
          const v = none[1];
          html += `<div class="r muted"><span>${esc(t.vsNoneUntil)}</span><b>${v >= 0 ? "+" : ""}${esc(this._money(v, h))}</b></div>`;
        }
        const cmp = (h.arbitrage_vs_nom || []).find(([cts]) => Math.abs(cts - ts) < 15 * 60e3);
        if (ts > Date.now() && cmp) {
          const v = cmp[1];
          html += `<div class="r muted"><span>${esc(t.advantageUntil)}</span><b>${v >= 0 ? "+" : ""}${esc(this._money(v, h))}</b></div>`;
        }
        if (ts > Date.now()) {
          if (expected) html += usual("consumption", ts, t.usualHouse, "W");
          if (pvExpected) html += usual("pv", ts, t.usualPv, "Wh");
        }
        return html;
      };
    }
    const buckets = Object.values(h.accuracy?.consumption?.lead_times || {});
    const acc = buckets.find((b) => b.samples);
    const accText = acc
      ? t.accuracy.replace("{mae}", this._power(acc.mae)).replace("{mape}", acc.mape ?? "–")
      : t.notVerified;
    // Solid = measured, dashed = expected (also in the legend).
    const item = (color, label, dashed = false) =>
      `<span><i style="${dashed ? `background:none;border-top:2px dashed ${color};height:0` : `background:${color}`}"></i>${esc(label)}</span>`;
    const forecastLegend = `<div class="legend" style="flex-wrap:wrap">${[
      // One item per quantity: solid (measured) vs dashed (expected) is clear
      // from the chart itself; the tooltip still names each line.
      item(primary, t.houseMeasured),
      h.has_pv || pvFc.length ? item(pvColor, t.pvMeasured) : "",
      item(gridColor, t.gridMeasured),
      h.has_battery ? item(batteryColor, t.batteryLine) : "",
      h.has_excluded ? item(excludedColor, t.excludedLine) : "",
      item(secondary, t.predicted, true),
    ].join("")}</div>`;

    const info = t.daysOfData.replace("{days}", Math.round(h.days_covered)) + (h.imported ? ` · ${t.imported}` : "");
    return `<div class="card"><h2>${esc(t.consumption)} · ${esc(info)}</h2><div class="charts">
      <div class="chart wide"><div class="head"><h3>${esc(t.flowTitle)}</h3>${this._flowNav(t)}</div>${forecastChart}${forecastLegend}
        <div class="muted">${esc(accText)}</div>
        ${h.battery_forecast?.length ? `<div class="muted">${esc(this._planText(h, t))} · ${esc(t.batteryNote)}</div>` : ""}</div>
      ${socChart ? `<div class="chart wide"><h3>${esc(t.socTitle)}</h3>${socChart}</div>` : ""}
      <div class="chart"><h3>${esc(t.last7)}</h3>${week}${weekLegend}<div class="muted small">${esc(t.last7Info)}</div></div>
      <div class="chart"><div class="head"><h3>${esc(t.avgDay)}</h3>${this._dayNav(t, weeks, lang)}</div>${avg}
        <div class="legend"><span><i style="background:${primary}"></i>${esc(t.weekday)}</span>
        <span><i style="background:${accent}"></i>${esc(t.weekend)}</span>${shown ? `<span>${esc(t.allAverage)}</span>` : ""}</div>
        <div class="muted small">${esc(t.avgDayInfo)}</div></div>
    </div></div>`;
  }

  _accuracy(t) {
    const acc = this._history?.accuracy;
    if (!acc) return "";
    const unit = this._history.price_unit || "";
    const leads = Object.keys(t.leads);
    const any = Object.values(acc).some((k) => Object.values(k.lead_times).some((b) => b.samples));
    const fmt = (kind, v) => {
      if (v == null) return "–";
      if (kind === "price") return `${v.toFixed(3)} ${unit}`;
      return kind === "pv" ? `${Math.round(v)} Wh` : `${Math.round(v)} W`;
    };
    const corr = (kind, b) => {
      if (b.correction == null || (kind === "pv" ? b.correction === 1 : b.correction === 0)) return "";
      if (kind === "pv") return `×${b.correction.toFixed(2)}`;
      return kind === "price" ? `${b.correction >= 0 ? "+" : ""}${b.correction.toFixed(3)}` : `${b.correction >= 0 ? "+" : ""}${Math.round(b.correction)} W`;
    };
    const rows = Object.entries(acc)
      .map(([kind, k]) => {
        const cells = leads
          .map((lead) => {
            const b = k.lead_times[lead];
            if (!b || !b.samples) return "<td>–</td>";
            const c = corr(kind, b);
            return `<td title="${b.samples} · bias ${fmt(kind, b.bias)}${b.mape != null ? ` · ${b.mape}%` : ""}">${esc(fmt(kind, b.mae))}${c ? `<small>${esc(c)}</small>` : ""}</td>`;
          })
          .join("");
        return `<tr><td>${esc(t.accKinds[kind])}<small>${esc(t.accModes[k.mode] || k.mode)}</small></td>${cells}</tr>`;
      })
      .join("");
    const head = `<tr><th></th>${leads.map((l) => `<th>${esc(t.leads[l])}</th>`).join("")}</tr>`;
    const body = any
      ? `<div class="acc-wrap"><table class="acc">${head}${rows}</table></div><div class="muted">${esc(t.accHelp)}</div>`
      : `<div class="muted">${esc(t.accNoData)}</div>`;
    return `<div class="card"><h2>${esc(t.accTitle)}</h2>${body}</div>`;
  }

  _message(text) {
    // Long explanations: one sentence per line; the comparisons with other
    // modes ("Met …" / "With …") together in a smaller line at the end.
    const sentences = String(text).split(/(?<=[.!?])\s+(?=[A-Z€(])/u);
    if (sentences.length < 2) return esc(text);
    const compare = /^(Met |With |Let op: met |Note: with )/;
    const main = sentences.filter((x) => !compare.test(x));
    const other = sentences.filter((x) => compare.test(x));
    const [first, ...rest] = main;
    return `<div class="lead">${esc(first)}</div>${rest.map((x) => `<div>${esc(x)}</div>`).join("")}${
      other.length ? `<div class="muted small">${other.map(esc).join("<br>")}</div>` : ""
    }`;
  }

  _decisions(s, t) {
    const items = s.decisions.length
      ? `<ul class="decisions">${s.decisions.map((d) => `<li><time>${this._time(d.time)}</time><div>${this._message(d.message)}</div></li>`).join("")}</ul>`
      : `<div class="muted">${esc(t.noDecisions)}</div>`;
    return `<div class="card"><h2>${esc(t.decisions)}</h2>${items}</div>`;
  }

  _render() {
    if (!this._hass) return;
    const t = this._t;
    let body;
    if (this._error === "not_loaded") body = `<div class="card">${esc(t.notLoaded)}</div>`;
    else if (this._error) body = `<div class="card">${esc(t.error)}: ${esc(this._error)}</div>`;
    else if (!this._status) body = "";
    else {
      const s = this._status;
      const tabs = {
        overview: () => [this._flows(s, t), this._phases(s, t), this._decisions(s, t)],
        forecast: () => [this._consumption(t), this._planning(s, t)],
        value: () => [this._compare(s, t), this._planCheck(s, t)],
        batteries: () => [this._batteries(s, t)],
        check: () => [this._accuracy(t)],
      };
      const tab = tabs[this._tab] ? this._tab : "overview";
      const bar = Object.keys(tabs)
        .map((k) => `<button data-tab="${k}" class="${k === tab ? "active" : ""}">${esc(t.tabs[k])}</button>`)
        .join("");
      body = `<div class="tabs">${bar}</div>${tabs[tab]().join("")}`;
    }
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <div class="toolbar"><span class="menu"></span><span class="title">${esc(t.title)}</span>
        ${this._status ? `<button class="recalc" ${this._busy ? "disabled" : ""}>
          <ha-icon icon="mdi:refresh"></ha-icon>${esc(this._busy ? t.recalculating : t.recalculate)}</button>` : ""}</div>
      <div class="content">${body}</div>`;
    const menu = document.createElement("ha-menu-button");
    menu.hass = this._hass;
    menu.narrow = this._narrow;
    this.shadowRoot.querySelector(".menu").appendChild(menu);
    this.shadowRoot.querySelector(".recalc")?.addEventListener("click", () => this._recalculate());
    this.shadowRoot
      .querySelectorAll("button[data-mode]")
      .forEach((button) => button.addEventListener("click", () => this._setMode(button.dataset.mode)));
    this.shadowRoot.querySelectorAll("button[data-tab]").forEach((button) =>
      button.addEventListener("click", () => {
        this._tab = button.dataset.tab;
        this._hover = null;
        try {
          localStorage.setItem("homebatteryassist-tab", this._tab);
        } catch (err) {
          // no storage: the tab is not remembered
        }
        this._render();
      }),
    );
    this.shadowRoot.querySelector('button[data-toggle="compare"]')?.addEventListener("click", () => {
      this._showCompare = !this._showCompare;
      this._render();
    });
    this._bindCharts();
    this._bindFlowNav();
    this._showHover();
  }
}

// A new version of the panel may be loaded next to an old one: define once.
if (!customElements.get("homebatteryassist-panel")) {
  customElements.define("homebatteryassist-panel", HomeBatteryAssistPanel);
}
