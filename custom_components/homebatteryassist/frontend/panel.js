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
    priceNowAt: "Now ({time})",
    fdTitle: "Energy flows",
    fdToday: "today",
    fdExpected: "expected",
    bandSun: "Solar",
    bandPv: "Charging with solar",
    bandGrid: "Charging from the grid",
    bandDischarge: "Battery discharging",
    fdTotal: "total",
    fdLive: "Today (live)",
    fdOlder: "Day before",
    fdNewer: "Day after",
    fdDayNote: "The energy of that day (kWh) per part and per flow; the thicker the line, the more energy went along it.",
    fdImport: "→ import",
    fdExport: "← export",
    fdCharge: "↓ charge",
    fdDischarge: "↑ discharge",
    fdTodayTotal: "Today so far",
    fdExcluded: "Excluded devices",
    fdPartOfHouse: "part of the house",
    tempTitle: "Temperature and heating/cooling",
    tempOutdoor: "Outdoor (forecast)",
    tempRoom: "Room (learned)",
    tempPower: "Heating/cooling (expected)",
    tempKwh: "Expected heating/cooling: {days}",
    tempLearning: "The effect of the temperature is still being learned (7 days with temperature needed); for now only the forecast outdoor temperature.",
    priceFromAt: "From {time}",
    priceCols: ["Market", "Import", "Export"],
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
    cmdLabel: "Command",
    cmdCharge: "charge {w}",
    cmdDischarge: "discharge {w}",
    cmdStop: "stop",
    cmdInfo: "What the battery is told to do now by the integration that controls it (in this phase not HomeBatteryAssist), and whether it follows.",
    cmdProblem: "Does not follow its command since {t}",
    cmdExplained: "Does not follow its command since {t}: {r}",
    cmdReasons: {
      full: "full",
      tapering: "almost full",
      cold: "cold",
      empty: "at its minimum",
      charge_off: "charging switched off",
      discharge_off: "discharging switched off",
      hysteresis: "hysteresis after full",
    },
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
      cell_spread_v: ["Cell difference", "V", 3],
      cell_delta_v: ["Cell difference at 100%", "V", 3],
      cycles: ["Cycles", "", 0],
      charged_today_kwh: ["Charged today", "kWh", 2],
      discharged_today_kwh: ["Discharged today", "kWh", 2],
      efficiency_measured_pct: ["Efficiency (measured by HBA)", "%", 1],
      efficiency_pct: ["Efficiency (according to the battery)", "%", 1],
    },
    allPhases: "all phases",
    withVirtual: "with virtual batteries",
    withTwin: "with the twin instead",
    realBattery: "Real battery",
    twinDiff: "Difference today (twin − real)",
    twinOf: "twin of {name}",
    ownControl: "own control, outside the plan",
    phaseLimit: "limit {a} A (fuse with {m}% margin)",
    fromGrid: "from the grid",
    phaseTotal: "Total",
    phaseTotalOf: "net, of 3 × {a} A",
    toGrid: "to the grid",
    relief: "phase protection: batteries take {w} off",
    limitedNow: "batteries held back by the limit",
    peakNow: "peak shaving: {w} taken off (limit {l})",
    peakSet: "peak limit {l}",
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
    summaryTitle: "The plan at a glance",
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
    dayTotals: "Per day",
    dayTotalsAll: "All",
    dayTotalsWeek: "Week",
    dayTotalsAvg: "Avg.",
    dayTotalsInfo: "kWh per day: the sum of the 24 hourly averages.",
    last7Info:
      "What the house itself used, averaged per hour: grid import + solar production − excluded devices − battery charging (+ battery discharging). Excluded devices (e.g. an EV charger) are not in the house line and are not forecast. Hover over the line for the exact hour and value.",
    avgDayInfo:
      "The same house consumption, averaged per hour of the day over all history (up to 28 days), for every day of the week separately (dashed: all days together). This is the typical day pattern; the consumption forecast uses it per day of the week, with recent days counting more. Use ◀ ▶ to see a single week next to the overall average and spot changes.",
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
    planModes: { nom: "NOM", arbitrage: "arbitrage own use", arbitrage_full: "arbitrage with export", time_slots: "time slots", manual: "manual" },
    planInfo: "Battery plan ({mode}, advice): expected saving {saving}",
    plannerActive: "Active planner:",
    plannerBuiltin: "built-in",
    plannerOwn: "own module",
    plannerSaving: "expected saving {saving} until {until} compared with no battery",
    plannerFallback: "This planner failed or is missing: zero on the meter is used instead (see Why).",
    plannerForecaster: "Consumption forecast:",
    plannerTariff: "Tariff:",
    moduleFallback: "failed or missing, built-in used",
    chosen: "chosen",
    forecasterNames: { profile: "Weekday and hour profile", last_weeks: "Same time in the last weeks" },
    pvCorrectorNames: { hour_and_level: "Per lead time, hour and level", lead_time: "Per lead time (original)" },
    plannerPvCorrector: "PV correction:",
    plannerInterceptor: "Interceptor:",
    controlLine: "Control:",
    controlModes: { nom: "zero on the meter", plan: "following the plan" },
    controlActive: "active",
    controlHeld: { test: "test running", not_following: "does not follow", meter: "meter gone", unknown: "state unknown", oscillating: "paused (oscillating)" },
    icAllThrough: "lets everything through",
    icActions: { reject: "held back", release: "released", limit: "limited to" },
    pvCorrectorsTitle: "PV corrections compared",
    pvCorrectorsHelp: "Average deviation of the PV forecast after each correction per lead time; the best in bold, 'uncorrected' for reference. All corrections are calculated every cycle, also when they are not chosen — choose one in the settings.",
    uncorrected: "Uncorrected",
    tariffNames: { source: "As the price source gives them" },
    forecastersTitle: "Consumption forecasters compared",
    forecastersHelp: "Average deviation of each forecaster's own prediction (before corrections) per lead time; the best in bold. All forecasters are calculated every cycle, also when they are not chosen — choose one in the settings.",
    planOther: "{mode}: {saving}",
    socExpected: "Expected state of charge",
    socTitle: "State of charge of the batteries",
    priceTitle: "Electricity price",
    priceAxis: "Price per kWh",
    priceAverage: "Average price (shown period)",
    exportAxis: "Export earns per kWh",
    priceImport: "Price (published)",
    priceImportFc: "Price (forecast)",
    priceExport: "Export earns (published)",
    priceExportFc: "Export earns (forecast)",
    priceInfo: "Solid: published prices; dashed: forecast (estimated). The price is what one kWh from the grid costs (all-in); export is what one kWh to the grid earns.",
    socTotal: "Total",
    bandFill: "Battery fill (background)",
    socPlan: "Total (plan)",
    realized: "Realised return",
    notYet: "no charging or discharging yet",
    expectedReturn: "Expected return",
    vsNoBattery: "vs no battery",
    vsMode: "{mode} vs {other}",
    modeNames: { nom: "Zero on the meter", arbitrage: "Arbitrage own use", arbitrage_full: "Arbitrage with export", time_slots: "Time slots", manual: "Manual" },
    compareTitle: "Return compared",
    evTitle: "Charge the car",
    evButton: "Charge the car",
    evNote: "When to switch the charging on for the lowest expected cost: one block, from the prices and the expected solar surplus of the plan. Advice only: nothing is switched.",
    evKwh: "Energy to charge (kWh, from the grid connection)",
    evPower: "Charging power (kW)",
    evFrom: "Not before",
    evUntil: "Ready by",
    evCalculate: "Calculate",
    evClose: "Close",
    evAdvice: "Switch on {start}, off {end}",
    evCost: "Expected cost {cost} (on average {avg}/kWh)",
    evSun: "of which {kwh} kWh from the solar surplus",
    evNow: "Starting at once ({start}): {cost}",
    evPricesUntil: "Prices known until {until}.",
    evReason: {
      invalid: "Fill in the energy, the power and a period that ends after it starts.",
      too_short: "The period is too short for this energy at this power.",
      beyond_prices: "The prices do not reach far enough: known until {until}. Choose an earlier end, or try again when tomorrow's prices are out.",
      no_prices: "There are no prices in the plan (yet).",
    },
    evFailed: "Calculating failed",
    adjTitle: "Occasional consumption",
    adjNote: "Tell the forecast about consumption it cannot know from the history, e.g. 1.5 kWh for the washing machine tomorrow 13:00–15:00. Extra comes on top of the learned consumption; part of the expected consumption moves that much of the day's expected consumption into the time window.",
    adjNone: "Nothing set.",
    adjButton: "Occasional consumption",
    adjClose: "Close",
    adjAdd: "Add",
    adjEdit: "Change",
    adjDelete: "Remove",
    adjName: "Name",
    adjNamePlaceholder: "e.g. washing machine",
    adjDay: "Day",
    adjFrom: "From (optional)",
    adjUntil: "Until (optional)",
    adjEnergy: "Energy (kWh)",
    adjExtra: "Extra, on top of the expected consumption",
    adjPart: "Part of the day's expected consumption (needs a time window)",
    adjPartShort: "part of the expected",
    adjExtraShort: "extra",
    adjWholeDay: "whole day",
    adjSave: "Save",
    adjCancel: "Cancel",
    adjByAction: "via action",
    adjNeedWindow: "Give a time window (from and until), or choose extra.",
    adjNeedEnergy: "Give an amount of energy in kWh.",
    adjFailed: "Saving failed",
    tabs: { overview: "Overview", forecast: "Forecast", value: "Return", batteries: "Batteries", check: "Accuracy", log: "Log" },
    logTitle: "Activity log",
    logHelp: "What each real battery did, per period: who decided it (HomeBatteryAssist's control, a test, the battery's own control, or an incident) and whether it was what the plan said. Kept 30 days.",
    logEmpty: "Nothing logged yet (a line is added every minute).",
    logCols: ["From", "To", "Battery", "Activity", "kWh", "Max W", "Price", "By", "Plan", "Reason"],
    logReasons: {
      house_demand: "the house asks for power",
      solar_surplus: "solar surplus",
      balanced: "grid in balance",
      spike: "short peak ignored",
      empty: "empty (minimum)",
      full: "full (maximum)",
      min_soc_guard: "charged back to the minimum",
      plan_charge: "plan: charge",
      plan_discharge: "plan: deliver",
      plan_idle: "plan: wait",
      test: "test by hand",
      not_following: "does not follow",
      meter: "grid measurement gone",
      unknown: "state unknown",
      oscillating: "paused (oscillating)",
      connection: "connection gone",
      released: "released (start/stop)",
      not_controlled: "not controlled by HBA",
    },
    logKinds: { charge_pv: "Charge (solar)", charge_grid: "Charge (grid)", discharge: "Discharge", idle: "Idle" },
    logSources: { hba_nom: "HBA: zero on the meter", hba_plan: "HBA: plan", test: "Test (by hand)", own: "Own control", incident: "Incident" },
    logPlan: { charge: "charge", discharge: "discharge", idle: "idle" },
    logDays: "days",
    logDay: "day",
    logCsv: "CSV",
    compareShow: "Return overview ▾",
    compareHide: "Hide overview ▴",
    realizedShort: "realised so far",
    checkTitle: "Plan versus reality (per day)",
    checkDay: "Day",
    checkPlanned: "Planned saving",
    checkRealized: "Realised",
    checkDiff: "Difference",
    checkDev: "Avg. power deviation",
    checkVirtual: "Followed (virtual)",
    checkReal: "Followed (real)",
    checkNote: "Per slot the plan when the slot started, compared with what all batteries (also virtual) really did and brought. Followed: how closely the batteries' power matched their share of the plan, per slot (100% = exactly; idle as planned counts as followed). In this phase your real batteries are controlled by their own integration, so their figure shows how close that comes to this plan.",
    followTitle: "Plan followed (last {d} days)",
    followVirtual: "Virtual batteries",
    followReal: "Real batteries",
    followHelp: "How closely the batteries' power matched their share of the plan, per slot, on average. Virtual batteries follow the plan (lower = they hit a limit, or the sun differed from the forecast). Real batteries are in this phase controlled by their own integration: this shows how close that comes to HomeBatteryAssist's plan.",
    followNone: "Not measured yet.",
    checkEmpty: "No complete slots measured yet.",
    modeLabel: "Plan mode",
    modeSwitching: "switching…",
    vsNone: "vs no battery",
    selected: "selected",
    realizedRow: "Realised ({mode}, after wear)",
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
    spans: { today: "Today", tomorrow: "Today + tomorrow", all: "Whole forecast" },
    reviewOpen: "Look back",
    reviewOpenTitle: "An earlier day: what happened against what was forecast",
    reviewLive: "Live",
    reviewOlder: "A day earlier",
    reviewNewer: "A day later",
    leadAhead: "Forecast well before",
    leadAheadTitle: "The forecast made 6–24 hours before (what the plan was mostly built on)",
    leadLate: "Forecast shortly before",
    leadLateTitle: "The last forecast, shortly before the moment itself",
    reviewForecast: "forecast",
    reviewPlanned: "Battery planned",
    reviewPriceEst: "Price (estimated then)",
    reviewMore: "More than forecast",
    reviewLess: "Less than forecast",
    reviewNone: "No history for this day.",
    reviewLoading: "Loading…",
    reviewFollowed: "plan followed",
    reviewAvgPrice: "Average price",
    reviewEstimated: "estimated",
    reviewInfo: "Solid: what happened; dashed: what was forecast for it then. The coloured area shows where the house used more (red) or less (green) than forecast.",
    now: "now",
    accuracy: "Average deviation (shortest lead time): {mae} ({mape}%)",
    notVerified: "Not checked yet: measured slots are compared with the forecast as time passes.",
    noForecast: "No consumption forecast yet.",
    reachTitle: "How far the forecasts reach",
    accTitle: "Forecast accuracy (running, last weeks)",
    accHelp: "Per lead time: average deviation, and the correction applied to new forecasts.",
    accKinds: { consumption: "Consumption", heating: "of which heating/cooling", pv: "PV", price: "Prices" },
    accModes: { learned: "learned", off: "off", manual: "manual" },
    accNoData: "No comparisons yet: forecasts are checked as soon as the real values are known.",
    leads: { "0-1h": "0-1 h", "1-6h": "1-6 h", "6-24h": "6-24 h", "1-2d": "1-2 d", "2-3d": "2-3 d", "3-5d": "3-5 d", "5d+": "5+ d" },
    reachConsumption: "Consumption",
    reachPrice: "Prices",
    reachWeather: "Outdoor temperature",
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
    priceNowAt: "Nu ({time})",
    fdTitle: "Energiestromen",
    fdToday: "vandaag",
    fdExpected: "verwacht",
    bandSun: "Zon",
    bandPv: "Laden met zonne-energie",
    bandGrid: "Laden vanaf net",
    bandDischarge: "Batterij ontladen",
    fdTotal: "totaal",
    fdLive: "Vandaag (live)",
    fdOlder: "Dag ervoor",
    fdNewer: "Dag erna",
    fdDayNote: "De energie van die dag (kWh) per onderdeel en per stroom; hoe dikker de lijn, hoe meer energie erlangs ging.",
    fdImport: "→ afname",
    fdExport: "← terug",
    fdCharge: "↓ laden",
    fdDischarge: "↑ ontladen",
    fdTodayTotal: "Vandaag tot nu",
    fdExcluded: "Uitgesloten apparaten",
    fdPartOfHouse: "deel van het huis",
    tempTitle: "Temperatuur en verwarming/koeling",
    tempOutdoor: "Buiten (verwacht)",
    tempRoom: "Kamer (geleerd)",
    tempPower: "Verwarming/koeling (verwacht)",
    tempKwh: "Verwacht verbruik verwarming/koeling: {days}",
    tempLearning: "Het effect van de temperatuur wordt nog geleerd (7 dagen met temperatuur nodig); voorlopig alleen de verwachte buitentemperatuur.",
    priceFromAt: "Vanaf {time}",
    priceCols: ["Beurs", "Inkoop", "Verkoop"],
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
    cmdLabel: "Opdracht",
    cmdCharge: "laden {w}",
    cmdDischarge: "ontladen {w}",
    cmdStop: "stoppen",
    cmdInfo: "Wat de batterij nu opgedragen krijgt van de integratie die haar aanstuurt (in deze fase niet HomeBatteryAssist), en of ze dat volgt.",
    cmdProblem: "Volgt opdracht niet sinds {t}",
    cmdExplained: "Volgt opdracht niet sinds {t}: {r}",
    cmdReasons: {
      full: "vol",
      tapering: "bijna vol",
      cold: "koud",
      empty: "op minimum",
      charge_off: "laden uitgeschakeld",
      discharge_off: "ontladen uitgeschakeld",
      hysteresis: "hysterese na vol",
    },
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
      cell_spread_v: ["Celverschil", "V", 3],
      cell_delta_v: ["Celverschil bij 100%", "V", 3],
      cycles: ["Cycli", "", 0],
      charged_today_kwh: ["Geladen vandaag", "kWh", 2],
      discharged_today_kwh: ["Ontladen vandaag", "kWh", 2],
      efficiency_measured_pct: ["Rendement (gemeten door HBA)", "%", 1],
      efficiency_pct: ["Rendement (volgens de batterij)", "%", 1],
    },
    allPhases: "alle fasen",
    withVirtual: "met virtuele batterijen",
    withTwin: "met de tweeling ervoor in de plaats",
    realBattery: "Echte batterij",
    twinDiff: "Verschil vandaag (tweeling − echt)",
    twinOf: "tweeling van {name}",
    ownControl: "eigen sturing, buiten het plan",
    phaseLimit: "grens {a} A (zekering met {m}% marge)",
    fromGrid: "van het net",
    phaseTotal: "Totaal",
    phaseTotalOf: "saldo, van 3 × {a} A",
    toGrid: "naar het net",
    relief: "fasebeveiliging: batterijen nemen {w} over",
    limitedNow: "batterijen teruggeschroefd door de grens",
    peakNow: "piekafvlakking: {w} opgevangen (grens {l})",
    peakSet: "piekgrens {l}",
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
    summaryTitle: "Het plan in het kort",
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
    dayTotals: "Per dag",
    dayTotalsAll: "Alles",
    dayTotalsWeek: "Week",
    dayTotalsAvg: "Gem.",
    dayTotalsInfo: "kWh per dag: de som van de 24 uurgemiddelden.",
    last7Info:
      "Wat het huis zelf verbruikte, gemiddeld per uur: afname van het net + zonne-opwek − uitgesloten apparaten − laden van de batterij (+ ontladen). Uitgesloten apparaten (bijv. een laadpaal) zitten niet in de huislijn en worden niet voorspeld. Wijs de lijn aan voor het precieze uur en de waarde.",
    avgDayInfo:
      "Hetzelfde huisverbruik, gemiddeld per uur van de dag over alle geschiedenis (tot 28 dagen), apart voor elke dag van de week (gestippeld: alle dagen samen). Zo zie je het vaste dagpatroon; de verbruiksvoorspelling gebruikt dit per dag van de week, waarbij recente dagen zwaarder tellen. Met ◀ ▶ blader je per week; het gemiddelde van alle geschiedenis staat gestippeld ernaast, zodat je veranderingen ziet.",
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
    planModes: { nom: "NOM", arbitrage: "arbitrage eigen gebruik", arbitrage_full: "arbitrage met teruglevering", time_slots: "tijdvakken", manual: "handmatig" },
    planInfo: "Batterijplan ({mode}, advies): verwachte besparing {saving}",
    plannerActive: "Actieve planningsmodule:",
    plannerBuiltin: "ingebouwd",
    plannerOwn: "eigen module",
    plannerSaving: "verwachte besparing {saving} tot {until} t.o.v. geen batterij",
    plannerFallback: "Deze module gaf een fout of ontbreekt: nul op de meter wordt gebruikt (zie Waarom).",
    plannerForecaster: "Verbruiksvoorspelling:",
    plannerTariff: "Tarief:",
    moduleFallback: "fout of ontbreekt, ingebouwde gebruikt",
    chosen: "gekozen",
    forecasterNames: { profile: "Profiel per weekdag en uur", last_weeks: "Zelfde tijd afgelopen weken" },
    pvCorrectorNames: { hour_and_level: "Per vooruitzicht, uur en niveau", lead_time: "Per vooruitzicht (oorspronkelijk)" },
    plannerPvCorrector: "PV-correctie:",
    plannerInterceptor: "Onderschepper:",
    controlLine: "Besturing:",
    controlModes: { nom: "nul op de meter", plan: "volgens het plan" },
    controlActive: "actief",
    controlHeld: { test: "test loopt", not_following: "volgt niet", meter: "meter weg", unknown: "stand onbekend", oscillating: "gepauzeerd (slingert)" },
    icAllThrough: "laat alles door",
    icActions: { reject: "tegengehouden", release: "vrijgegeven", limit: "beperkt tot" },
    pvCorrectorsTitle: "PV-correcties vergeleken",
    pvCorrectorsHelp: "Gemiddelde afwijking van de PV-voorspelling na elke correctie per vooruitzicht; de beste vetgedrukt, 'ongecorrigeerd' ter vergelijking. Alle correcties worden elke cyclus doorgerekend, ook als ze niet gekozen zijn — kies er een in de instellingen.",
    uncorrected: "Ongecorrigeerd",
    tariffNames: { source: "Zoals de prijsbron ze geeft" },
    forecastersTitle: "Verbruiksvoorspellers vergeleken",
    forecastersHelp: "Gemiddelde afwijking van de eigen voorspelling van elke voorspeller (vóór correcties) per vooruitzicht; de beste vetgedrukt. Alle voorspellers worden elke cyclus doorgerekend, ook als ze niet gekozen zijn — kies er een in de instellingen.",
    planOther: "{mode}: {saving}",
    socExpected: "Verwachte vulling",
    socTitle: "Vulling batterijen",
    priceTitle: "Stroomprijs",
    priceAxis: "Prijs per kWh",
    priceAverage: "Gemiddelde prijs (getoonde periode)",
    exportAxis: "Teruglevering per kWh",
    priceImport: "Prijs (gepubliceerd)",
    priceImportFc: "Prijs (voorspeld)",
    priceExport: "Teruglevering (gepubliceerd)",
    priceExportFc: "Teruglevering (voorspeld)",
    priceInfo: "Doorgetrokken: gepubliceerde prijzen; gestippeld: voorspelling (geschat). De prijs is wat een kWh van het net kost (all-in); teruglevering is wat een kWh naar het net oplevert.",
    socTotal: "Totaal",
    bandFill: "Batterijvulling (achtergrond)",
    socPlan: "Totaal (plan)",
    realized: "Gerealiseerd rendement",
    notYet: "nog niet geladen of ontladen",
    expectedReturn: "Verwacht rendement",
    vsNoBattery: "t.o.v. geen batterij",
    vsMode: "{mode} t.o.v. {other}",
    modeNames: { nom: "Nul op de meter", arbitrage: "Arbitrage eigen gebruik", arbitrage_full: "Arbitrage met teruglevering", time_slots: "Tijdvakken", manual: "Handmatig" },
    compareTitle: "Rendement vergeleken",
    evTitle: "Auto laden",
    evButton: "Auto laden",
    evNote: "Wanneer je het laden het best aanzet voor de laagste verwachte kosten: één blok, uit de prijzen en het verwachte zonne-overschot van het plan. Alleen advies: er wordt niets geschakeld.",
    evKwh: "Te laden energie (kWh, vanaf de netaansluiting)",
    evPower: "Laadvermogen (kW)",
    evFrom: "Niet vóór",
    evUntil: "Klaar om",
    evCalculate: "Bereken",
    evClose: "Sluiten",
    evAdvice: "Aanzetten {start}, uit {end}",
    evCost: "Verwachte kosten {cost} (gemiddeld {avg}/kWh)",
    evSun: "waarvan {kwh} kWh uit het zonne-overschot",
    evNow: "Meteen beginnen ({start}): {cost}",
    evPricesUntil: "Prijzen bekend tot {until}.",
    evReason: {
      invalid: "Vul de energie, het vermogen en een periode in die na het begin eindigt.",
      too_short: "De periode is te kort voor deze energie bij dit vermogen.",
      beyond_prices: "De prijzen reiken niet ver genoeg: bekend tot {until}. Kies een eerder einde, of probeer het opnieuw als de prijzen van morgen er zijn.",
      no_prices: "Er zijn (nog) geen prijzen in het plan.",
    },
    evFailed: "Berekenen mislukt",
    adjTitle: "Incidenteel verbruik",
    adjNote: "Vertel de voorspelling over verbruik dat hij niet uit de geschiedenis kan weten, bijv. 1,5 kWh voor de wasmachine morgen 13:00–15:00. Extra komt bovenop het geleerde verbruik; deel van het verwachte verbruik verschuift zoveel van het verwachte verbruik van die dag naar het tijdvenster.",
    adjNone: "Niets ingesteld.",
    adjButton: "Incidenteel verbruik",
    adjClose: "Sluiten",
    adjAdd: "Toevoegen",
    adjEdit: "Wijzigen",
    adjDelete: "Verwijderen",
    adjName: "Naam",
    adjNamePlaceholder: "bijv. wasmachine",
    adjDay: "Dag",
    adjFrom: "Van (optioneel)",
    adjUntil: "Tot (optioneel)",
    adjEnergy: "Energie (kWh)",
    adjExtra: "Extra, bovenop het verwachte verbruik",
    adjPart: "Deel van het verwachte verbruik van die dag (vraagt een tijdvenster)",
    adjPartShort: "deel van het verwachte",
    adjExtraShort: "extra",
    adjWholeDay: "hele dag",
    adjSave: "Opslaan",
    adjCancel: "Annuleren",
    adjByAction: "via actie",
    adjNeedWindow: "Geef een tijdvenster (van en tot), of kies extra.",
    adjNeedEnergy: "Geef een hoeveelheid energie in kWh.",
    adjFailed: "Opslaan mislukt",
    tabs: { overview: "Overzicht", forecast: "Voorspelling", value: "Rendement", batteries: "Batterijen", check: "Nauwkeurigheid", log: "Log" },
    logTitle: "Activiteitenlog",
    logHelp: "Wat elke echte batterij deed, per periode: wie het besliste (de besturing van HomeBatteryAssist, een test, de eigen sturing van de batterij, of een incident) en of het was wat het plan zei. 30 dagen bewaard.",
    logEmpty: "Nog niets gelogd (elke minuut komt er een regel bij).",
    logCols: ["Van", "Tot", "Batterij", "Activiteit", "kWh", "Max W", "Prijs", "Door", "Plan", "Reden"],
    logReasons: {
      house_demand: "huis vraagt stroom",
      solar_surplus: "zonne-overschot",
      balanced: "net in balans",
      spike: "korte piek genegeerd",
      empty: "leeg (ondergrens)",
      full: "vol (bovengrens)",
      min_soc_guard: "bijgeladen tot ondergrens",
      plan_charge: "plan: laden",
      plan_discharge: "plan: leveren",
      plan_idle: "plan: wachten",
      test: "test (handmatig)",
      not_following: "volgt niet",
      meter: "netmeting weg",
      unknown: "stand onbekend",
      oscillating: "gepauzeerd (slingert)",
      connection: "verbinding weg",
      released: "losgelaten (start/stop)",
      not_controlled: "niet door HBA aangestuurd",
    },
    logKinds: { charge_pv: "Laden (zon)", charge_grid: "Laden (net)", discharge: "Ontladen", idle: "Rust" },
    logSources: { hba_nom: "HBA: nul op de meter", hba_plan: "HBA: plan", test: "Test (handmatig)", own: "Eigen sturing", incident: "Incident" },
    logPlan: { charge: "laden", discharge: "ontladen", idle: "rust" },
    logDays: "dagen",
    logDay: "dag",
    logCsv: "CSV",
    compareShow: "Rendement overzicht ▾",
    compareHide: "Overzicht verbergen ▴",
    realizedShort: "tot nu gerealiseerd",
    checkTitle: "Plan tegen werkelijkheid (per dag)",
    checkDay: "Dag",
    checkPlanned: "Verwachte besparing",
    checkRealized: "Gerealiseerd",
    checkDiff: "Verschil",
    checkDev: "Gem. afwijking vermogen",
    checkVirtual: "Gevolgd (virtueel)",
    checkReal: "Gevolgd (echt)",
    checkNote: "Per tijdvak het plan bij de start ervan, vergeleken met wat alle batterijen (ook virtuele) echt deden en opleverden. Gevolgd: hoe dicht het vermogen van de batterijen per kwartier bij hun deel van het plan lag (100% = precies; niets doen zoals gepland telt als gevolgd). In deze fase worden je echte batterijen door hun eigen integratie aangestuurd; hun cijfer laat zien hoe dicht die bij dit plan komt.",
    followTitle: "Plan gevolgd (afgelopen {d} dagen)",
    followVirtual: "Virtuele batterijen",
    followReal: "Echte batterijen",
    followHelp: "Hoe dicht het vermogen van de batterijen per tijdvak gemiddeld bij hun deel van het plan lag. Virtuele batterijen volgen het plan (lager = ze liepen tegen een grens aan, of de zon week af van de voorspelling). Echte batterijen worden in deze fase door hun eigen integratie aangestuurd: dit laat zien hoe dicht die bij het plan van HomeBatteryAssist komt.",
    followNone: "Nog niet gemeten.",
    checkEmpty: "Nog geen volledige kwartieren gemeten.",
    modeLabel: "Planmodus",
    modeSwitching: "wisselen…",
    vsNone: "t.o.v. geen batterij",
    selected: "gekozen",
    realizedRow: "Gerealiseerd ({mode}, na slijtage)",
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
    spans: { today: "Vandaag", tomorrow: "Vandaag + morgen", all: "Hele voorspelling" },
    reviewOpen: "Terugkijken",
    reviewOpenTitle: "Een eerdere dag: wat er gebeurde tegenover wat er voorspeld was",
    reviewLive: "Live",
    reviewOlder: "Een dag eerder",
    reviewNewer: "Een dag later",
    leadAhead: "Voorspelling ruim vooraf",
    leadAheadTitle: "De voorspelling van 6–24 uur vooraf (waar het plan vooral op rekende)",
    leadLate: "Voorspelling vlak vooraf",
    leadLateTitle: "De laatste voorspelling, vlak voor het moment zelf",
    reviewForecast: "voorspeld",
    reviewPlanned: "Batterij gepland",
    reviewPriceEst: "Prijs (toen geschat)",
    reviewMore: "Meer dan voorspeld",
    reviewLess: "Minder dan voorspeld",
    reviewNone: "Geen historie voor deze dag.",
    reviewLoading: "Laden…",
    reviewFollowed: "plan gevolgd",
    reviewAvgPrice: "Gemiddelde prijs",
    reviewEstimated: "geschat",
    reviewInfo: "Doorgetrokken: wat er gebeurde; gestippeld: wat er toen voor voorspeld was. Het gekleurde vlak laat zien waar het huis meer (rood) of minder (groen) verbruikte dan voorspeld.",
    now: "nu",
    accuracy: "Gemiddelde afwijking (kortste vooruitzicht): {mae} ({mape}%)",
    notVerified: "Nog niet gecontroleerd: gemeten tijdvakken worden in de loop van de tijd met de voorspelling vergeleken.",
    noForecast: "Nog geen verbruiksvoorspelling.",
    reachTitle: "Hoe ver de voorspellingen reiken",
    accTitle: "Nauwkeurigheid voorspellingen (meelopend, afgelopen weken)",
    accHelp: "Per vooruitzicht: gemiddelde afwijking, en de correctie die op nieuwe voorspellingen wordt toegepast.",
    accKinds: { consumption: "Verbruik", heating: "waarvan verwarming/koeling", pv: "PV", price: "Prijzen" },
    accModes: { learned: "geleerd", off: "uit", manual: "handmatig" },
    accNoData: "Nog geen vergelijkingen: voorspellingen worden gecontroleerd zodra de werkelijke waarden bekend zijn.",
    leads: { "0-1h": "0-1 u", "1-6h": "1-6 u", "6-24h": "6-24 u", "1-2d": "1-2 d", "2-3d": "2-3 d", "3-5d": "3-5 d", "5d+": "5+ d" },
    reachConsumption: "Verbruik",
    reachPrice: "Prijzen",
    reachWeather: "Buitentemperatuur",
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
  .fd { position: relative; max-width: 640px; margin: 8px auto 4px; aspect-ratio: 520 / 460; }
  .fd svg { position: absolute; inset: 0; width: 100%; height: 100%; }
  .fd-totals { text-align: center; }
  .fd-chips { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px 8px; margin-top: 6px; }
  /* Wide: today's totals in a column to the right of the diagram; narrow: below it. */
  .fd-wrap { display: flex; align-items: center; justify-content: center; gap: 16px; }
  .fd-wrap .fd { flex: 1 1 auto; min-width: 0; margin-left: 0; margin-right: 0; }
  .fd-wrap .fd-totals { flex: 0 0 220px; text-align: left; }
  .fd-wrap .fd-chips { flex-direction: column; align-items: stretch; flex-wrap: nowrap; }
  @media (max-width: 900px) {
    .fd-wrap { flex-direction: column; align-items: stretch; }
    .fd-wrap .fd { margin: 8px auto 4px; width: 100%; }
    .fd-wrap .fd-totals { flex: none; text-align: center; }
    .fd-wrap .fd-chips { flex-direction: row; flex-wrap: wrap; justify-content: center; }
  }
  .fd-chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px 4px 8px; border-radius: 12px; font-size: 13px;
    border: 1px solid var(--divider-color); border-left: 3px solid var(--fd-color); text-align: left; line-height: 1.25; }
  .fd-chip ha-icon { --mdc-icon-size: 18px; color: var(--fd-color); }
  .review-chips { margin: 8px 0 4px; }
  .fd-chip b { font-weight: 500; }
  .fd-chip small { display: block; font-size: 11px; color: var(--secondary-text-color); }
  .card > .head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
  .fd-flow { font-size: 12px; font-weight: 600; text-anchor: middle; paint-order: stroke; stroke: var(--card-background-color, #1c1c1c); stroke-width: 3px; }
  .fd-line { fill: none; stroke-width: 2; opacity: .45; }
  .fd-line.on { opacity: .9; }
  .fd-node { position: absolute; transform: translate(-50%, -44px); width: 150px;
    display: flex; flex-direction: column; align-items: center; pointer-events: none; }
  .fd-circle { width: 88px; height: 88px; border-radius: 50%; border: 3px solid var(--fd-color); box-sizing: border-box;
    background: var(--card-background-color, var(--ha-card-background, #1c1c1c));
    display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }
  .fd-circle ha-icon { --mdc-icon-size: 22px; color: var(--fd-color); }
  .fd-circle b { font-size: 14px; font-weight: 600; white-space: nowrap; }
  .fd-circle small { font-size: 11px; color: var(--secondary-text-color); white-space: pre-line; line-height: 1.2; }
  .fd-info { margin-top: 3px; padding: 2px 6px; border-radius: 6px;
    background: var(--card-background-color, var(--ha-card-background, #1c1c1c)); text-align: center; }
  .fd-name { font-size: 12px; font-weight: 500; color: var(--primary-text-color); white-space: nowrap; }
  .fd-info table { border-collapse: collapse; font-size: 11px; margin: 1px auto 0; }
  .fd-info th { font-weight: 400; color: var(--secondary-text-color); padding: 0 4px; }
  .fd-info td, .fd-info th { white-space: nowrap; }
  .fd-info td { padding: 0 4px; text-align: right; font-variant-numeric: tabular-nums; }
  .fd-info td:first-child { text-align: left; color: var(--secondary-text-color); }
  .fd-node.fd-grid { --fd-color: #488fc2; }
  .fd-node.fd-house { --fd-color: var(--primary-color); }
  .fd-node.fd-pv { --fd-color: #ff9800; }
  .fd-node.fd-battery { --fd-color: #4db6ac; }
  .fd-node.fd-excluded { --fd-color: #ce93d8; }
  .fd-node.fd-zone { --fd-color: #e53935; }
  @media (max-width: 600px) { .fd-circle { width: 64px; height: 64px; } .fd-circle ha-icon { --mdc-icon-size: 16px; } .fd-circle b { font-size: 11px; } .fd-node { transform: translate(-50%, -32px); width: 112px; } .fd-info table { font-size: 9px; } .fd-name { font-size: 10px; } }
  .toolbar .version { font-size: 12px; opacity: .7; margin-left: 8px; }
  .toolbar .stage { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; margin-left: 6px; padding: 1px 6px; border-radius: 8px; background: var(--warning-color, #ff9800); color: #000; vertical-align: middle; }
  .toolbar button { display: flex; align-items: center; gap: 6px; font: inherit; font-size: 14px; cursor: pointer;
    color: inherit; background: rgba(255, 255, 255, 0.15); border: 1px solid rgba(255, 255, 255, 0.4);
    border-radius: 18px; padding: 6px 14px; }
  .toolbar button:disabled { opacity: .6; cursor: default; }
  .toolbar button ha-icon { --mdc-icon-size: 18px; }
  @media (max-width: 600px) { .toolbar .adj-open .label, .toolbar .ev-open .label { display: none; } }
  .log-cards { display: none; }
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
  .flow { position: relative; }
  .flow .corner { position: absolute; top: 8px; right: 10px; display: flex; flex-direction: column; align-items: flex-end; gap: 1px; font-size: 11px; color: var(--secondary-text-color); line-height: 1.2; }
  .flow .value { font-size: 22px; font-weight: 500; white-space: nowrap; }
  .flow .label { color: var(--secondary-text-color); font-size: 12px; }
  .flow .value small { font-size: 60%; font-weight: 400; margin-left: 2px; }
  .flows > .flow.price { flex: 2 1 0; min-width: 250px; }
  .flow .value table.prices { font-size: 13px; font-weight: 400; border-collapse: collapse; width: 100%; }
  .flow .value table.prices th, .flow .value table.prices td { padding: 1px 4px; text-align: right; }
  .flow .value table.prices th { font-weight: 500; color: var(--secondary-text-color); }
  .flow .value table.prices tr > th:first-child { text-align: left; padding-left: 0; }
  .pv ha-icon { color: var(--warning-color, #f4b400); }
  .export .value { color: var(--success-color, #43a047); }
  .import .value { color: var(--error-color, #db4437); }
  .batteries { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
  .battery { padding: 12px; border-radius: 10px; background: var(--secondary-background-color); display: grid; gap: 8px; align-content: start; }
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
  .row.cmd.alert span { color: var(--error-color, #db4437); font-weight: 500; }
  .phases { display: grid; gap: 10px; }
  .summary { display: grid; gap: 6px; font-size: 14px; line-height: 1.4; }
  .summary-row { display: grid; grid-template-columns: 90px 1fr; gap: 8px; }
  .summary-row b { font-weight: 500; }
  @media (max-width: 600px) { .summary-row { grid-template-columns: 1fr; gap: 0; } }
  table.log { border-collapse: collapse; width: 100%; font-size: 13px; }
  table.log th, table.log td { padding: 4px 6px; border-bottom: 1px solid var(--divider-color); text-align: left; white-space: nowrap; }
  table.log th { font-weight: 500; color: var(--secondary-text-color); }
  table.log td.num { text-align: right; }
  table.log tr.off-plan td { color: var(--warning-color, #ff9800); }
  table.log tr.incident td { color: var(--error-color, #db4437); }
  .log-nav { display: flex; gap: 4px; flex-wrap: wrap; }
  .log-nav button { background: none; border: 1px solid var(--divider-color); border-radius: 12px; padding: 2px 10px; color: var(--primary-text-color); cursor: pointer; font: inherit; font-size: 12px; }
  .log-nav button.active { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  table.compare { border-collapse: collapse; width: 100%; max-width: 640px; margin-bottom: 8px; }
  table.compare td { padding: 6px 8px; border-bottom: 1px solid var(--divider-color); }
  table.compare td.num, table.compare th.num { text-align: right; white-space: nowrap; }
  table.compare th { text-align: left; font-weight: 500; padding: 6px 8px; color: var(--secondary-text-color); }
  table.compare tr.sel td { font-weight: 500; }
  .daytotals-wrap { overflow-x: auto; margin-top: 6px; }
  table.daytotals { border-collapse: collapse; font-size: 13px; width: 100%; }
  table.daytotals th, table.daytotals td { padding: 2px 4px; text-align: right; white-space: nowrap; }
  table.daytotals th { font-weight: 500; color: var(--secondary-text-color); }
  table.daytotals tr > :first-child { text-align: left; padding-left: 0; color: var(--secondary-text-color); font-weight: 400; }
  table.daytotals .avg { border-left: 1px solid var(--divider-color); font-weight: 500; }
  table.daytotals i { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 4px; }
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
  .card.planner { padding: 10px 16px; font-size: 15px; display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; }
  .card.planner .sub { flex-basis: 100%; font-size: 13px; }
  .alert-text { flex-basis: 100%; color: var(--error-color, #db4437); font-size: 13px; }
  ul.decisions { gap: 0; }
  ul.decisions li { padding: 8px 0; border-bottom: 1px solid var(--divider-color); line-height: 1.45; }
  ul.decisions li:last-child { border-bottom: none; }
  ul.decisions li > div > div + div { margin-top: 2px; }
  ul.decisions .lead { font-weight: 500; }
  .muted { color: var(--secondary-text-color); }
  .adj-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; padding: 8px 0; border-top: 1px solid var(--divider-color); }
  .adj-row .what { flex: 1 1 200px; }
  .adj-row button, .adj-actions button, .card .adj-add { font: inherit; font-size: 14px; cursor: pointer; border-radius: 8px;
    padding: 6px 12px; border: 1px solid var(--divider-color); background: none; color: var(--primary-color); }
  .adj-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.45); display: flex; align-items: center;
    justify-content: center; z-index: 10; padding: 16px; box-sizing: border-box; }
  .adj-dialog { background: var(--card-background-color); color: var(--primary-text-color); border-radius: 12px;
    padding: 20px; width: 100%; max-width: 420px; display: flex; flex-direction: column; gap: 12px; box-sizing: border-box; }
  .adj-dialog label { display: flex; flex-direction: column; gap: 4px; font-size: 14px; color: var(--secondary-text-color); }
  .adj-dialog label.choice { flex-direction: row; align-items: center; gap: 8px; color: var(--primary-text-color); }
  .adj-dialog input[type="text"], .adj-dialog input[type="date"], .adj-dialog input[type="time"], .adj-dialog input[type="number"] {
    font: inherit; padding: 8px; border-radius: 8px; border: 1px solid var(--divider-color);
    background: var(--primary-background-color); color: var(--primary-text-color); }
  .adj-dialog .times { display: flex; gap: 12px; }
  .adj-dialog .times label { flex: 1; }
  .adj-list { max-height: 50vh; overflow-y: auto; }
  .adj-dialog .error { color: var(--error-color, #db4437); font-size: 14px; }
  .adj-actions { display: flex; justify-content: flex-end; gap: 8px; }
  .adj-actions button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  .small { font-size: 0.85em; margin-top: 4px; }
  .charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
  .chart h3 { margin: 0 0 6px; font-size: 14px; font-weight: 500; }
  .chart svg { width: 100%; height: auto; display: block; }
  .chart .grid { stroke: var(--divider-color); stroke-width: 1; }
  .chart .fill-area { fill: var(--secondary-text-color); fill-opacity: .1; stroke: var(--secondary-text-color); stroke-opacity: .25; stroke-width: .8; }
  .chart .axis { fill: var(--secondary-text-color); font-size: 11px; }
  .chart .line { fill: none; stroke-width: 1.4; stroke-linejoin: round; }
  .chart .line.dashed { stroke-dasharray: 4 3; stroke-width: 1.2; }
  .chart .area { stroke: none; fill-opacity: 0.22; }
  .legend .unit { opacity: .7; margin-right: 4px; }
  .legend .group { margin-right: 18px; }
  .legend .group > span { margin-right: 12px; }
  .chart .line.thin { stroke-width: 0.8; stroke-dasharray: 1 3; opacity: 0.8; }
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
  .chart .xscroll { position: relative; overflow-x: auto; overflow-y: hidden; padding-bottom: 4px; }
  .chart svg { touch-action: pan-y; cursor: crosshair; }
  .chart .cursor { stroke: var(--secondary-text-color); stroke-width: 1; }
  .tip { position: absolute; top: 28px; pointer-events: none; z-index: 2; min-width: 120px;
    background: color-mix(in srgb, var(--card-background-color, #1c1c1c) 97%, transparent); color: var(--primary-text-color);
    border: 1px solid var(--divider-color); border-radius: 8px; padding: 5px 8px; font-size: 12px; line-height: 1.35;
    box-shadow: 0 2px 6px rgba(0, 0, 0, .25); }
  .tip .t { font-weight: 500; margin-bottom: 2px; }
  .tip .r { display: flex; justify-content: space-between; gap: 12px; }
  .tip i { display: inline-block; width: 10px; height: 10px; border-radius: 5px; margin-right: 6px; }
  .reach { display: grid; grid-template-columns: max-content 1fr max-content; gap: 8px 12px; align-items: center; margin-top: 12px; }
  .acc { width: 100%; border-collapse: collapse; font-size: 13px; }
  .acc th, .acc td { padding: 6px 4px; text-align: right; border-bottom: 1px solid var(--divider-color); }
  .acc th:first-child, .acc td:first-child { text-align: left; }
  .acc td small { display: block; color: var(--secondary-text-color); }
  .acc-wrap { overflow-x: auto; }
  .reach .row { display: contents; } /* one grid: the labels set the first column's width */
  .reach .bar { height: 12px; }
  .legend { display: flex; gap: 16px; font-size: 13px; color: var(--secondary-text-color); margin-top: 4px; }
  .legend i { display: inline-block; width: 12px; height: 3px; border-radius: 2px; margin-right: 6px; vertical-align: middle; }
  /* Phone: everything fits the width (no sideways page), round icon buttons,
     tables scroll in their own box, the log as compact blocks, readable charts. */
  @media (max-width: 600px) {
    .toolbar { padding: 0 6px; gap: 6px; font-size: 17px; }
    .toolbar .title { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .toolbar .version { display: none; }
    .toolbar .stage { font-size: 9px; padding: 1px 4px; margin-left: 4px; }
    .toolbar button { padding: 6px; border-radius: 50%; flex: none; }
    .toolbar button .label { display: none; }
    .content { padding: 8px; gap: 10px; }
    .content > *, .card { min-width: 0; }
    .card { padding: 12px; }
    .tabs button { padding: 10px 10px; }
    table.compare, table.acc, table.daytotals, table.prices { display: block; overflow-x: auto; max-width: 100%; }
    table.compare td, table.compare th, table.acc td, table.acc th { white-space: nowrap; }
    table.compare tr > :first-child, table.acc tr > :first-child {
      position: sticky; left: 0; z-index: 1; background: var(--card-background-color); }
    .log-wide { display: none; }
    .log-cards { display: block; }
    .log-card { padding: 6px 0; border-bottom: 1px solid var(--divider-color); font-size: 13px; }
    .log-card .l1 { display: flex; justify-content: space-between; gap: 8px; }
    .log-card .l1 > :last-child { white-space: nowrap; }
    .log-card .l2 { color: var(--secondary-text-color); font-size: 12px; margin-top: 2px; }
    .log-card.off-plan .l1 { color: var(--warning-color, #ff9800); }
    .log-card.incident .l1 { color: var(--error-color, #db4437); }
    .log-nav { flex-wrap: wrap; }
    .chart .axis { font-size: 16px; }
    .chart .line { stroke-width: 2.4; }
    .chart .line.thin { stroke-width: 1.4; }
    .chart .line.dashed { stroke-width: 2; stroke-dasharray: 6 4; }
    .chart .grid { stroke-opacity: .6; }
    .chart h3, .chart .head h3 { font-size: 15px; }
    .legend i { width: 16px; height: 4px; }
    .legend { flex-wrap: wrap; gap: 4px 12px; font-size: 12px; }
  }
`;

const FLOW_LEAD = 6 * 3600e3; // the flow chart shows this much history before now
const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// The development stage, shown beside the version (empty from the first stable release).
const STAGE = "alpha";

// The integration's version: the panel is loaded as panel.js?v=<version>.
const VERSION = (() => {
  try {
    // "0.109.0-1795450471": the version, then the file time (cache only).
    return (new URL(import.meta.url).searchParams.get("v") || "").replace(/-\d+$/, "");
  } catch (err) {
    return "";
  }
})();

const FLOW_SCROLL_HOURS = 36; // flow chart: wider than the card past this (hours per card width)

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
    this._flowSpan = 72; // hours in view (follows the chosen range)
    this._flowRange = "all"; // today | tomorrow | all (the whole forecast)
    this._flowEnd = null; // ms; null = follow "now"
    this._dayWeek = null; // index in profile_weeks; null = all history
  }

  async _setMode(mode) {
    if (this._modeBusy || !this._hass || mode === this._history?.value?.mode) return;
    this._actionError = null;
    this._modeBusy = true;
    this._scheduleRender();
    try {
      await this._hass.callService("homebatteryassist", "set_plan_mode", { mode });
      // The integration reloads and plans again with the new mode: wait
      // until it answers again (a slow machine may take longer), at most 60 s.
      await new Promise((resolve) => setTimeout(resolve, 3000));
      for (let i = 0; i < 19; i++) {
        try {
          await this._hass.callWS({ type: "homebatteryassist/status" });
          break;
        } catch (err) {
          await new Promise((resolve) => setTimeout(resolve, 3000));
        }
      }
    } catch (err) {
      this._actionError = err?.message || String(err);
    }
    this._modeBusy = false;
    this._historyAt = 0;
    await this._load();
  }

  async _recalculate() {
    if (!this._hass) return;
    this._actionError = null;
    if (this._busy) {
      // Running: once more when it is done (a change came in meanwhile).
      this._recalcAgain = true;
      return;
    }
    this._busy = true;
    this._scheduleRender();
    try {
      await this._hass.callService("homebatteryassist", "recalculate", {});
    } catch (err) {
      this._actionError = err?.message || String(err);
    }
    this._busy = false;
    this._historyAt = 0;
    await this._load();
    if (this._recalcAgain) {
      this._recalcAgain = false;
      await this._recalculate();
    }
  }

  set hass(hass) {
    const old = this._hass;
    this._hass = hass;
    if (old && this._status && !this._shownChanged(old, hass)) return;
    // Live values are only on the overview and the batteries tab: the other
    // tabs are not rebuilt on every state change (charts stay as they are).
    if (old && this._status && !["overview", "batteries"].includes(this._tab)) return;
    // First data on the first hass only: HA sets hass on every state change,
    // and while the entry is not loaded the status stays empty (else a request
    // per state change). After that the 60 s timer reloads.
    if (!this._loadStarted) {
      this._loadStarted = true;
      this._load();
    }
    this._scheduleRender();
  }

  // Whether a state the panel shows changed (HA sets hass on every state
  // change in the house; re-rendering for each restarts the animations).
  _shownChanged(old, hass) {
    if (!this._shown) {
      const ids = new Set();
      const walk = (v) => {
        if (typeof v === "string") {
          if (/^[a-z_]+\.[a-z0-9_]+$/.test(v)) ids.add(v);
        } else if (Array.isArray(v)) v.forEach(walk);
        else if (v && typeof v === "object") Object.values(v).forEach(walk);
      };
      walk(this._status);
      this._shown = [...ids];
    }
    return this._shown.some((id) => old.states[id] !== hass.states[id]);
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
      this._shown = null;
      this._error = null;
      // A new forecast cycle (its window starts anew): fetch the charts at
      // once, e.g. the first full cycle after a restart.
      const cycle = this._status?.window?.start;
      const newCycle = cycle && this._cycle && cycle !== this._cycle;
      this._cycle = cycle;
      if (newCycle || Date.now() - this._historyAt > 5 * 60000) {
        // A failing history call only costs the charts, not the whole panel.
        this._historyAt = Date.now();
        try {
          this._history = await this._hass.callWS({ type: "homebatteryassist/history", days: 7 });
        } catch (err) {
          console.warn("HomeBatteryAssist: history not available", err);
        }
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

  // A power or current sensor in W (as the integration reads it: kW, MW,
  // mA/A at 230 V; without a unit W).
  _watts(entityId) {
    const state = entityId && this._hass.states[entityId];
    const value = state ? parseFloat(state.state) : NaN;
    if (Number.isNaN(value)) return null;
    const factor = { W: 1, kW: 1000, MW: 1e6, mW: 0.001, A: 230, mA: 0.23 }[state.attributes?.unit_of_measurement || "W"];
    return factor === undefined ? null : value * factor;
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

  // Times in Home Assistant's time zone, as the integration's own texts and
  // day boundaries (the browser may be in another one).
  get _tz() {
    return this._hass?.config?.time_zone || undefined;
  }

  // The local date and time parts of a moment in Home Assistant's zone.
  _zone(ts) {
    const tz = this._tz;
    if (!this._zoneFmt || this._zoneFmtTz !== tz) {
      this._zoneFmtTz = tz;
      this._zoneFmt = new Intl.DateTimeFormat("en-US", {
        timeZone: tz,
        hourCycle: "h23",
        year: "numeric",
        month: "numeric",
        day: "numeric",
        hour: "numeric",
        minute: "numeric",
      });
    }
    const p = Object.fromEntries(this._zoneFmt.formatToParts(new Date(ts)).map((x) => [x.type, x.value]));
    return { y: +p.year, mo: +p.month, d: +p.day, h: +p.hour % 24, mi: +p.minute };
  }

  // The next local midnight after ``ts`` (``days`` later: further).
  _zoneMidnight(ts, days = 1) {
    const z = this._zone(ts);
    let guess = Date.UTC(z.y, z.mo - 1, z.d + days);
    for (let i = 0; i < 2; i++) {
      const g = this._zone(guess);
      const local = Date.UTC(g.y, g.mo - 1, g.d, g.h, g.mi);
      guess -= local - Date.UTC(z.y, z.mo - 1, z.d + days);
    }
    return guess;
  }

  // Ticks every ``step`` local hours between two moments; a local midnight
  // gets the date as label.
  _hourTicks(xMin, xMax, step, lang, inclusive = false) {
    const ticks = [];
    const z = this._zone(xMin);
    let ts = xMin + ((60 - z.mi) % 60) * 60e3 - (new Date(xMin).getSeconds() * 1e3 + new Date(xMin).getMilliseconds());
    for (let guard = 0; guard < 2000 && (inclusive ? ts <= xMax : ts < xMax); guard++, ts += 3600e3) {
      const h = this._zone(ts).h;
      if (h % step !== 0) continue;
      ticks.push([
        ts,
        h === 0
          ? new Date(ts).toLocaleDateString(lang, { timeZone: this._tz, weekday: "short", day: "numeric", month: "numeric" })
          : `${String(h).padStart(2, "0")}:00`,
      ]);
    }
    return ticks;
  }

  _time(iso) {
    if (!iso) return "–";
    const date = new Date(iso);
    const day = (z) => `${z.y}-${z.mo}-${z.d}`;
    const sameDay = day(this._zone(date.getTime())) === day(this._zone(Date.now()));
    const opts = sameDay ? { hour: "2-digit", minute: "2-digit" } : { weekday: "short", hour: "2-digit", minute: "2-digit" };
    return date.toLocaleString(this._hass.locale?.language || this._hass.language, { ...opts, timeZone: this._tz });
  }

  _flow(cls, icon, label, value, sub = "", corner = "") {
    return `<div class="flow ${cls}">${corner ? `<div class="corner">${corner}</div>` : ""}<ha-icon icon="${icon}"></ha-icon>
      <div class="value">${value}</div><div class="label">${esc(label)}${sub ? ` · ${esc(sub)}` : ""}</div></div>`;
  }

  // Energy flow diagram: every measured flow now (W, moving dots) and the
  // energy of today per node (kWh, from the history).
  _flowDiagram(s, t) {
    const days = this._history?.energy_days || [];
    // The day chosen may be gone (fewer days after a refresh): back to live.
    if (this._fdDay != null && !days[this._fdDay]) this._fdDay = null;
    if (this._fdDay != null) return this._flowDay(s, t, days, this._fdDay);
    const e = s.entities;
    const num = (id) => this._num(id);
    const house = num(e.house_consumption);
    const grid = num(e.grid_power);
    if (house === null && grid === null) return "";
    const pv = s.has_pv ? Math.max(num(e.pv_power) || 0, 0) : null;
    const excluded = s.has_excluded ? Math.max(num(e.excluded_power) || 0, 0) : null;
    // Each excluded device on its own (sum of its sensors, e.g. per phase).
    const devices = (s.excluded || []).map((d) => ({
      name: d.name,
      w: d.sensors.reduce((a, id) => a + Math.abs(this._watts(id) || 0), 0),
    }));
    // + charging; only virtual batteries: added up here (no total sensors).
    const { power: battery, soc } = this._batteryTotals(s);
    const zones = (s.zones || []).map((z) => ({ name: z.name, w: Math.abs(this._watts(z.sensor) || 0), wh: s.today?.zones?.[z.id] }));
    // Who supplies whom: solar first to the house, then the excluded devices,
    // the battery and the grid; then the battery; the grid the rest.
    const supply = { pv: pv || 0, battery: Math.max(-(battery || 0), 0), grid: Math.max(grid || 0, 0) };
    const demand = { house: Math.max(house || 0, 0), excluded: excluded || 0, battery: Math.max(battery || 0, 0), grid: Math.max(-(grid || 0), 0) };
    const flows = {};
    for (const from of ["pv", "battery", "grid"]) {
      for (const to of ["house", "excluded", "battery", "grid"]) {
        if (from === to) continue;
        const w = Math.min(supply[from], demand[to]);
        if (w > 1) {
          flows[`${from}-${to}`] = w;
          supply[from] -= w;
          demand[to] -= w;
        }
      }
    }
    // Today (Wh) since local midnight, incl. the interval running now
    // (status, refreshed every minute).
    const today = s.today || {};
    const lang = this._hass.locale?.language || this._hass.language;
    const kwh = (wh) => `${(wh / 1000).toLocaleString(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} kWh`;
    const hasHistory = s.today != null;
    // Layout (viewBox 520 x 360): solar top, grid left, house right,
    // battery bottom, excluded devices bottom right, zones top right.
    const pos = { pv: [260, 55], zone: [450, 55], grid: [70, 205], house: [450, 205], battery: [260, 360], excluded: [450, 360] };
    const J = [260, 205];  // where the lines meet
    const line = (a, b) => {
      const [x1, y1] = pos[a];
      const [x2, y2] = pos[b];
      return x1 === x2 || y1 === y2 ? `M${x1} ${y1} L${x2} ${y2}` : `M${x1} ${y1} Q${J[0]} ${J[1]} ${x2} ${y2}`;
    };
    const paths = Object.fromEntries(
      ["pv-house", "pv-grid", "pv-battery", "pv-excluded", "grid-house", "grid-battery", "grid-excluded",
        "battery-house", "battery-grid", "battery-excluded", "house-zone"].map((k) => [k, line(...k.split("-"))]),
    );
    const colors = { pv: "#ff9800", grid: "#488fc2", battery: "#4db6ac", export: "#8353d1", zone: "#e53935" };
    const exists = (n) =>
      n === "pv" ? pv !== null : n === "battery" ? battery !== null : n === "excluded" ? excluded !== null : n === "zone" ? zones.length > 0 : true;
    if (zones.length) flows["house-zone"] = zones.reduce((a, z) => a + z.w, 0);
    const now = Date.now() / 1000;
    let svg = "";
    for (const [key, d] of Object.entries(paths)) {
      const [from, to] = key.split("-");
      if (!exists(from) || !exists(to)) continue;
      const color = key === "house-zone" ? colors.zone : to === "grid" ? colors.export : colors[from];
      const w = flows[key] || 0;
      svg += `<path d="${d}" class="fd-line${w > 1 ? " on" : ""}" stroke="${w > 1 ? color : "var(--divider-color)"}"/>`;
      if (w > 1) {
        // Faster with more power; the start follows the clock, so the dots
        // do not jump back on every redraw.
        const dur = Math.max(1.2, 6 - Math.log10(w) * 1.4);
        for (const shift of w > 1500 ? [0, 0.5] : [0]) {
          const begin = -((now / dur + shift) % 1) * dur;
          // Hidden until the animation runs (no flash at the corner on a redraw).
          svg += `<circle r="4.5" fill="${color}" visibility="hidden"><set attributeName="visibility" to="visible" begin="0s" fill="freeze"/><animateMotion dur="${dur.toFixed(2)}s" begin="${begin.toFixed(2)}s" repeatCount="indefinite" path="${d}"/></circle>`;
        }
      }
    }
    const expected = s.today_expected || {};
    const num1 = (wh) => (wh == null ? "–" : (wh / 1000).toLocaleString(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
    // rows: [label, today Wh, expected Wh]
    const node = (key, cls, icon, label, value, rows = [], extra = "") => {
      const [x, y] = pos[key];
      // No "expected" column for rows without one (excluded devices are
      // not forecast).
      const withExpected = rows.some((r) => r.length > 2);
      const table = rows.length
        ? `<table><tr><th>kWh</th><th>${esc(t.fdToday)}</th>${withExpected ? `<th>${esc(t.fdExpected)}</th>` : ""}</tr>${rows
            .map(([name, a, b]) => `<tr><td>${esc(name)}</td><td>${hasHistory ? esc(num1(a)) : "–"}</td>${withExpected ? `<td>${esc(num1(b))}</td>` : ""}</tr>`)
            .join("")}</table>`
        : "";
      return `<div class="fd-node ${cls}" style="left:${(x / 520) * 100}%;top:${(y / 460) * 100}%">
        <div class="fd-circle"><ha-icon icon="${icon}"></ha-icon><b>${esc(value)}</b>${extra ? `<small>${esc(extra)}</small>` : ""}</div>
        <div class="fd-info"><div class="fd-name">${esc(label)}</div>${table}</div></div>`;
    };
    const zoneW = zones.reduce((a, z) => a + z.w, 0);
    const zoneWh = zones.some((z) => z.wh != null) ? zones.reduce((a, z) => a + (z.wh || 0), 0) : null;
    // The grid is on the left, the house on the right: import flows → (to
    // the house), export ← (to the grid).
    const nodes = [
      node("grid", "fd-grid", "mdi:transmission-tower", t.grid,
        grid === null ? "–" : `${grid >= 0 ? "→ " : "← "}${this._power(Math.abs(grid))}`,
        [[t.fdImport, today.imported, expected.imported], [t.fdExport, today.exported, expected.exported]]),
      node("house", "fd-house", "mdi:home", t.house, this._power(house), [["", today.house, expected.house]]),
      pv !== null ? node("pv", "fd-pv", "mdi:solar-power", t.pv, this._power(pv), [["", today.pv, expected.pv]]) : "",
      battery !== null
        ? node("battery", "fd-battery", "mdi:home-battery", t.batteries,
            `${battery > 1 ? "↓ " : battery < -1 ? "↑ " : ""}${this._power(Math.abs(battery || 0))}`,
            [[t.fdCharge, today.charged, expected.charged], [t.fdDischarge, today.discharged, expected.discharged]],
            soc !== null ? `${Math.round(soc)}%` : "")
        : "",
      excluded !== null
        ? node("excluded", "fd-excluded", "mdi:ev-station", devices.length === 1 ? devices[0].name : t.fdExcluded, this._power(excluded),
            [["", today.excluded]],
            devices.length > 1 ? devices.map((d) => `${d.name}: ${this._power(d.w)}`).join("\n") : "")
        : "",
      zones.length
        ? node("zone", "fd-zone", "mdi:hvac", zones.map((z) => z.name).join(", "), this._power(zoneW),
            zoneWh != null ? [["", zoneWh, expected.zones]] : [], t.fdPartOfHouse)
        : "",
    ];
    // Totals of today: one chip per part, with its icon and colour.
    const chip = (icon, color, name, value, sub) =>
      `<span class="fd-chip" style="--fd-color:${color}"><ha-icon icon="${icon}"></ha-icon><span><b>${esc(name)}</b> ${esc(value)}${
        sub ? `<small>${esc(sub)}</small>` : ""
      }</span></span>`;
    const totals = hasHistory
      ? [
          chip("mdi:home", "var(--primary-color)", t.house, kwh(today.house), expected.house != null ? `${t.fdExpected} ${kwh(expected.house)}` : ""),
          pv !== null ? chip("mdi:solar-power", "#ff9800", t.pv, kwh(today.pv), expected.pv != null ? `${t.fdExpected} ${kwh(expected.pv)}` : "") : "",
          chip("mdi:transmission-tower", "#488fc2", t.grid, `→ ${kwh(today.imported)} ${t.fdImport.replace(/^[←→]\s*/, "")}`, `← ${kwh(today.exported)} ${t.fdExport.replace(/^[←→]\s*/, "")}`),
          battery !== null
            ? chip("mdi:home-battery", "#4db6ac", t.batteries, `↓ ${kwh(today.charged)} ${t.fdCharge.replace(/^[↑↓]\s*/, "")}`, `↑ ${kwh(today.discharged)} ${t.fdDischarge.replace(/^[↑↓]\s*/, "")}`)
            : "",
          zones.length && today.zones
            ? chip("mdi:hvac", "#e53935", zones.map((z) => z.name).join(", "), kwh(Object.values(today.zones).reduce((a, v) => a + v, 0)), t.fdPartOfHouse)
            : "",
          excluded !== null ? chip("mdi:ev-station", "#ce93d8", (s.excluded_names || []).join(", ") || t.fdExcluded, kwh(today.excluded), "") : "",
        ].filter(Boolean).join("")
      : "";
    return `<div class="card"><div class="head"><h2>${esc(t.fdTitle)}</h2>${this._fdNav(t, days)}</div><div class="fd-wrap"><div class="fd"><svg viewBox="0 0 520 460" preserveAspectRatio="xMidYMid meet">${svg}</svg>${nodes.join("")}</div>
      ${totals ? `<div class="fd-totals"><div class="muted small">${esc(t.fdTodayTotal)}</div><div class="fd-chips">${totals}</div></div>` : ""}</div></div>`;
  }

  // The batteries together: the total sensors, else (only virtual
  // batteries, which have no totals) added up from each battery.
  _batteryTotals(s) {
    const e = s.entities;
    if (!s.batteries.length) return { power: null, soc: null, summed: false };
    const power = this._num(e.batteries_power);
    const soc = this._num(e.batteries_soc);
    if (power !== null || soc !== null) return { power, soc, summed: false };
    let cap = 0, stored = 0, sum = 0, known = false;
    for (const b of s.batteries) {
      const p = this._num(b.entities.battery_power);
      const c = this._num(b.entities.battery_soc);
      if (p !== null) { sum += p; known = true; }
      if (c !== null) { stored += (c * b.capacity_kwh) / 100; cap += b.capacity_kwh; }
    }
    return { power: known ? sum : null, soc: cap ? (stored / cap) * 100 : null, summed: true };
  }

  // Day navigation of the flow diagram: today (live) or an earlier day.
  _fdNav(t, days) {
    if (!days.length) return "";
    const i = this._fdDay;
    const lang = this._hass.locale?.language || this._hass.language;
    const label =
      i == null
        ? t.fdLive
        : new Date(`${days[i].date}T12:00:00`).toLocaleDateString(lang, { timeZone: this._tz, weekday: "short", day: "numeric", month: "short" });
    const older = i == null ? 0 : i + 1;
    const newer = i == null ? null : i - 1;
    return `<div class="nav">
      <button data-fdday="${older}" title="${esc(t.fdOlder)}" ${older >= days.length ? "disabled" : ""}>◀</button>
      <button data-fdday="live" class="${i == null ? "active" : ""}">${esc(label)}</button>
      <button data-fdday="${newer == null || newer < 0 ? "live" : newer}" title="${esc(t.fdNewer)}" ${i == null ? "disabled" : ""}>▶</button>
    </div>`;
  }

  // The flow diagram of an earlier day: energy per node and per flow (kWh),
  // lines as thick as the energy that went along them.
  _flowDay(s, t, days, index) {
    const d = days[index];
    const lang = this._hass.locale?.language || this._hass.language;
    const num1 = (wh) => (wh == null ? "–" : (wh / 1000).toLocaleString(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
    const kwh = (wh) => `${num1(wh)} kWh`;
    const zones = s.zones || [];
    const zoneWh = zones.reduce((a, z) => a + (d.zones?.[z.id] || 0), 0);
    const pos = { pv: [260, 55], zone: [450, 55], grid: [70, 205], house: [450, 205], battery: [260, 360], excluded: [450, 360] };
    const J = [260, 205];
    const colors = { pv: "#ff9800", grid: "#488fc2", battery: "#4db6ac", export: "#8353d1", zone: "#e53935" };
    const exists = (n) =>
      n === "pv" ? s.has_pv : n === "battery" ? s.batteries.length > 0 : n === "excluded" ? s.has_excluded : n === "zone" ? zones.length > 0 : true;
    const flows = { ...(d.flows || {}) };
    if (zones.length) flows["house-zone"] = zoneWh;
    const max = Math.max(...Object.values(flows), 1);
    let svg = "";
    for (const key of ["pv-house", "pv-grid", "pv-battery", "pv-excluded", "grid-house", "grid-battery", "grid-excluded",
      "battery-house", "battery-grid", "battery-excluded", "house-zone"]) {
      const [from, to] = key.split("-");
      if (!exists(from) || !exists(to)) continue;
      const [x1, y1] = pos[from];
      const [x2, y2] = pos[to];
      const straight = x1 === x2 || y1 === y2;
      const d0 = straight ? `M${x1} ${y1} L${x2} ${y2}` : `M${x1} ${y1} Q${J[0]} ${J[1]} ${x2} ${y2}`;
      const wh = flows[key] || 0;
      const on = wh >= 50;
      const color = key === "house-zone" ? colors.zone : to === "grid" ? colors.export : colors[from];
      svg += `<path d="${d0}" class="fd-line${on ? " on" : ""}" stroke="${on ? color : "var(--divider-color)"}" style="stroke-width:${on ? 2 + (6 * wh) / max : 2}"/>`;
      if (on) {
        // The energy on the line, at its middle.
        // (straight lines at a third, so they do not meet in the middle)
        const f = 0.35;
        const mx = straight ? x1 + (x2 - x1) * f : 0.25 * x1 + 0.5 * J[0] + 0.25 * x2;
        const my = straight ? y1 + (y2 - y1) * f : 0.25 * y1 + 0.5 * J[1] + 0.25 * y2;
        svg += `<text class="fd-flow" x="${(mx + (x1 === x2 ? 14 : 0)).toFixed(0)}" y="${(my - (x1 === x2 ? 0 : 6)).toFixed(0)}" fill="${color}">${esc(num1(wh))}</text>`;
      }
    }
    const node = (key, cls, icon, label, value, rows = [], extra = "") => {
      const [x, y] = pos[key];
      const table = rows.length
        ? `<table><tr><th>kWh</th><th>${esc(t.fdTotal)}</th></tr>${rows
            .map(([name, a]) => `<tr><td>${esc(name)}</td><td>${esc(num1(a))}</td></tr>`)
            .join("")}</table>`
        : "";
      return `<div class="fd-node ${cls}" style="left:${(x / 520) * 100}%;top:${(y / 460) * 100}%">
        <div class="fd-circle"><ha-icon icon="${icon}"></ha-icon><b>${esc(value)}</b>${extra ? `<small>${esc(extra)}</small>` : ""}</div>
        <div class="fd-info"><div class="fd-name">${esc(label)}</div>${table}</div></div>`;
    };
    const nodes = [
      node("grid", "fd-grid", "mdi:transmission-tower", t.grid, `→ ${kwh(d.imported)}`,
        [[t.fdImport, d.imported], [t.fdExport, d.exported]]),
      node("house", "fd-house", "mdi:home", t.house, kwh(d.house)),
      s.has_pv ? node("pv", "fd-pv", "mdi:solar-power", t.pv, kwh(d.pv)) : "",
      s.batteries.length
        ? node("battery", "fd-battery", "mdi:home-battery", t.batteries, `↓ ${num1(d.charged)} ↑ ${num1(d.discharged)}`,
            [[t.fdCharge, d.charged], [t.fdDischarge, d.discharged]])
        : "",
      s.has_excluded
        ? node("excluded", "fd-excluded", "mdi:ev-station", (s.excluded_names || []).length === 1 ? s.excluded_names[0] : t.fdExcluded, kwh(d.excluded))
        : "",
      zones.length ? node("zone", "fd-zone", "mdi:hvac", zones.map((z) => z.name).join(", "), kwh(zoneWh), [], t.fdPartOfHouse) : "",
    ];
    return `<div class="card"><div class="head"><h2>${esc(t.fdTitle)}</h2>${this._fdNav(t, days)}</div>
      <div class="fd"><svg viewBox="0 0 520 460" preserveAspectRatio="xMidYMid meet">${svg}</svg>${nodes.join("")}</div>
      <div class="muted small fd-totals">${esc(t.fdDayNote)}</div></div>`;
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
      // Now and from the next price change: market, import and export price.
      const hhmm = (iso) => new Date(iso).toLocaleTimeString(lang, { timeZone: this._tz, hour: "2-digit", minute: "2-digit" });
      const row = (label, market, imp, est, exp) =>
        `<tr><th>${esc(label)}</th><td>${fmt(market)}</td><td>${fmt(imp, est)}</td><td>${fmt(exp)}</td></tr>`;
      const rows = [row(t.priceNowAt.replace("{time}", hhmm(p.start || new Date().toISOString())), p.market_now, p.now, p.now_estimated, p.export_now)];
      if (p.next != null) rows.push(row(t.priceFromAt.replace("{time}", hhmm(p.next_start)), p.market_next, p.next, p.next_estimated, p.export_next));
      const table = `<table class="prices"><tr><th></th>${t.priceCols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>${rows.join("")}</table>`;
      const cls = p.next == null ? "price" : p.next > p.now ? "price up" : "price down";
      parts.push(this._flow(cls, (this._hass?.config?.currency || "EUR") === "EUR" ? "mdi:currency-eur" : "mdi:cash", t.priceNow, table));
    }
    if (s.has_pv || s.has_pv_forecast) {
      const expected = s.pv_forecast_now_w == null ? "" : `${t.expected} ${this._power(s.pv_forecast_now_w)}`;
      const value = s.has_pv ? this._power(this._num(e.pv_power)) : "–";
      const sub = [s.has_pv ? "" : t.notMeasured, expected].filter(Boolean).join(" · ");
      parts.push(this._flow("pv", "mdi:solar-power", t.pv, value, sub));
    }
    if (s.batteries.length) {
      const { power, soc, summed } = this._batteryTotals(s);
      let label = t.batteries;
      if (summed && s.batteries.every((b) => b.virtual)) label = `${t.batteries} (${t.virtual})`;
      const mode = power === null ? "" : power > 20 ? t.charging : power < -20 ? t.discharging : t.idle;
      // The real batteries' temperatures, small in the corner (at most 4).
      const temps = s.batteries
        .filter((b) => !b.virtual && b.details && b.details.temperature_c != null)
        .slice(0, 4)
        .map((b) => `<span title="${esc(b.name)}">${Number(b.details.temperature_c).toFixed(1)} °C</span>`)
        .join("");
      parts.push(
        this._flow("battery", "mdi:home-battery", label, this._power(power === null ? null : Math.abs(power)),
          [mode, soc === null ? "" : `${Math.round(soc)}%`].filter(Boolean).join(" · "), temps),
      );
    }
    if (s.has_excluded) parts.push(this._flow("excluded", "mdi:ev-station", t.excluded, this._power(this._num(e.excluded_power))));
    return `<div class="card"><h2>${esc(t.flows)}</h2><div class="flows">${parts.join("")}</div></div>`;
  }

  // On a twin: its real battery now and the difference in value today.
  _twinRows(s, b, t) {
    const real = b.twin_of && s.batteries.find((x) => x.id === b.twin_of);
    if (!real) return "";
    const soc = this._num(real.entities.battery_soc);
    const p = this._num(real.entities.battery_power);
    const what = p === null ? "–" : Math.abs(p) < 1 ? t.idle : `${p > 0 ? t.charging : t.discharging} ${this._power(Math.abs(p))}`;
    const diff = this._num(b.entities.twin_difference_today);
    const money = diff === null ? "–" : `${diff >= 0 ? "+" : "−"}${Math.abs(diff).toFixed(2)} ${this._hass.config?.currency || ""}`.trim();
    return `<div class="row"><span>${esc(t.realBattery)} (${esc(real.name)})</span><b>${soc === null ? "–" : `${Math.round(soc)}%`} · ${esc(what.toLowerCase())}</b></div>
      <div class="row"><span>${esc(t.twinDiff)}</span><b>${esc(money)}</b></div>`;
  }

  _twinNote(s, b, t) {
    // A twin names the real battery it replaces; that one runs outside the plan.
    if (b.twin_of) {
      const real = s.batteries.find((x) => x.id === b.twin_of);
      return ` <small class="muted">· ${esc(t.twinOf.replace("{name}", real ? real.name : "?"))}</small>`;
    }
    return b.twinned ? ` <small class="muted">· ${esc(t.ownControl)}</small>` : "";
  }

  _markVirtual(b, t) {
    // "(virtual)" after a virtual battery's name, unless the name says so.
    return b.virtual && !String(b.name || "").toLowerCase().includes(String(t.virtual).toLowerCase());
  }

  _compare(s, t) {
    // Every mode compared with no battery, and arbitrage compared with NOM.
    const value = this._history?.value;
    if (!value || !s.batteries.length || !value.by_mode) return "";
    const lang = this._hass.locale?.language || this._hass.language;
    const money = (v) =>
      v == null ? "–" : new Intl.NumberFormat(lang, { style: "currency", currency: value.currency || "EUR" }).format(v);
    const signed = (v) => (v == null ? "–" : `${v > 0 ? "+" : ""}${money(v)}`);
    // Own planner modules by their own name (not their key).
    const name = (m) => t.modeNames[m] || this._history?.planner_names?.[m] || m;
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
      ? new Date(value.until).toLocaleString(lang, { timeZone: this._tz, weekday: "short", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" })
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
    // Only the groups that exist (real and/or virtual batteries).
    const followGroups = ["virtual", "real"].filter((g) => s.batteries.some((b) => !b.twinned && !!b.virtual === (g === "virtual")));
    const rows = days.map((d) => {
      const day = new Date(`${d.day}T12:00:00`).toLocaleDateString(lang, { timeZone: this._tz, weekday: "short", day: "numeric", month: "numeric" });
      const diff = d.realized - d.planned;
      const groups = followGroups.map((g) => `<td class="num">${d[`followed_${g}`] == null ? "–" : `${Math.round(d[`followed_${g}`])}%`}</td>`).join("");
      return `<tr><td>${esc(day)}</td><td class="num">${esc(money(d.planned))}</td><td class="num">${esc(money(d.realized))}</td>
        <td class="num"><b>${esc(signed(diff))}</b></td><td class="num">${esc(this._power(d.power_deviation_w))}</td>${groups}</tr>`;
    });
    const groupHead = followGroups.map((g) => `<th class="num">${esc(g === "real" ? t.checkReal : t.checkVirtual)}</th>`).join("");
    const head = `<tr><th>${esc(t.checkDay)}</th><th class="num">${esc(t.checkPlanned)}</th><th class="num">${esc(t.checkRealized)}</th><th class="num">${esc(t.checkDiff)}</th><th class="num">${esc(t.checkDev)}</th>${groupHead}</tr>`;
    const body = rows.length ? `<table class="compare">${head}${rows.join("")}</table>` : `<div class="muted">${esc(t.checkEmpty)}</div>`;
    return `<div class="card"><h2>${esc(t.checkTitle)}</h2>${body}<div class="muted">${esc(t.checkNote)}</div></div>`;
  }

  _battery(b, t, s) {
    const e = b.entities;
    const soc = this._num(e.battery_soc);
    const power = this._num(e.battery_power);
    const status = this._str(e.battery_status);
    const target = this._str(e.battery_time_to_target);
    const fill = soc === null ? 0 : soc;
    const cls = soc !== null && soc <= b.min_soc ? "alert" : soc !== null && soc < b.min_soc + 10 ? "warn" : "";
    return `<div class="battery">
      <div class="head"><span class="name">${esc(b.name)}${this._markVirtual(b, t) ? ` <small class="muted">(${esc(t.virtual)})</small>` : ""}${this._twinNote(s, b, t)}</span>
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
      ${this._command(b, t)}
      ${this._twinRows(s, b, t)}
      ${Object.keys(t.detail)
        .filter((k) => b.details && b.details[k] !== undefined)
        .map((k) => [k, b.details[k]])
        .map(([k, v]) => {
          const [label, unit, digits] = t.detail[k];
          const lang = this._hass.locale?.language || this._hass.language;
          const text = Number(v).toLocaleString(lang, { maximumFractionDigits: digits, minimumFractionDigits: digits });
          return `<div class="row"><span>${esc(label)}</span><b>${esc(text)}${unit ? ` ${unit}` : ""}</b></div>`;
        })
        .join("")}
    </div>`;
  }

  // The command the battery has now (from its controlling integration) and
  // whether it follows it.
  _command(b, t) {
    const c = b.command;
    if (!c || c.command_w === null || c.command_w === undefined) return "";
    const w = this._power(Math.abs(c.command_w));
    const what = c.command_w > 0 ? t.cmdCharge.replace("{w}", w) : c.command_w < 0 ? t.cmdDischarge.replace("{w}", w) : t.cmdStop;
    let line = `<div class="row" title="${esc(t.cmdInfo)}"><span>${esc(t.cmdLabel)}</span><b>${esc(what)}</b></div>`;
    if (c.not_following && c.since) {
      const when = this._time(c.since);
      const text = c.problem
        ? t.cmdProblem.replace("{t}", when)
        : t.cmdExplained.replace("{t}", when).replace("{r}", t.cmdReasons[c.reason] || c.reason || "");
      line += `<div class="row cmd ${c.problem ? "alert" : "muted"}"><span>${esc(text)}</span></div>`;
    }
    return line;
  }

  _batteries(s, t) {
    const body = s.batteries.length
      ? `<div class="batteries">${s.batteries.filter((b) => !b.twinned).map((b) => this._battery(b, t, s)).join("")}</div>`
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
      // A real battery with a twin is not shown: the twin acts in its place.
      const here = s.batteries.filter((b) => share(b) > 0 && !b.twinned);
      const twinned = s.batteries.filter((b) => share(b) > 0 && b.twinned);
      let virtualW = 0;
      let twinnedW = 0; // real batteries with a twin: the twin replaces them
      const who = here.map((b) => {
        const p = this._num(b.entities.battery_power);
        if (b.virtual && p !== null) virtualW += p * share(b);
        const what = p === null ? "–" : Math.abs(p) < 1 ? t.idle : `${p > 0 ? t.charging : t.discharging} ${this._power(Math.abs(p * share(b)))}`;
        return `<span class="${b.virtual ? "virtual" : ""}">${esc(b.name)}${share(b) < 1 ? " (⅓)" : ""}: ${esc(what.toLowerCase())}</span>`;
      });
      for (const b of twinned) {
        const p = this._num(b.entities.battery_power);
        if (p !== null) twinnedW += p * share(b);
      }
      let withVirtual = "";
      if ((virtualW || twinnedW) && power !== null) {
        const amps = Math.abs(power - twinnedW + virtualW) / 230;
        const wcls = amps >= s.phase_limit_a ? "alert" : amps >= 0.75 * s.max_current ? "warn" : "";
        const label = s.batteries.some((b) => b.twinned) ? t.withTwin : t.withVirtual;
        withVirtual = `<span class="${wcls}">${esc(label)}: <b>${amps.toFixed(1)} A</b></span>`;
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
      ${row(t.reachPv, r.pv_end, r.has_pv_forecast)}
      ${r.has_weather ? row(t.reachWeather, r.weather_end, true) : ""}</div>`;
    return `<div class="card"><h2>${esc(t.planning)}</h2><div>${esc(text)}</div>
      <div class="muted">${esc(t.limit[w.limited_by] || w.limited_by)}</div>${reach}</div>`;
  }

  _niceMax(value) {
    if (!value || value <= 0) return 100;
    const step = 10 ** Math.floor(Math.log10(value));
    for (const m of [1, 2, 2.5, 5, 10]) if (value <= m * step) return m * step;
    return 10 * step;
  }

  _chart(id, series, xMin, xMax, ticks, gapLimit, markers = [], xFmt = (v) => this._time(new Date(v).toISOString()), yFmt = null, bands = [], fill = null) {
    // Full-width charts get a wider canvas so they are as high as the others.
    // The full-width flow chart gets a wider and higher canvas.
    const wide = id === "forecast" || id === "soc" || id === "temperature" || id === "review";
    const rightSeries = series.filter((s) => s.axis === "right");
    const hasLeft = series.some((s) => s.axis !== "right");
    // The flow chart over more than FLOW_SCROLL_HOURS: wider than the card (a
    // horizontal scrollbar) at that scale, so it stays readable.
    const hours = (xMax - xMin) / 3600e3;
    const scroll = id === "forecast" && hours > FLOW_SCROLL_HOURS;
    // On a phone (narrow screen) a narrower, higher canvas: scaled down to
    // the screen, the text stays readable.
    const phone = !scroll && window.matchMedia?.("(max-width: 600px)").matches;
    const W = scroll ? Math.round((1232 * hours) / FLOW_SCROLL_HOURS) : phone ? 520 : wide ? 1232 : 600,
      H = id === "forecast" ? 300 : phone ? 260 : 190, L = 58, R = rightSeries.length ? 58 : 8, T = 8, B = 24;
    const all = series.filter((s) => s.axis !== "right").flatMap((s) => s.points.map((p) => p[1])).filter((v) => v != null);
    const yMax = this._niceMax(Math.max(...all, 0));
    const low = Math.min(...all, 0);
    const yMin = low < 0 ? -this._niceMax(-low) : 0;
    const x = (v) => L + ((v - xMin) / (xMax - xMin || 1)) * (W - L - R);
    const y = (v) => T + (1 - (v - yMin) / (yMax - yMin)) * (H - T - B);
    // Right axis (e.g. prices): its own scale on the same grid lines.
    let right = null;
    if (rightSeries.length) {
      const values = rightSeries.flatMap((s) => s.points.map((p) => p[1])).filter((v) => v != null);
      if (values.length) {
        const step = 0.05;
        const rMin = Math.min(0, Math.floor(Math.min(...values) / step) * step);
        const rMax = Math.max(Math.ceil(Math.max(...values) / step) * step, rMin + step);
        right = { min: rMin, max: rMax, fmt: rightSeries[0].axisFmt || rightSeries[0].fmt };
      }
    }
    const yr = (v) => T + (1 - (v - right.min) / (right.max - right.min)) * (H - T - B);
    const yOf = (s) => (s.axis === "right" && right ? yr : y);
    let svg = `<clipPath id="clip-${id}"><rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}"/></clipPath>`;
    // Background bands (e.g. charging / discharging periods), behind everything.
    for (const [from, to, color] of bands) {
      const x1 = Math.max(x(from), L);
      const x2 = Math.min(x(to), W - R);
      if (x2 > x1) svg += `<rect class="band" x="${x1.toFixed(1)}" y="${T}" width="${(x2 - x1).toFixed(1)}" height="${H - T - B}" fill="${color}"/>`;
    }
    // A filled area over the whole height (0-100 %, e.g. the batteries'
    // total state of charge), on the background.
    if (fill && fill.points.length > 1) {
      const fy = (pct) => T + (1 - Math.max(0, Math.min(100, pct)) / 100) * (H - T - B);
      const pts = fill.points.map(([ts, pct]) => `${x(ts).toFixed(1)},${fy(pct).toFixed(1)}`);
      const first = x(fill.points[0][0]).toFixed(1);
      const last = x(fill.points[fill.points.length - 1][0]).toFixed(1);
      svg += `<path class="fill-area" clip-path="url(#clip-${id})" d="M${first},${H - B} L${pts.join(" L")} L${last},${H - B} Z"/>`;
    }
    // Axis labels in the colour of their series (when a chart asks for it).
    const leftColor = series.find((s) => s.axis !== "right" && s.axisColor)?.axisColor;
    const rightColor = series.find((s) => s.axis === "right" && s.axisColor)?.axisColor;
    const steps = 4;
    for (let i = 0; i <= steps; i++) {
      const v = yMin + ((yMax - yMin) / steps) * i;
      svg += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`;
      if (hasLeft) svg += `<text class="axis" x="${L - 6}" y="${y(v) + 4}" text-anchor="end"${leftColor ? ` style="fill:${leftColor}"` : ""}>${esc(yFmt ? yFmt(v) : this._axisPower(v))}</text>`;
      if (right) {
        const rv = right.min + ((right.max - right.min) / steps) * i;
        svg += `<text class="axis" x="${W - R + 6}" y="${y(v) + 4}" text-anchor="start"${rightColor ? ` style="fill:${rightColor}"` : ""}>${esc(right.fmt ? right.fmt(rv) : rv.toFixed(2))}</text>`;
      }
    }
    if (yMin < 0) svg += `<line class="zero" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}"/>`;
    // On a phone at most 5 time labels (they would overlap at the larger text).
    const shown = phone && ticks.length > 5 ? ticks.filter((_, i) => i % Math.ceil(ticks.length / 5) === 0) : ticks;
    for (const [v, label] of shown) {
      svg += `<text class="axis" x="${x(v)}" y="${H - 6}" text-anchor="middle">${esc(label)}</text>`;
    }
    // Rectangles of a series ([from, to, value 1, value 2, colour]), e.g. the
    // difference between measured and forecast, behind every line.
    for (const s of series.filter((s) => s.rects)) {
      const sy = yOf(s);
      for (const [a, b, v1, v2, color] of s.rects) {
        const x1 = Math.max(x(a), L);
        const x2 = Math.min(x(b), W - R);
        const y1 = Math.min(sy(v1), sy(v2));
        const h = Math.abs(sy(v1) - sy(v2));
        if (x2 > x1 && h > 0.5) svg += `<rect x="${x1.toFixed(1)}" y="${y1.toFixed(1)}" width="${(x2 - x1).toFixed(1)}" height="${h.toFixed(1)}" fill="${color}" fill-opacity="0.28" clip-path="url(#clip-${id})"/>`;
      }
    }
    // Filled areas (e.g. a power under temperature lines): down to the zero
    // line, per unbroken run of points, behind every line.
    for (const s of series.filter((s) => s.area)) {
      const sy = yOf(s);
      const base = (s.axis === "right" && right ? yr(Math.max(right.min, 0)) : y(Math.max(yMin, 0))).toFixed(1);
      let run = [];
      const flush = () => {
        if (run.length > 1) svg += `<path class="area" d="M${run[0][0]},${base} L${run.map((q) => q.join(",")).join(" L")} L${run[run.length - 1][0]},${base} Z" fill="${s.color}" clip-path="url(#clip-${id})"/>`;
        run = [];
      };
      let prev = null;
      for (const [px, py] of s.points) {
        if (py == null || (prev !== null && gapLimit && px - prev > gapLimit)) flush();
        if (py != null) run.push([x(px).toFixed(1), sy(py).toFixed(1)]);
        prev = py == null ? null : px;
      }
      flush();
    }
    for (const s of series) {
      let d = "";
      let prev = null;
      const sy = yOf(s);
      for (const [px, py] of s.points) {
        if (py == null) { prev = null; continue; }
        const jump = prev === null || (gapLimit && px - prev > gapLimit);
        d += `${jump ? "M" : "L"}${x(px).toFixed(1)},${sy(py).toFixed(1)}`;
        prev = px;
      }
      svg += `<path class="line${s.thin ? " thin" : s.dashed ? " dashed" : ""}" d="${d}" stroke="${s.color}" clip-path="url(#clip-${id})"/>`;
    }
    for (const [v, label] of markers) {
      svg += `<line class="now" x1="${x(v)}" x2="${x(v)}" y1="${T}" y2="${H - B}"/>`;
      svg += `<text class="axis" x="${x(v) + 4}" y="${T + 10}">${esc(label)}</text>`;
    }
    svg += `<g class="hover" style="display:none"><line class="cursor" y1="${T}" y2="${H - B}"/>
      ${series.map((s, i) => `<circle r="${phone ? 6 : 3.5}" data-i="${i}" style="fill:${s.color}"/>`).join("")}</g>`;
    this._charts[id] = { series, xMin, xMax, yMin, yMax, W, H, L, R, T, B, gapLimit, xFmt, yFmt, right, fill: !!(fill && fill.points.length > 1) };
    const chart = `<svg data-chart="${id}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet"${
      scroll ? ` style="width:${W}px;max-width:none"` : ""
    }>${svg}</svg>`;
    // The tooltip stays outside the scrolling box (never clipped or squeezed).
    return `${scroll ? `<div class="xscroll" data-scroll="${id}">${chart}</div>` : chart}
      <div class="tip" data-tip="${id}" hidden></div>`;
  }

  _money(value, h) {
    const unit = h.price_unit?.split("/")[0] || "";
    return value == null ? "–" : `${value.toFixed(2)} ${unit}`.trim();
  }

  _planText(h, t) {
    const money = (v) => (v == null ? "–" : `${v.toFixed(2)} ${h.price_unit?.split("/")[0] || ""}`.trim());
    const plan = h.plans?.[h.plan_mode];
    const name = (mode) => t.planModes[mode] || h.planner_names?.[mode] || mode;
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
      .map(([h, label]) => `<button data-span="${h}" class="${h === this._flowRange ? "active" : ""}">${esc(label)}</button>`)
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
    if (this._review) return this._reviewNav(t);
    return `<div class="nav">${nav}<span style="width:8px"></span>${spans}<span style="width:8px"></span><button data-review="open" title="${esc(t.reviewOpenTitle)}">⟲ ${esc(t.reviewOpen)}</button></div>`;
  }

  // Looking back at an earlier day (``homebatteryassist/day_review``).
  _reviewNav(t) {
    const r = this._review;
    const lang = this._hass?.language || "en";
    const day = new Date(`${r.day}T12:00:00`);
    const label = day.toLocaleDateString(lang, { weekday: "short", day: "numeric", month: "short" });
    const first = r.data?.first_day;
    const today = this._localDay(0);
    const lead = ["ahead", "late"]
      .map((k) => `<button data-lead="${k}" class="${r.lead === k ? "active" : ""}" title="${esc(k === "ahead" ? t.leadAheadTitle : t.leadLateTitle)}">${esc(k === "ahead" ? t.leadAhead : t.leadLate)}</button>`)
      .join("");
    return `<div class="nav">
      <button data-review="older" title="${esc(t.reviewOlder)}" ${first && r.day <= first ? "disabled" : ""}>◀</button>
      <button class="active" disabled>${esc(label)}</button>
      <button data-review="newer" title="${esc(t.reviewNewer)}" ${r.day >= today ? "disabled" : ""}>▶</button>
      <button data-review="live">${esc(t.reviewLive)}</button><span style="width:8px"></span>${lead}</div>`;
  }

  // A local day as YYYY-MM-DD, ``offset`` days from today.
  _localDay(offset) {
    const d = new Date(Date.now() + offset * 864e5);
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: this._tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
    return parts;
  }

  _shiftDay(day, offset) {
    const d = new Date(`${day}T12:00:00Z`);
    d.setUTCDate(d.getUTCDate() + offset);
    return d.toISOString().slice(0, 10);
  }

  async _loadReview() {
    const r = this._review;
    if (!r || r.busy) return;
    r.busy = true;
    r.data = null;
    this._render();
    try {
      r.data = await this._hass.callWS({ type: "homebatteryassist/day_review", day: r.day, lead: r.lead });
    } catch (err) {
      console.warn("HomeBatteryAssist: day review not available", err);
      r.data = { failed: true };
    }
    r.busy = false;
    this._render();
  }

  _reviewBlock(t, lang) {
    const r = this._review;
    const d = r.data;
    if (!d) return `<div class="muted">${esc(t.reviewLoading)}</div>`;
    if (d.failed || !d.measured?.length) return `<div class="muted">${esc(t.reviewNone)}</div>`;
    const primary = "var(--primary-color)";
    const pvColor = "#ffd600";
    const batteryColor = "#00c853";
    const gridColor = "#ff1744";
    const priceColor = "var(--primary-text-color)";
    const unit = d.price_unit || "";
    const priceFmt = (v) => `${Number(v).toFixed(3)}${unit ? ` ${unit}` : ""}`;
    const money = new Intl.NumberFormat(lang, { style: "currency", currency: this._hass?.config?.currency || "EUR", minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const axisFmt = (v) => money.format(Number(v));
    // Step lines over slots: [start, value] for each slot of ``minutes``.
    const steps = (rows, value, minutes) => {
      const pts = [];
      for (let i = 0; i < rows.length; i++) {
        const v = value(rows[i]);
        const next = rows[i + 1]?.[0];
        const end = next && next - rows[i][0] <= minutes * 60e3 ? next : rows[i][0] + minutes * 60e3;
        if (v == null) { pts.push([rows[i][0], null]); continue; }
        pts.push([rows[i][0], v], [end - 1, v]);
      }
      return pts;
    };
    const m = d.measured;
    const step = m.length > 1 ? (m[1][0] - m[0][0]) / 60e3 : 15;
    const hf = d.house_forecast || [];
    const hfStep = hf.length > 1 ? (hf[1][0] - hf[0][0]) / 60e3 : 15;
    const rects = hf
      .filter(([, f, a]) => f != null && a != null)
      .map(([ts, f, a]) => [ts, ts + hfStep * 60e3, f, a, a > f ? "#e53935" : "#43a047"]);
    const series = [
      { points: steps(m, (row) => row[1], step), color: primary, label: t.houseMeasured, rects },
      { points: steps(hf, (row) => row[1], hfStep), color: primary, dashed: true, label: `${t.houseMeasured} (${t.reviewForecast})` },
      ...(m.some((row) => row[2]) || d.pv_forecast?.length
        ? [
            { points: steps(m, (row) => row[2], step), color: pvColor, label: t.pvMeasured },
            { points: steps(d.pv_forecast || [], (row) => row[1], 60), color: pvColor, dashed: true, label: `${t.pvMeasured} (${t.reviewForecast})` },
          ]
        : []),
      { points: steps(m, (row) => row[5], step), color: gridColor, label: t.gridMeasured, thin: false },
      ...(m.some((row) => row[3]) || d.battery_plan?.length
        ? [
            { points: steps(m, (row) => row[3], step), color: batteryColor, label: t.batteryLine },
            { points: steps(d.battery_plan || [], (row) => row[1], 15), color: batteryColor, dashed: true, label: t.reviewPlanned },
          ]
        : []),
      ...(d.prices?.length
        ? [
            { points: steps(d.prices, (row) => row[2], 15), color: priceColor, label: t.priceImport, axis: "right", fmt: priceFmt, axisFmt },
            { points: steps(d.prices, (row) => row[1], 15), color: priceColor, dashed: true, label: t.reviewPriceEst, axis: "right", fmt: priceFmt, axisFmt },
          ]
        : []),
    ];
    const ticks = this._hourTicks(d.start, d.end, 3, lang);
    const chart = this._chart("review", series, d.start, d.end, ticks, 2 * 3600e3);
    const item = (color, label, dashed = false) =>
      `<span><i style="${dashed ? `background:none;border-top:2px dashed ${color};height:0` : `background:${color}`}"></i>${esc(label)}</span>`;
    const legend = `<div class="legend" style="flex-wrap:wrap">${series.map((x) => item(x.color, x.label, x.dashed)).join("")}${[
      ["#e53935", t.reviewMore],
      ["#43a047", t.reviewLess],
    ].map(([c, l]) => `<span><i style="background:${c};opacity:.45;height:9px"></i>${esc(l)}</span>`).join("")}</div>`;
    // The day in chips (as the energy flows).
    const nl = lang.startsWith("nl");
    const kwh = (v) => (v == null ? "–" : `${v.toFixed(1).replace(".", nl ? "," : ".")} kWh`);
    const pct = (vs) => (vs && vs[0] ? ` (${vs[1] >= vs[0] ? "+" : ""}${Math.round(((vs[1] - vs[0]) / vs[0]) * 100)}%)` : "");
    const chip = (icon, color, name, value, sub) =>
      `<span class="fd-chip" style="--fd-color:${color}"><ha-icon icon="${icon}"></ha-icon><span><b>${esc(name)}</b> ${esc(value)}${sub ? `<small>${esc(sub)}</small>` : ""}</span></span>`;
    const tot = d.totals || {};
    const followed = d.followed?.real ?? d.followed?.virtual;
    const chips = [
      chip("mdi:home", primary, t.house, `${kwh(tot.house)}${pct(d.house_vs)}`, d.house_vs ? `${t.reviewForecast} ${kwh(d.house_vs[0])}` : ""),
      tot.pv || d.pv_vs ? chip("mdi:solar-power", "#ff9800", t.pv, `${kwh(tot.pv)}${pct(d.pv_vs)}`, d.pv_vs ? `${t.reviewForecast} ${kwh(d.pv_vs[0])}` : "") : "",
      chip("mdi:transmission-tower", "#488fc2", t.grid, `→ ${kwh(tot.imported)} ${t.fdImport.replace(/^[←→]\s*/, "")}`, `← ${kwh(tot.exported)} ${t.fdExport.replace(/^[←→]\s*/, "")}`),
      tot.charged || tot.discharged
        ? chip("mdi:home-battery", "#4db6ac", t.batteries, `↓ ${kwh(tot.charged)} · ↑ ${kwh(tot.discharged)}`, followed != null ? `${t.reviewFollowed} ${Math.round(followed)}%` : "")
        : "",
      d.price_vs ? chip("mdi:currency-eur", "var(--primary-text-color)", t.reviewAvgPrice, priceFmt(d.price_vs[1]), `${t.reviewEstimated} ${priceFmt(d.price_vs[0])}`) : "",
    ].filter(Boolean).join("");
    return `${chart}${legend}<div class="fd-chips review-chips">${chips}</div><div class="muted small">${esc(t.reviewInfo)}</div>`;
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
      const fmt = (d) => d.toLocaleDateString(lang, { timeZone: this._tz, day: "numeric", month: "short" });
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
    const current = this._flowEnd ?? b.now - FLOW_LEAD + span;
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
    for (const button of this.shadowRoot.querySelectorAll(".nav button[data-fdday]")) {
      button.addEventListener("click", () => {
        this._fdDay = button.dataset.fdday === "live" ? null : Number(button.dataset.fdday);
        this._scheduleRender();
      });
    }
    for (const button of this.shadowRoot.querySelectorAll(".nav button[data-day]")) {
      button.addEventListener("click", () => {
        this._dayWeek = button.dataset.day === "all" ? null : Number(button.dataset.day);
        this._hover = null;
        this._scheduleRender();
      });
    }
    for (const button of this.shadowRoot.querySelectorAll(".nav button[data-review]")) {
      button.addEventListener("click", () => {
        const what = button.dataset.review;
        if (what === "live") this._review = null;
        else if (what === "open") this._review = { day: this._localDay(-1), lead: "ahead" };
        else this._review.day = this._shiftDay(this._review.day, what === "older" ? -1 : 1);
        this._hover = null;
        if (this._review) this._loadReview();
        else this._scheduleRender();
      });
    }
    for (const button of this.shadowRoot.querySelectorAll(".nav button[data-lead]")) {
      button.addEventListener("click", () => {
        this._review.lead = button.dataset.lead;
        this._loadReview();
      });
    }
    for (const button of this.shadowRoot.querySelectorAll(".nav button[data-nav]")) {
      button.addEventListener("click", () => this._flowShift(button.dataset.nav));
    }
    for (const button of this.shadowRoot.querySelectorAll(".nav button[data-span]")) {
      button.addEventListener("click", () => {
        this._flowRange = button.dataset.span;
        this._flowEnd = null;
        this._scheduleRender();
      });
    }
    const svg = this.shadowRoot.querySelector('svg[data-chart="forecast"]');
    svg?.addEventListener(
      "wheel",
      (event) => {
        const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.shiftKey ? event.deltaY : 0;
        if (!delta) return; // plain vertical scroll keeps scrolling the page
        if (svg.closest(".xscroll")) return; // its scrollbar moves it
        event.preventDefault();
        this._flowShift("wheel", (delta / 600) * this._flowSpan * 3600e3);
      },
      { passive: false },
    );
  }

  _bindCharts() {
    this._scrolls = this._scrolls || {};
    for (const box of this.shadowRoot.querySelectorAll(".xscroll[data-scroll]")) {
      const id = box.dataset.scroll;
      box.scrollLeft = this._scrolls[id] || 0;
      box.addEventListener("scroll", () => {
        this._scrolls[id] = box.scrollLeft;
      });
    }
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
    const sy = (v, s) =>
      s?.axis === "right" && c.right
        ? c.T + (1 - (v - c.right.min) / (c.right.max - c.right.min)) * (c.H - c.T - c.B)
        : c.T + (1 - (v - c.yMin) / (c.yMax - c.yMin)) * (c.H - c.T - c.B);
    layer.style.display = "";
    const cursor = layer.querySelector(".cursor");
    cursor.setAttribute("x1", sx(anchor[0]));
    cursor.setAttribute("x2", sx(anchor[0]));
    layer.querySelectorAll("circle").forEach((circle) => {
      const hit = hits[Number(circle.dataset.i)];
      circle.style.display = hit ? "" : "none";
      if (hit) {
        circle.setAttribute("cx", sx(hit[0]));
        circle.setAttribute("cy", sy(hit[1], c.series[Number(circle.dataset.i)]));
      }
    });
    const rows = c.series
      .map((s, i) => (hits[i] ? `<div class="r"><span><i style="background:${s.color}"></i>${esc(s.label || "")}</span>
        <b>${esc(s.fmt ? s.fmt(hits[i][1]) : c.yFmt ? c.yFmt(hits[i][1]) : this._power(hits[i][1]))}</b></div>` : ""))
      .join("");
    const extra = c.extra ? c.extra(anchor[0], hits) : "";
    tip.innerHTML = `<div class="t">${esc(c.xFmt(anchor[0]))}</div>${rows}${extra}`;
    tip.hidden = false;
    const box = svg.getBoundingClientRect();
    const parent = tip.parentElement.getBoundingClientRect();
    const px = box.left - parent.left + (sx(anchor[0]) / c.W) * box.width;
    const width = tip.offsetWidth;
    tip.style.left = `${px + 12 + width > parent.width ? Math.max(0, px - width - 12) : px + 12}px`;
    // Small charts: under the chart, so it never covers the lines; wide
    // charts have room beside the cursor.
    const small = box.width < 700;
    tip.style.top = small ? `${box.bottom - parent.top + 4}px` : "28px";
  }

  _consumption(t) {
    const h = this._history;
    if (!h) return "";
    if (!h.hourly.length && !(h.profile?.all || []).some((v) => v != null)) {
      return `<div class="card"><h2>${esc(t.consumption)}</h2><div class="muted">${esc(t.noHistory)}</div></div>`;
    }
    const lang = this._hass.locale?.language || this._hass.language;
    const primary = "var(--primary-color)";

    // Last 7 days: hourly points, ticks at local midnight.
    const pts = h.hourly.map(([time, house]) => [time, house]);
    const excludedPts = h.hourly.map(([time, , excluded]) => [time, excluded]);
    const excludedColor = "#ce93d8"; // purple: clearly different from PV (yellow)
    const xMin = pts.length ? pts[0][0] : Date.now() - 7 * 864e5;
    const xMax = Date.now();
    const ticks = [];
    for (let day = this._zoneMidnight(xMin); day < xMax; day = this._zoneMidnight(day)) {
      ticks.push([day, new Date(day).toLocaleDateString(lang, { timeZone: this._tz, weekday: "short", day: "numeric", month: "numeric" })]);
    }
    const weekSeries = [{ points: pts, color: primary, label: t.houseLine }];
    if (h.has_excluded) weekSeries.push({ points: excludedPts, color: excludedColor, label: t.excludedLine });
    const hourFmt = (v) =>
      new Date(v).toLocaleString(lang, { timeZone: this._tz, weekday: "short", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" });
    const week = this._chart("week", weekSeries, xMin, xMax, ticks, 2 * 3600e3, [], hourFmt);
    const weekLegend = h.has_excluded
      ? `<div class="legend"><span><i style="background:${primary}"></i>${esc(t.houseLine)}</span>
         <span><i style="background:${excludedColor}"></i>${esc(t.excludedLine)}</span></div>`
      : "";

    // Average day: 24 local hours, one line per day of the week.
    const profilePts = (values) => (values || []).map((v, hour) => [hour, v]);
    const hourTicks = [0, 3, 6, 9, 12, 15, 18, 21].map((hour) => [hour, `${String(hour).padStart(2, "0")}:00`]);
    const two = (n) => String(n).padStart(2, "0");
    const weeks = h.profile_weeks || [];
    if (this._dayWeek !== null && this._dayWeek >= weeks.length) this._dayWeek = null;
    const shown = this._dayWeek === null ? null : weeks[this._dayWeek];
    // Monday first; 1 January 2024 was a Monday.
    const dayNames = [0, 1, 2, 3, 4, 5, 6].map((i) =>
      // Noon UTC, named in UTC: the same day in every time zone.
      new Date(Date.UTC(2024, 0, 1 + i, 12)).toLocaleDateString(lang, { timeZone: "UTC", weekday: "short" }),
    );
    const dayColors = ["#1e88e5", "#43a047", "#8e24aa", "#00acc1", "#fdd835", "#fb8c00", "#e53935"];
    const profile = shown || h.profile || {};
    const daySeries = [
      ...dayNames.map((name, i) => ({ points: profilePts(profile.days?.[i]), color: dayColors[i], label: name })),
      { points: profilePts(h.profile?.all), color: "var(--secondary-text-color)", dashed: true, label: t.allAverage },
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
    // kWh per day: the 24 hourly averages added up (missing hours filled
    // with the day's mean); null without enough hours.
    const dayKwh = (values) => {
      const known = (values || []).filter((v) => v != null && Number.isFinite(Number(v))).map(Number);
      if (known.length < 12) return null;
      return (known.reduce((a, b) => a + b, 0) / known.length) * 24 / 1000;
    };
    const kwh = (v) => (v == null ? "–" : v.toLocaleString(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
    const meanOf = (list) => {
      const known = list.filter((v) => v != null);
      return known.length ? known.reduce((a, b) => a + b, 0) / known.length : null;
    };
    const allTotals = dayNames.map((_, i) => dayKwh(h.profile?.days?.[i]));
    const weekTotals = shown ? dayNames.map((_, i) => dayKwh(shown.days?.[i])) : null;
    // Lying down under the chart: a column per day, a row per period.
    const totalsHead = `<tr><th>kWh</th>${dayNames.map((name, i) => `<th><i style="background:${dayColors[i]}"></i>${esc(name)}</th>`).join("")}<th class="avg">${esc(t.dayTotalsAvg)}</th></tr>`;
    const totalsRow = (label, totals) =>
      `<tr><th>${esc(label)}</th>${totals.map((v) => `<td>${kwh(v)}</td>`).join("")}<td class="avg">${kwh(meanOf(totals))}</td></tr>`;
    const dayTotals = allTotals.some((v) => v != null)
      ? `<div class="daytotals-wrap"><table class="daytotals" title="${esc(t.dayTotalsInfo)}">${totalsHead}${
          weekTotals ? totalsRow(t.dayTotalsWeek, weekTotals) : ""
        }${totalsRow(weekTotals ? t.dayTotalsAll : t.dayTotals, allTotals)}</table></div>`
      : "";
    // Expected consumption: past 24 h measured vs. predicted, next 48 h forecast.
    const now = Date.now();
    const secondary = "var(--secondary-text-color)";
    const verified = h.verification || [];
    const fc = h.forecast || [];
    let forecastChart;
    const past = h.past || [];
    const pvFc = h.pv_forecast || [];
    const pvColor = "#ffd600";
    const batteryColor = "#00c853";
    const gridColor = "#ff1744";
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
    // Prices (published solid, forecast dashed) as steps, on the right axis.
    const priceRows = h.price_series || [];
    const priceColor = "var(--primary-text-color)"; // white in a dark theme
    const exportColor = "#ff9100";
    const priceUnit = h.price_unit || "";
    const priceFmt = (v) => `${Number(v).toFixed(2)}${priceUnit ? ` ${priceUnit}` : ""}`;
    const axisMoney = new Intl.NumberFormat(this._hass?.language || "en", { style: "currency", currency: this._hass?.config?.currency || "EUR", minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const axisFmt = (v) => axisMoney.format(Number(v));
    const priceSteps = (rows, value) => {
      const pts = [];
      for (const row of rows) {
        const v = value(row);
        if (v == null) continue;
        pts.push([row[0], v], [row[1] - 1, v]);
      }
      return pts;
    };
    const knownPrices = priceRows.filter((r) => !r[4]);
    const guessedPrices = priceRows.filter((r) => r[4]);
    if (knownPrices.length && guessedPrices.length) guessedPrices.unshift(knownPrices.at(-1));
    const priceSeries = priceRows.length
      ? [
          { points: priceSteps(knownPrices, (r) => r[2]), color: priceColor, label: t.priceImport, axis: "right", fmt: priceFmt },
          { points: priceSteps(guessedPrices, (r) => r[2]), color: priceColor, dashed: true, label: t.priceImportFc, axis: "right", fmt: priceFmt },
          { points: priceSteps(knownPrices, (r) => r[3]), color: exportColor, label: t.priceExport, axis: "right", fmt: priceFmt },
          { points: priceSteps(guessedPrices, (r) => r[3]), color: exportColor, dashed: true, label: t.priceExportFc, axis: "right", fmt: priceFmt },
        ].map((series) => ({ ...series, axisFmt }))
      : [];
    if (!fc.length && !verified.length && !past.length) {
      forecastChart = `<div class="muted">${esc(t.noForecast)}</div>`;
    } else {
      // Visible range: by default from a little before now to the end of the
      // forecast (or of today / tomorrow); scrollable back into the history.
      const firsts = [past[0]?.[0], verified[0]?.[0]].filter((v) => v != null);
      const lasts = [fc.at(-1)?.[0], pvFc.at(-1)?.[0]].filter((v) => v != null);
      const dataMin = Math.min(now - 24 * 3600e3, ...firsts);
      const dataMax = Math.max(now + 3600e3, ...lasts.map((v) => v + 3600e3));
      this._flowBounds = { dataMin, dataMax, now };
      const midnight = this._zoneMidnight(now);
      const rangeEnd = {
        today: midnight,
        tomorrow: this._zoneMidnight(now, 2),
      }[this._flowRange] ?? dataMax;
      const span = Math.max(rangeEnd - (now - FLOW_LEAD), FLOW_LEAD);
      this._flowSpan = span / 3600e3;
      let fMax = this._flowEnd ?? now - FLOW_LEAD + span;
      fMax = Math.min(Math.max(fMax, dataMin + span), Math.max(dataMax, dataMin + span));
      const fMin = fMax - span;
      const step = this._flowSpan <= 24 ? 3 : this._flowSpan <= 72 ? 12 : 24;
      const fTicks = this._hourTicks(fMin, fMax, step, lang);
      const margin = 2 * 3600e3;
      const inView = (points) => points.filter(([ts]) => ts >= fMin - margin && ts <= fMax + margin);
      const slot = 3600e3;  // verification/forecast points are at most an hour apart
      // What the batteries did / are planned to do, as background bands:
      // solar charging, grid charging, discharging; solar alone (faint).
      const bandColors = { pv: "rgba(67,160,71,.28)", grid: "rgba(142,36,170,.28)", discharge: "rgba(30,136,229,.28)", sun: "rgba(253,216,53,.10)" };
      const kindOf = (battery, surplus, pvW) => {
        if (battery < -100) return "discharge";
        if (battery > 100) {
          const fromPv = Math.min(battery, Math.max(surplus, 0));
          return fromPv >= battery - fromPv ? "pv" : "grid";
        }
        return pvW > 50 ? "sun" : null;
      };
      const raw = [];
      past.forEach(([ts, hw, ex, pw, bw], i) => {
        if (hw == null || ts >= now) return;
        const end = Math.min(past[i + 1]?.[0] ?? ts + 3600e3, now);
        raw.push([ts, end, kindOf(bw || 0, (pw || 0) - hw - (ex || 0), pw || 0)]);
      });
      const pvAt = (ts) => pvByHour.get(Math.floor(ts / 3600e3) * 3600e3) || 0;
      batFc.forEach(([ts, power, , grid], i) => {
        const end = batFc[i + 1]?.[0] ?? ts + 900e3;
        if (end <= now) return;
        raw.push([Math.max(ts, now), end, kindOf(power || 0, -((grid || 0) - (power || 0)), pvAt(ts))]);
      });
      const bands = [];
      for (const [from, to, kind] of raw) {
        if (!kind) continue;
        const last = bands[bands.length - 1];
        if (last && last[2] === bandColors[kind] && Math.abs(last[1] - from) < 1000) last[1] = to;
        else bands.push([from, to, bandColors[kind]]);
      }
      // The batteries' total state of charge as an area on the background:
      // measured up to now, planned after.
      const fillBatteries = (h.soc?.batteries || []).filter((b) => b.planned !== false);
      // Measured: the capacity of the batteries summed (also one that is
      // offline now); planned: the plan's own percentage.
      const fillCapacity = fillBatteries.reduce((sum, b) => sum + b.capacity_kwh, 0);
      let fillPoints = [];
      if (fillBatteries.length && fillCapacity > 0) {
        const sums = new Map();
        for (const b of fillBatteries) {
          for (const [ts, kwh] of b.points) sums.set(ts, (sums.get(ts) || 0) + kwh);
        }
        const measured = [...sums.entries()]
          .filter(([ts]) => ts <= now && fillBatteries.every((b) => b.points.some(([bts]) => bts === ts)))
          .sort((a, b) => a[0] - b[0])
          .map(([ts, kwh]) => [ts, (kwh / fillCapacity) * 100]);
        const ahead = (h.battery_forecast || [])
          .filter(([ts, , soc]) => ts > now && soc != null)
          .map(([ts, , soc]) => [ts, soc]);
        fillPoints = inView([...measured, ...ahead]);
      }
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
          ...priceSeries,
          ...(() => {
            // Average price per kWh over the visible part (thin line).
            let sum = 0;
            let time = 0;
            for (const row of priceRows) {
              const from = Math.max(row[0], fMin);
              const to = Math.min(row[1], fMax);
              if (to > from && row[2] != null) {
                sum += row[2] * (to - from);
                time += to - from;
              }
            }
            if (!time) return [];
            const avg = sum / time;
            const points = [];
            for (let ts = fMin; ts < fMax; ts += 1800e3) points.push([ts, avg]);
            points.push([fMax, avg]);
            return [{ points, color: priceColor, thin: true, label: t.priceAverage, axis: "right", fmt: priceFmt, axisFmt }];
          })(),
        ].map((series) => ({ ...series, points: inView(series.points) })),
        fMin,
        fMax,
        fTicks,
        2 * 3600e3,
        now >= fMin && now <= fMax ? [[now, t.now]] : [],
        (v) =>
          new Date(v).toLocaleString(lang, {
            timeZone: this._tz,
            weekday: "short",
            day: "numeric",
            month: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          }),
        null,
        bands.filter(([from, to]) => to >= fMin && from <= fMax),
        fillPoints.length > 1 ? { points: fillPoints } : null,
      );
      this._charts.forecast.gapLimit = slot;

      // State of charge (kWh): measured total + per battery, plan ahead.
      // Only the planned batteries (a real battery with a twin is not:
      // its twin is planned in its place).
      const socBatteries = (h.soc?.batteries || []).filter((b) => b.planned !== false);
      if (socBatteries.length) {
        const capacity =
          h.battery_capacity_kwh || socBatteries.reduce((sum, b) => sum + b.capacity_kwh, 0);
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
            const name = `${b.name}${this._markVirtual(b, t) ? ` (${t.virtual})` : ""}`;
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
      priceRows.length ? item(priceColor, t.priceAxis) : "",
      priceRows.length ? item(exportColor, t.exportAxis) : "",
      item(secondary, t.predicted, true),
    ].join("")}</div>
    <div class="legend" style="flex-wrap:wrap">${[
      ["rgba(253,216,53,.35)", t.bandSun],
      ["rgba(67,160,71,.6)", t.bandPv],
      ["rgba(142,36,170,.6)", t.bandGrid],
      ["rgba(30,136,229,.6)", t.bandDischarge],
      ...(this._charts.forecast?.fill ? [["rgba(158,158,158,.35)", t.bandFill]] : []),
    ].map(([color, label]) => `<span><i style="background:${color};border-radius:2px;width:10px;height:10px"></i>${esc(label)}</span>`).join("")}</div>`;

    const info = t.daysOfData.replace("{days}", Math.round(h.days_covered)) + (h.imported ? ` · ${t.imported}` : "");
    return `<div class="card"><h2>${esc(t.consumption)} · ${esc(info)}</h2><div class="charts">
      <div class="chart wide"><div class="head"><h3>${esc(t.flowTitle)}</h3>${this._flowNav(t)}</div>${
        this._review
          ? this._reviewBlock(t, lang)
          : `${forecastChart}${forecastLegend}
        <div class="muted">${esc(accText)}</div>
        ${h.battery_forecast?.length ? `<div class="muted">${esc(this._planText(h, t))} · ${esc(t.batteryNote)}</div>` : ""}`
      }</div>
      ${socChart ? `<div class="chart wide"><h3>${esc(t.socTitle)}</h3>${socChart}</div>` : ""}
      ${this._temperatureChart(h, t, lang)}
      <div class="chart"><h3>${esc(t.last7)}</h3>${week}${weekLegend}<div class="muted small">${esc(t.last7Info)}</div></div>
      <div class="chart"><div class="head"><h3>${esc(t.avgDay)}</h3>${this._dayNav(t, weeks, lang)}</div>
        ${avg}
        <div class="legend">${dayNames.map((name, i) => `<span><i style="background:${dayColors[i]}"></i>${esc(name)}</span>`).join("")}
        <span>${esc(t.allAverage)}</span></div>${dayTotals}
        <div class="muted small">${esc(t.avgDayInfo)} ${esc(t.dayTotalsInfo)}</div></div>
    </div></div>`;
  }

  // Expected outdoor temperature, learned room temperature and the heating /
  // cooling power to expect (only with a weather source).
  _temperatureChart(h, t, lang) {
    const temp = h.temperature;
    if (!temp || !temp.slots?.length) return "";
    const rows = temp.slots;
    const xMin = rows[0][0];
    const xMax = rows[rows.length - 1][0];
    const span = (xMax - xMin) / 3600e3;
    const step = span <= 48 ? 6 : 24;
    const ticks = this._hourTicks(xMin, xMax, step, lang, true);
    const degrees = (v) => (v == null ? "–" : `${v.toFixed(1).replace(".", lang.startsWith("nl") ? "," : ".")} °C`);
    const axisDeg = (v) => `${Math.round(v)} °C`;
    // Power (W, left) as an orange area; temperatures (°C, right) as lines
    // in cool colours; each axis in the colour of its unit.
    const outdoorColor = "#039be5";
    const roomColor = "#ab47bc";
    const heatColor = "#fb8c00";
    const series = [
      ...(temp.learned ? [{ points: rows.map(([ts, , , w]) => [ts, w]), color: heatColor, label: t.tempPower, area: true, axisColor: heatColor }] : []),
      { points: rows.map(([ts, out]) => [ts, out]), color: outdoorColor, label: t.tempOutdoor, axis: "right", fmt: degrees, axisFmt: axisDeg, axisColor: outdoorColor },
      ...(rows.some((r) => r[2] != null)
        ? [{ points: rows.map(([ts, , room]) => [ts, room]), color: roomColor, dashed: true, label: t.tempRoom, axis: "right", fmt: degrees, axisFmt: axisDeg }]
        : []),
    ];
    const chart = this._chart("temperature", series, xMin, xMax, ticks, 2 * 3600e3);
    // Expected heating/cooling energy per local day (from the slots).
    const perDay = new Map();
    for (let i = 0; i < rows.length; i++) {
      const [ts, , , w] = rows[i];
      if (w == null) continue;
      const next = rows[i + 1]?.[0] ?? ts + (rows.length > 1 ? rows[1][0] - rows[0][0] : 900e3);
      const day = new Date(ts).toLocaleDateString(lang, { timeZone: this._tz, weekday: "short", day: "numeric", month: "numeric" });
      perDay.set(day, (perDay.get(day) || 0) + (w * (next - ts)) / 3600e6);
    }
    const kwh = [...perDay.entries()]
      .map(([day, v]) => `${day}: ${v.toFixed(1).replace(".", lang.startsWith("nl") ? "," : ".")} kWh`)
      .join(" · ");
    const note = temp.learned ? t.tempKwh.replace("{days}", kwh || "–") : t.tempLearning;
    // The legend grouped per unit: W (the area), °C (the lines).
    const item = (s) =>
      `<span><i style="${s.dashed ? `background:none;border-top:2px dashed ${s.color};height:0` : s.area ? `background:${s.color};opacity:.55;height:9px` : `background:${s.color}`}"></i>${esc(s.label)}</span>`;
    const group = (unit, list) => (list.length ? `<span class="group"><b class="unit">${unit}</b>${list.map(item).join("")}</span>` : "");
    const legend = `<div class="legend">${group("W", series.filter((s) => s.axis !== "right"))}${group("°C", series.filter((s) => s.axis === "right"))}</div>`;
    return `<div class="chart wide"><h3>${esc(t.tempTitle)}</h3>${chart}${legend}<div class="muted small">${esc(note)}</div></div>`;
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
    const rows = Object.keys(t.accKinds)
      .filter((kind) => acc[kind])
      .map((kind) => [kind, acc[kind]])
      .map(([kind, k]) => {
        const cells = leads
          .map((lead) => {
            const b = k.lead_times[lead];
            if (!b || !b.samples) return "<td>–</td>";
            const c = k.mode ? corr(kind, b) : "";
            return `<td title="${esc(`${b.samples} · bias ${fmt(kind, b.bias)}${b.mape != null ? ` · ${b.mape}%` : ""}`)}">${esc(fmt(kind, b.mae))}${c ? `<small>${esc(c)}</small>` : ""}</td>`;
          })
          .join("");
        return `<tr><td>${esc(t.accKinds[kind] || kind)}${k.mode ? `<small>${esc(t.accModes[k.mode] || k.mode)}</small>` : ""}</td>${cells}</tr>`;
      })
      .join("");
    const head = `<tr><th></th>${leads.map((l) => `<th>${esc(t.leads[l])}</th>`).join("")}</tr>`;
    const body = any
      ? `<div class="acc-wrap"><table class="acc">${head}${rows}</table></div><div class="muted">${esc(t.accHelp)}</div>`
      : `<div class="muted">${esc(t.accNoData)}</div>`;
    return `${this._planFollowed(t)}<div class="card"><h2>${esc(t.accTitle)}</h2>${body}</div>${this._forecasterAccuracy(t, leads, head)}${this._pvCorrectorAccuracy(t, leads, head)}`;
  }

  // How well the plan was followed (last days), real and virtual batteries.
  _planFollowed(t) {
    const f = this._history?.plan_followed;
    const batteries = this._status?.batteries || [];
    if (!f || !batteries.length) return "";
    const groups = [
      ["virtual", t.followVirtual],
      ["real", t.followReal],
    ].filter(([g]) => batteries.some((b) => !!b.virtual === (g === "virtual")));
    const tiles = groups
      .map(([g, label]) => {
        const v = f[g];
        return `<div class="flow"><div class="value">${v == null ? `<small>${esc(t.followNone)}</small>` : `${Math.round(v)}%`}</div><div class="label">${esc(label)}</div></div>`;
      })
      .join("");
    return `<div class="card"><h2>${esc(t.followTitle.replace("{d}", f.days))}</h2><div class="flows">${tiles}</div><div class="muted">${esc(t.followHelp)}</div></div>`;
  }

  _forecasterAccuracy(t, leads, head) {
    // Every consumption forecaster's own accuracy (before corrections).
    const all = Object.entries(this._history?.forecasters || {}).map(([key, f]) => ({
      name: t.forecasterNames[key] || f.name || key,
      tag: f.chosen ? t.chosen : f.builtin ? t.plannerBuiltin : t.plannerOwn,
      lead_times: f.lead_times,
    }));
    return this._moduleAccuracy(all, leads, head, "W", t.forecastersTitle, t.forecastersHelp);
  }

  _pvCorrectorAccuracy(t, leads, head) {
    // Every PV correction's accuracy, next to the uncorrected forecast.
    const all = Object.entries(this._history?.pv_correctors || {}).map(([key, f]) => ({
      name: t.pvCorrectorNames[key] || f.name || key,
      tag: f.chosen ? t.chosen : f.builtin ? t.plannerBuiltin : t.plannerOwn,
      lead_times: f.lead_times,
    }));
    const raw = this._history?.accuracy?.pv?.lead_times;
    if (all.length && raw) all.push({ name: t.uncorrected, tag: "", lead_times: raw });
    return this._moduleAccuracy(all, leads, head, "Wh", t.pvCorrectorsTitle, t.pvCorrectorsHelp);
  }

  _moduleAccuracy(all, leads, head, unit, title, help) {
    // Modules side by side: average deviation per lead time, the lowest in bold.
    if (all.length < 2) return "";
    const best = Object.fromEntries(
      leads.map((lead) => {
        const values = all
          .map((f) => f.lead_times[lead])
          .filter((b) => b && b.samples && b.mae != null)
          .map((b) => b.mae);
        return [lead, values.length > 1 ? Math.min(...values) : null];
      }),
    );
    const rows = all
      .map((f) => {
        const cells = leads
          .map((lead) => {
            const b = f.lead_times[lead];
            if (!b || !b.samples || b.mae == null) return "<td>–</td>";
            const text = `${Math.round(b.mae)} ${unit}`;
            return `<td title="${b.samples} · bias ${Math.round(b.bias)} ${unit}">${b.mae === best[lead] ? `<b>${esc(text)}</b>` : esc(text)}</td>`;
          })
          .join("");
        return `<tr><td>${esc(f.name)}${f.tag ? `<small>${esc(f.tag)}</small>` : ""}</td>${cells}</tr>`;
      })
      .join("");
    return `<div class="card"><h2>${esc(title)}</h2>
      <div class="acc-wrap"><table class="acc">${head}${rows}</table></div>
      <div class="muted">${esc(help)}</div></div>`;
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

  _planner(s, t) {
    const p = s.planner;
    if (!p) return "";
    const name = t.planModes[p.key] || p.name || p.key;
    const kind = p.builtin ? t.plannerBuiltin : t.plannerOwn;
    const unit = this._history?.price_unit?.split("/")[0] || "";
    const saving =
      p.saving == null
        ? ""
        : ` · ${t.plannerSaving.replace("{saving}", `${p.saving.toFixed(2)} ${unit}`.trim()).replace("{until}", this._time(p.until))}`;
    const warn = p.fallback ? `<div class="alert-text">${esc(t.plannerFallback)}</div>` : "";
    const module = (label, m, names) => {
      if (!m) return "";
      const text = names[m.key] || m.name || m.key;
      const tag = m.fallback ? t.moduleFallback : m.builtin ? t.plannerBuiltin : t.plannerOwn;
      return `<div class="sub"><span class="muted">${esc(label)}</span> ${esc(text)} <small class="muted">(${esc(tag)})</small></div>`;
    };
    return `<div class="card planner"><span class="muted">${esc(t.plannerActive)}</span>
      <b>${esc(name.charAt(0).toUpperCase() + name.slice(1))}</b> <small class="muted">(${esc(kind)})</small>${esc(saving)}${warn}
      ${this._controlLine(s.control, t)}${module(t.plannerForecaster, p.forecaster, t.forecasterNames)}${module(t.plannerTariff, p.tariff, t.tariffNames)}${module(t.plannerPvCorrector, p.pv_corrector, t.pvCorrectorNames)}${this._interceptorLine(p.interceptor, t)}</div>`;
  }

  // Control by HomeBatteryAssist: the mode and per battery active / why held.
  _controlLine(c, t) {
    if (!c) return "";
    const each = (c.batteries || [])
      .map((b) => `<b>${esc(b.name)}</b> · ${b.held ? `<span class="alert-text">${esc(t.controlHeld[b.held] || b.held)}</span>` : esc(t.controlActive)}`)
      .join(" · ");
    // The mode is the active planner module above: not repeated here.
    return `<div class="sub"><span class="muted">${esc(t.controlLine)}</span> ${each}</div>`;
  }

  // The interceptor (own module) and what it holds back or limits now.
  _interceptorLine(ic, t) {
    if (!ic) return "";
    const what = (ic.changes || [])
      .map((c) => `${c.battery}: ${t.icActions[c.action] || c.action}${c.action === "limit" ? ` ${Math.abs(c.power_w)} W` : ""}${c.reason ? ` (${c.reason})` : ""}`)
      .join("; ");
    return `<div class="sub"><span class="muted">${esc(t.plannerInterceptor)}</span> ${esc(ic.name)} <small class="muted">(${esc(t.plannerOwn)})</small>${
      what ? ` · <span class="alert-text">${esc(what)}</span>` : ` · <small class="muted">${esc(t.icAllThrough)}</small>`}</div>`;
  }

  // The plan at a glance: now, next, the plan, the sun, the cheapest price.
  _summary(s, t) {
    const lines = s.summary || [];
    if (!lines.length) return "";
    const rows = lines.map((l) => `<div class="summary-row"><b>${esc(l.label)}</b><span>${esc(l.text)}</span></div>`).join("");
    return `<div class="card"><h2>${esc(t.summaryTitle)}</h2><div class="summary">${rows}</div></div>`;
  }

  _decisions(s, t) {
    const items = s.decisions.length
      ? `<ul class="decisions">${s.decisions.map((d) => `<li><time>${this._time(d.time)}</time><div>${this._message(d.message)}</div></li>`).join("")}</ul>`
      : `<div class="muted">${esc(t.noDecisions)}</div>`;
    return `<div class="card"><h2>${esc(t.decisions)}</h2>${items}</div>`;
  }

  // Occasional consumption: energy per day, extra or part of the
  // expected consumption, optionally in a time window. One dialog from the
  // toolbar: the list, and a form to add or change.
  _openAdjustments() {
    if (this._dialogOpen) return;
    this._dialogOpen = true;
    const overlay = document.createElement("div");
    overlay.className = "adj-overlay";
    this.shadowRoot.appendChild(overlay);
    // Recalculated once, when the dialog closes, and only after a change.
    let changed = false;
    const close = () => {
      overlay.remove();
      this._dialogOpen = false;
      if (changed) this._recalculate();
      else this._render();
    };
    overlay.addEventListener("click", (ev) => {
      if (ev.target === overlay) close();
    });
    overlay.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") close();
    });
    const after = (result) => {
      changed = true;
      if (this._status) this._status.adjustments = result.adjustments;
      // Saved after the dialog was closed (Escape while saving).
      if (!overlay.isConnected) this._recalculate();
    };
    const list = () => this._adjustmentList(overlay, close, form, after);
    const form = (row) => this._adjustmentForm(overlay, row, list, after);
    list();
  }

  _adjustmentList(overlay, close, form, after) {
    const t = this._t;
    const lang = this._hass.locale?.language || this._hass.language;
    const rows = this._status?.adjustments || [];
    const dayText = (iso) =>
      new Date(`${iso}T12:00:00`).toLocaleDateString(lang, { timeZone: this._tz, weekday: "short", day: "numeric", month: "numeric" });
    const num = (v) => Number(v).toLocaleString(lang, { maximumFractionDigits: 2 });
    const items = rows.length
      ? rows
          .map((r) => {
            const when = r.from ? `${r.from}–${r.until}` : t.adjWholeDay;
            let what;
            if (r.kind === "energy_kwh") what = `${num(r.value)} kWh · ${r.part ? t.adjPartShort : t.adjExtraShort}`;
            else if (r.kind === "factor") what = `× ${num(r.value)} · ${t.adjByAction}`;
            else if (r.kind === "offset_w") what = `${r.value >= 0 ? "+" : ""}${num(r.value)} W · ${t.adjByAction}`;
            else what = `= ${num(r.value)} W · ${t.adjByAction}`;
            const edit = r.kind === "energy_kwh" ? `<button data-edit="${esc(r.id)}">${esc(t.adjEdit)}</button>` : "";
            return `<div class="adj-row"><span class="what"><b>${esc(dayText(r.date))} ${esc(when)}</b> · ${esc(r.name)}<br><span class="muted">${esc(what)}</span></span>
              ${edit}<button data-del="${esc(r.id)}">${esc(t.adjDelete)}</button></div>`;
          })
          .join("")
      : `<div class="muted">${esc(t.adjNone)}</div>`;
    overlay.innerHTML = `<div class="adj-dialog" role="dialog" aria-modal="true">
        <h2>${esc(t.adjTitle)}</h2>
        <div class="muted">${esc(t.adjNote)}</div>
        <div class="adj-list">${items}</div>
        <div class="error"></div>
        <div class="adj-actions"><button data-act="close">${esc(t.adjClose)}</button><button class="primary" data-act="add">${esc(t.adjAdd)}</button></div>
      </div>`;
    const error = overlay.querySelector(".error");
    overlay.querySelector('[data-act="close"]').addEventListener("click", close);
    overlay.querySelector('[data-act="add"]').addEventListener("click", () => form(null));
    overlay.querySelectorAll("button[data-edit]").forEach((button) =>
      button.addEventListener("click", () => form(rows.find((r) => r.id === button.dataset.edit))),
    );
    overlay.querySelectorAll("button[data-del]").forEach((button) =>
      button.addEventListener("click", async () => {
        try {
          after(await this._hass.callWS({ type: "homebatteryassist/adjustment_delete", adjustment_id: button.dataset.del }));
          this._adjustmentList(overlay, close, form, after);
        } catch (err) {
          error.textContent = `${t.adjFailed}: ${err?.message || err}`;
        }
      }),
    );
    overlay.querySelector('[data-act="add"]').focus();
  }

  _adjustmentForm(overlay, row, back, after) {
    const t = this._t;
    // Dates in Home Assistant's time zone: the backend reads the day and
    // times there (the browser may be elsewhere).
    const zone = this._hass.config?.time_zone;
    const local = (d) => new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
    const today = new Date();
    const tomorrow = new Date(today.getTime() + 864e5);
    const r = row || { name: "", date: local(tomorrow), from: null, until: null, value: "", part: false };
    overlay.innerHTML = `<div class="adj-dialog" role="dialog" aria-modal="true">
        <h2>${esc(row ? t.adjEdit : t.adjAdd)} · ${esc(t.adjTitle.toLowerCase())}</h2>
        <label>${esc(t.adjName)}<input type="text" name="name" maxlength="40" placeholder="${esc(t.adjNamePlaceholder)}" value="${esc(r.name || "")}"></label>
        <label>${esc(t.adjDay)}<input type="date" name="date" min="${local(today)}" value="${esc(r.date)}"></label>
        <div class="times">
          <label>${esc(t.adjFrom)}<input type="time" name="from" value="${esc(r.from || "")}"></label>
          <label>${esc(t.adjUntil)}<input type="time" name="until" value="${esc(r.until || "")}"></label>
        </div>
        <label>${esc(t.adjEnergy)}<input type="number" name="energy" step="0.1" min="-500" max="500" value="${esc(r.value ?? "")}"></label>
        <label class="choice"><input type="radio" name="kind" value="extra" ${r.part ? "" : "checked"}>${esc(t.adjExtra)}</label>
        <label class="choice"><input type="radio" name="kind" value="part" ${r.part ? "checked" : ""}>${esc(t.adjPart)}</label>
        <div class="error"></div>
        <div class="adj-actions"><button data-act="cancel">${esc(t.adjCancel)}</button><button class="primary" data-act="save">${esc(t.adjSave)}</button></div>
      </div>`;
    const field = (name) => overlay.querySelector(`[name="${name}"]`);
    const error = overlay.querySelector(".error");
    overlay.querySelector('[data-act="cancel"]').addEventListener("click", back);
    overlay.querySelector('[data-act="save"]').addEventListener("click", async () => {
      const from = field("from").value || null;
      const until = field("until").value || null;
      const energy = parseFloat(String(field("energy").value).replace(",", "."));
      const part = overlay.querySelector('[name="kind"]:checked')?.value === "part";
      if (Number.isNaN(energy) || energy === 0) {
        error.textContent = t.adjNeedEnergy;
        return;
      }
      if (part && !(from && until)) {
        error.textContent = t.adjNeedWindow;
        return;
      }
      const msg = {
        type: "homebatteryassist/adjustment_save",
        name: field("name").value,
        date: field("date").value,
        from: from && until ? from : null,
        until: from && until ? until : null,
        energy_kwh: energy,
        part,
      };
      if (row?.id) msg.adjustment_id = row.id;
      try {
        after(await this._hass.callWS(msg));
        back();
      } catch (err) {
        error.textContent = `${t.adjFailed}: ${err?.message || err}`;
      }
    });
    field("energy").focus();
  }

  // Charge the car: when to switch the charging on for the lowest expected
  // cost within a period (advice only). The last inputs are remembered.
  _openEvAdvice() {
    if (this._dialogOpen) return;
    this._dialogOpen = true;
    const t = this._t;
    const lang = this._hass.locale?.language || this._hass.language;
    const zone = this._hass.config?.time_zone;
    const overlay = document.createElement("div");
    overlay.className = "adj-overlay";
    this.shadowRoot.appendChild(overlay);
    const close = () => {
      overlay.remove();
      this._dialogOpen = false;
      this._render();
    };
    overlay.addEventListener("click", (ev) => {
      if (ev.target === overlay) close();
    });
    overlay.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") close();
    });
    // Date and time in Home Assistant's time zone (the backend reads them there).
    const localInput = (d) => {
      const parts = Object.fromEntries(
        new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
          .formatToParts(d)
          .map((p) => [p.type, p.value]),
      );
      return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
    };
    let saved = {};
    try {
      saved = JSON.parse(localStorage.getItem("homebatteryassist-ev") || "{}");
    } catch (err) {
      saved = {};
    }
    const now = new Date();
    const morning = new Date(now.getTime() + 864e5);
    const untilDefault = `${localInput(morning).slice(0, 10)}T07:00`;
    overlay.innerHTML = `<div class="adj-dialog" role="dialog" aria-modal="true">
        <h2>${esc(t.evTitle)}</h2>
        <div class="muted">${esc(t.evNote)}</div>
        <label>${esc(t.evKwh)}<input type="number" name="kwh" step="0.5" min="0.1" max="200" value="${esc(saved.kwh ?? 20)}"></label>
        <label>${esc(t.evPower)}<input type="number" name="power" step="0.1" min="0.5" max="50" value="${esc(saved.power ?? 11)}"></label>
        <div class="times">
          <label>${esc(t.evFrom)}<input type="datetime-local" name="start" value="${esc(localInput(now))}"></label>
          <label>${esc(t.evUntil)}<input type="datetime-local" name="end" value="${esc(untilDefault)}"></label>
        </div>
        <div class="ev-result"></div>
        <div class="error"></div>
        <div class="adj-actions"><button data-act="close">${esc(t.evClose)}</button><button class="primary" data-act="calc">${esc(t.evCalculate)}</button></div>
      </div>`;
    const field = (name) => overlay.querySelector(`[name="${name}"]`);
    const result = overlay.querySelector(".ev-result");
    const error = overlay.querySelector(".error");
    const when = (iso) =>
      iso ? new Date(iso).toLocaleString(lang, { timeZone: zone, weekday: "short", hour: "2-digit", minute: "2-digit" }) : "–";
    const money = (v, currency) =>
      v == null ? "–" : new Intl.NumberFormat(lang, { style: "currency", currency: currency || "EUR", maximumFractionDigits: 3 }).format(v);
    overlay.querySelector('[data-act="close"]').addEventListener("click", close);
    overlay.querySelector('[data-act="calc"]').addEventListener("click", async () => {
      error.textContent = "";
      result.innerHTML = "";
      const kwh = parseFloat(String(field("kwh").value).replace(",", "."));
      const power = parseFloat(String(field("power").value).replace(",", "."));
      try {
        localStorage.setItem("homebatteryassist-ev", JSON.stringify({ kwh, power }));
      } catch (err) {
        // no storage: not remembered
      }
      try {
        const a = await this._hass.callWS({
          type: "homebatteryassist/ev_advice",
          kwh,
          power_kw: power,
          start: field("start").value,
          end: field("end").value,
        });
        const until = when(a.prices_until);
        if (a.reason) {
          result.innerHTML = `<p>${esc((t.evReason[a.reason] || a.reason).replace("{until}", until))}</p>`;
          return;
        }
        const lines = [
          `<p><b>${esc(t.evAdvice.replace("{start}", when(a.start)).replace("{end}", when(a.end)))}</b></p>`,
          `<p>${esc(t.evCost.replace("{cost}", money(a.cost, a.currency)).replace("{avg}", money(a.avg_price, a.currency)))}${a.sun_kwh > 0.05 ? `, ${esc(t.evSun.replace("{kwh}", Number(a.sun_kwh).toLocaleString(lang, { maximumFractionDigits: 1 })))}` : ""}.</p>`,
        ];
        if (a.now_cost != null && Math.abs(a.now_cost - a.cost) >= 0.01) {
          lines.push(`<p class="muted">${esc(t.evNow.replace("{start}", when(a.now_start)).replace("{cost}", money(a.now_cost, a.currency)))}</p>`);
        }
        lines.push(`<p class="muted">${esc(t.evPricesUntil.replace("{until}", until))}</p>`);
        result.innerHTML = lines.join("");
      } catch (err) {
        error.textContent = `${t.evFailed}: ${err?.message || err}`;
      }
    });
    field("kwh").focus();
  }

  // The activity log: fetched when its tab is open (at most every minute).
  async _loadActivity(force) {
    const days = this._logDays || 7;
    if (!force && this._activity && this._activity.days === days && Date.now() - this._activityAt < 60000) return;
    if (this._activityBusy) return;
    this._activityBusy = true;
    this._activityAt = Date.now();
    try {
      const result = await this._hass.callWS({ type: "homebatteryassist/activity", days });
      this._activity = { ...result, days };
    } catch (err) {
      // Not available: show empty, try again after a minute (never a loop).
      console.warn("HomeBatteryAssist: activity log not available", err);
      this._activity = { periods: [], days, failed: true };
    }
    this._activityBusy = false;
    this._render();
  }

  _activityRows(t) {
    const unit = this._activity?.price_unit || "";
    const time = (iso) => new Date(iso).toLocaleString(this._hass.language, { timeZone: this._tz, weekday: "short", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" });
    return (this._activity?.periods || []).map((p) => [
      time(p.start),
      time(p.end),
      p.name,
      t.logKinds[p.kind] || p.kind,
      p.kind === "idle" ? "" : p.kwh.toFixed(2),
      p.kind === "idle" ? "" : String(Math.round(p.max_w)),
      p.price == null ? "" : `${p.price.toFixed(3)}${unit ? ` ${unit}` : ""}`,
      t.logSources[p.source] || p.source,
      p.plan == null ? "" : `${p.follows ? "✓" : "✗"} ${t.logPlan[p.plan] || p.plan}`,
      this._logReasons(t, p.reasons),
      p,
    ]);
  }

  // Reasons of a period, most minutes first; with minutes when there are more.
  _logReasons(t, reasons) {
    const list = Object.entries(reasons || {}).sort((a, b) => b[1] - a[1]);
    const name = (k) => t.logReasons[k] || k;
    if (list.length <= 1) return list.length ? name(list[0][0]) : "";
    return list.map(([k, m]) => `${name(k)} (${Math.round(m)} min)`).join(", ");
  }

  _activityLog(t) {
    const days = this._logDays || 7;
    const pick = [1, 7, 30]
      .map((d) => `<button data-log-days="${d}" class="${d === days ? "active" : ""}">${d} ${esc(d === 1 ? t.logDay : t.logDays)}</button>`)
      .join("");
    const rows = this._activityRows(t);
    const head = `<tr>${t.logCols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>`;
    const body = rows
      .map((r) => {
        const p = r[10];
        const cls = p.source === "incident" ? "incident" : p.follows === false ? "off-plan" : "";
        return `<tr class="${cls}">${r.slice(0, 10).map((v, i) => `<td class="${i >= 4 && i <= 6 ? "num" : ""}">${esc(v)}</td>`).join("")}</tr>`;
      })
      .join("");
    const clock = (text) => String(text).split(", ").pop();
    const cards = rows
      .map((r) => {
        const p = r[10];
        const cls = p.source === "incident" ? "incident" : p.follows === false ? "off-plan" : "";
        const amount = [r[4] ? `${r[4]} kWh` : "", r[5] ? `max ${r[5]} W` : ""].filter(Boolean).join(" · ");
        const second = [r[7], r[8], r[9]].filter(Boolean).join(" · ");
        return `<div class="log-card ${cls}"><div class="l1"><span><b>${esc(r[0])}–${esc(clock(r[1]))}</b> · ${esc(r[3])}</span><span>${esc(amount)}</span></div>${
          second ? `<div class="l2">${esc(second)}</div>` : ""
        }</div>`;
      })
      .join("");
    const table = rows.length
      ? `<div class="acc-wrap log-wide"><table class="log">${head}${body}</table></div><div class="log-cards">${cards}</div>`
      : `<div class="muted">${esc(t.logEmpty)}</div>`;
    return `<div class="card"><div class="head"><h2>${esc(t.logTitle)}</h2><span class="log-nav">${pick}<button class="log-csv">${esc(t.logCsv)}</button></span></div>
      ${table}<div class="muted small">${esc(t.logHelp)}</div></div>`;
  }

  _activityCsv() {
    const t = this._t;
    const quote = (v) => `"${String(v).replace(/"/g, '""')}"`;
    const lines = [t.logCols, ...this._activityRows(t).map((r) => r.slice(0, 10))].map((r) => r.map(quote).join(";"));
    const blob = new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `homebatteryassist-log-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  _render() {
    if (!this._hass) return;
    // A dialog is open: keep its fields (render again when it closes).
    if (this._dialogOpen) return;
    const t = this._t;
    let body;
    if (this._error === "not_loaded") body = `<div class="card">${esc(t.notLoaded)}</div>`;
    else if (this._error) body = `<div class="card">${esc(t.error)}: ${esc(this._error)}</div>`;
    else if (!this._status) body = "";
    else {
      const s = this._status;
      const tabs = {
        overview: () => [this._planner(s, t), this._summary(s, t), this._flows(s, t), this._flowDiagram(s, t), this._phases(s, t), this._decisions(s, t)],
        forecast: () => [this._consumption(t), this._planning(s, t), this._decisions(s, t)],
        value: () => [this._compare(s, t), this._planCheck(s, t)],
        batteries: () => [this._batteries(s, t)],
        check: () => [this._accuracy(t)],
        log: () => [this._activityLog(t)],
      };
      const tab = tabs[this._tab] ? this._tab : "overview";
      const bar = Object.keys(tabs)
        .map((k) => `<button data-tab="${k}" class="${k === tab ? "active" : ""}">${esc(t.tabs[k])}</button>`)
        .join("");
      body = `<div class="tabs">${bar}</div>${tabs[tab]().join("")}`;
      if (this._actionError) {
        // An action (plan mode, recalculate) failed: shown until the next one.
        body = `<div class="card">${esc(t.error)}: ${esc(this._actionError)}</div>${body}`;
      }
    }
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <div class="toolbar"><span class="menu"></span><span class="title">${esc(t.title)}${VERSION ? `<span class="version">v${esc(VERSION)}</span>` : ""}${STAGE ? `<span class="stage">${esc(STAGE)}</span>` : ""}</span>
        ${this._status ? `<button class="ev-open" title="${esc(t.evTitle)}"><ha-icon icon="mdi:car-electric"></ha-icon><span class="label">${esc(t.evButton)}</span></button>` : ""}
        ${this._status ? `<button class="adj-open" title="${esc(t.adjTitle)}"><ha-icon icon="mdi:calendar-plus"></ha-icon><span class="label">${esc(t.adjButton)}${(this._status.adjustments || []).length ? ` (${this._status.adjustments.length})` : ""}</span></button>` : ""}
        ${this._status ? `<button class="recalc" ${this._busy ? "disabled" : ""}>
          <ha-icon icon="mdi:refresh"></ha-icon><span class="label">${esc(this._busy ? t.recalculating : t.recalculate)}</span></button>` : ""}</div>
      <div class="content">${body}</div>`;
    const menu = document.createElement("ha-menu-button");
    menu.hass = this._hass;
    menu.narrow = this._narrow;
    this.shadowRoot.querySelector(".menu").appendChild(menu);
    this.shadowRoot.querySelector(".recalc")?.addEventListener("click", () => this._recalculate());
    // The active tab in view (on a phone the row of tabs scrolls sideways).
    const active = this.shadowRoot.querySelector(".tabs button.active");
    if (active) active.parentElement.scrollLeft = Math.max(active.offsetLeft - 24, 0);
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
    this.shadowRoot.querySelectorAll("button[data-log-days]").forEach((button) =>
      button.addEventListener("click", () => {
        this._logDays = Number(button.dataset.logDays);
        this._loadActivity(true);
      }),
    );
    this.shadowRoot.querySelector("button.log-csv")?.addEventListener("click", () => this._activityCsv());
    if (this._tab === "log") this._loadActivity(false);
    this.shadowRoot.querySelector("button.adj-open")?.addEventListener("click", () => this._openAdjustments());
    this.shadowRoot.querySelector("button.ev-open")?.addEventListener("click", () => this._openEvAdvice());
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
