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
    noBatteries: "No batteries linked yet. Add one under Settings → Devices & services → HomeBatteryAssist.",
    stored: "Stored",
    usable: "Usable",
    fullAt: "Full at",
    emptyAt: "Empty at",
    phases: "Grid connection",
    phase: "Phase",
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
    pvMeasured: "PV",
    pvExpected: "PV expected",
    batteryLine: "Battery (+ charging / − discharging)",
    flowTitle: "Energy flows and expected consumption (past 24 h, next 48 h)",
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
    noBatteries: "Nog geen batterijen gekoppeld. Voeg er een toe via Instellingen → Apparaten & diensten → HomeBatteryAssist.",
    stored: "Opgeslagen",
    usable: "Bruikbaar",
    fullAt: "Vol om",
    emptyAt: "Leeg om",
    phases: "Netaansluiting",
    phase: "Fase",
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
    pvMeasured: "PV",
    pvExpected: "PV verwacht",
    batteryLine: "Batterij (+ laden / − ontladen)",
    flowTitle: "Energiestromen en verwacht verbruik (afgelopen 24 uur, komende 48 uur)",
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
  .card { background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px);
    box-shadow: var(--ha-card-box-shadow, none); border: 1px solid var(--divider-color); padding: 16px; }
  h2 { margin: 0 0 12px; font-size: 16px; font-weight: 500; color: var(--secondary-text-color); }
  .flows { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
  .flow { display: flex; flex-direction: column; gap: 4px; padding: 12px; border-radius: 10px;
    background: var(--secondary-background-color); }
  .flow ha-icon { --mdc-icon-size: 28px; color: var(--state-icon-color, var(--primary-color)); }
  .flow .value { font-size: 24px; font-weight: 500; }
  .flow .label { color: var(--secondary-text-color); font-size: 13px; }
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
  .bar .fill.warn { background: var(--warning-color, #f4b400); }
  .bar .fill.alert { background: var(--error-color, #db4437); }
  .bar .mark { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--primary-text-color); opacity: .5; }
  .bar .text { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 500; color: var(--primary-text-color); }
  .row { display: flex; justify-content: space-between; font-size: 14px; color: var(--secondary-text-color); }
  .row b { color: var(--primary-text-color); font-weight: 500; }
  .phases { display: grid; gap: 10px; }
  .phase { display: grid; grid-template-columns: 40px 1fr 190px; gap: 8px; align-items: center; font-size: 14px; }
  .phase b { color: var(--primary-text-color); font-weight: 500; }
  ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; }
  li { display: grid; grid-template-columns: 90px 1fr; gap: 8px; font-size: 14px; }
  li time { color: var(--secondary-text-color); }
  .muted { color: var(--secondary-text-color); }
  .charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
  .chart h3 { margin: 0 0 6px; font-size: 14px; font-weight: 500; }
  .chart svg { width: 100%; height: auto; display: block; }
  .chart .grid { stroke: var(--divider-color); stroke-width: 1; }
  .chart .axis { fill: var(--secondary-text-color); font-size: 11px; }
  .chart .line { fill: none; stroke-width: 2; stroke-linejoin: round; }
  .chart .line.dashed { stroke-dasharray: 5 4; stroke-width: 1.5; }
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
    this._hover = null;
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
    if (s.has_pv || s.has_pv_forecast) {
      const expected = s.pv_forecast_now_w == null ? "" : `${t.expected} ${this._power(s.pv_forecast_now_w)}`;
      const value = s.has_pv ? this._power(this._num(e.pv_power)) : "–";
      const sub = [s.has_pv ? "" : t.notMeasured, expected].filter(Boolean).join(" · ");
      parts.push(this._flow("pv", "mdi:solar-power", t.pv, value, sub));
    }
    if (s.batteries.length) {
      const power = this._num(e.batteries_power);
      const soc = this._num(e.batteries_soc);
      const mode = power === null ? "" : power > 20 ? t.charging : power < -20 ? t.discharging : t.idle;
      parts.push(
        this._flow("battery", "mdi:home-battery", t.batteries, this._power(power === null ? null : Math.abs(power)),
          [mode, soc === null ? "" : `${Math.round(soc)}%`].filter(Boolean).join(" · ")),
      );
    }
    if (s.has_excluded) parts.push(this._flow("excluded", "mdi:ev-station", t.excluded, this._power(this._num(e.excluded_power))));
    return `<div class="card"><h2>${esc(t.flows)}</h2><div class="flows">${parts.join("")}</div></div>`;
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
      <div class="head"><span class="name">${esc(b.name)}</span>
        <span class="status ${esc(status || "")}">${esc(status ? t[status] || status : t.unavailable)}</span></div>
      <div class="bar"><div class="fill ${cls}" style="width:${fill}%"></div>
        <div class="mark" style="left:${b.min_soc}%"></div><div class="mark" style="left:${b.max_soc}%"></div>
        <div class="text">${soc === null ? "–" : `${Math.round(soc)}%`}</div></div>
      <div class="row"><span>${esc(t.stored)}</span><b>${this._kwh(this._num(e.battery_stored_energy))} / ${b.capacity_kwh} kWh</b></div>
      <div class="row"><span>${esc(t.usable)}</span><b>${this._kwh(this._num(e.battery_usable_energy))}</b></div>
      <div class="row"><span>${esc(status === "discharging" ? t.discharging : t.charging)}</span><b>${this._power(power === null ? null : Math.abs(power))}</b></div>
      ${target ? `<div class="row"><span>${esc(status === "charging" ? t.fullAt : t.emptyAt)}</span><b>${this._time(target)}</b></div>` : ""}
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
      rows.push(`<div class="phase"><span>L${i}</span>
        <div class="bar"><div class="fill ${cls}" style="width:${Math.min(load ?? 0, 100)}%"></div>
          <div class="text">${load === null ? "–" : `${Math.round(load)}%`}</div></div>
        <span class="muted"><b>${this._power(power)}</b> · ${current == null ? "–" : `${current} A`} / ${s.max_current} A</span></div>`);
    }
    return `<div class="card"><h2>${esc(t.phases)} · ${s.phases}x${s.max_current}A</h2><div class="phases">${rows.join("")}</div></div>`;
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

  _chart(id, series, xMin, xMax, ticks, gapLimit, markers = [], xFmt = (v) => this._time(new Date(v).toISOString())) {
    // Full-width charts get a wider canvas so they are as high as the others.
    const W = id === "forecast" ? 1232 : 600, H = 190, L = 46, R = 8, T = 8, B = 24;
    const all = series.flatMap((s) => s.points.map((p) => p[1])).filter((v) => v != null);
    const yMax = this._niceMax(Math.max(...all, 0));
    const low = Math.min(...all, 0);
    const yMin = low < 0 ? -this._niceMax(-low) : 0;
    const x = (v) => L + ((v - xMin) / (xMax - xMin || 1)) * (W - L - R);
    const y = (v) => T + (1 - (v - yMin) / (yMax - yMin)) * (H - T - B);
    let svg = "";
    const steps = 4;
    for (let i = 0; i <= steps; i++) {
      const v = yMin + ((yMax - yMin) / steps) * i;
      svg += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`;
      svg += `<text class="axis" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${esc(this._power(v))}</text>`;
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
      svg += `<path class="line${s.dashed ? " dashed" : ""}" d="${d}" stroke="${s.color}"/>`;
    }
    for (const [v, label] of markers) {
      svg += `<line class="now" x1="${x(v)}" x2="${x(v)}" y1="${T}" y2="${H - B}"/>`;
      svg += `<text class="axis" x="${x(v) + 4}" y="${T + 10}">${esc(label)}</text>`;
    }
    svg += `<g class="hover" style="display:none"><line class="cursor" y1="${T}" y2="${H - B}"/>
      ${series.map((s, i) => `<circle r="3.5" data-i="${i}" style="fill:${s.color}"/>`).join("")}</g>`;
    this._charts[id] = { series, xMin, xMax, yMin, yMax, W, H, L, R, T, B, gapLimit, xFmt };
    return `<svg data-chart="${id}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">${svg}</svg>
      <div class="tip" data-tip="${id}" hidden></div>`;
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
        <b>${esc(this._power(hits[i][1]))}</b></div>` : ""))
      .join("");
    tip.innerHTML = `<div class="t">${esc(c.xFmt(anchor[0]))}</div>${rows}`;
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
    const excludedColor = "var(--warning-color, #ff9800)";
    const xMin = pts.length ? pts[0][0] : Date.now() - 7 * 864e5;
    const xMax = Date.now();
    const ticks = [];
    const day = new Date(xMin);
    day.setHours(24, 0, 0, 0);
    for (; day.getTime() < xMax; day.setDate(day.getDate() + 1)) {
      ticks.push([day.getTime(), day.toLocaleDateString(lang, { weekday: "short" })]);
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
    const avg = this._chart(
      "day",
      [
        { points: profilePts(h.profile.weekday), color: primary, label: t.weekday },
        { points: profilePts(h.profile.weekend), color: accent, label: t.weekend },
      ],
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
    const forecastColor = "var(--info-color, #039be5)";
    const verified = h.verification || [];
    const fc = h.forecast || [];
    let forecastChart;
    const past = h.past || [];
    const pvFc = h.pv_forecast || [];
    const pvColor = "#fbc02d";
    const batteryColor = "var(--success-color, #43a047)";
    if (!fc.length && !verified.length && !past.length) {
      forecastChart = `<div class="muted">${esc(t.noForecast)}</div>`;
    } else {
      const fMin = now - 24 * 3600e3;
      const fMax = now + 48 * 3600e3;
      const fTicks = [];
      const d = new Date(fMin);
      d.setHours(d.getHours() < 12 ? 12 : 24, 0, 0, 0);
      for (; d.getTime() < fMax; d.setHours(d.getHours() + 12)) {
        const label = d.getHours() === 0 ? d.toLocaleDateString(lang, { weekday: "short" }) : "12:00";
        fTicks.push([d.getTime(), label]);
      }
      const slot = 3600e3;  // verification/forecast points are at most an hour apart
      forecastChart = this._chart(
        "forecast",
        [
          { points: past.map(([ts, house]) => [ts, house]), color: primary, label: t.houseMeasured },
          { points: verified.map(([ts, , predicted]) => [ts, predicted]), color: secondary, dashed: true, label: t.predicted },
          { points: fc.map(([ts, power]) => [ts, power]), color: forecastColor, label: t.houseExpected },
          ...(h.has_pv || pvFc.length
            ? [
                { points: past.map(([ts, , , pv]) => [ts, pv]), color: pvColor, label: t.pvMeasured },
                { points: pvFc, color: pvColor, dashed: true, label: t.pvExpected },
              ]
            : []),
          ...(h.has_battery
            ? [{ points: past.map(([ts, , , , battery]) => [ts, battery]), color: batteryColor, label: t.batteryLine }]
            : []),
          ...(h.has_excluded
            ? [{ points: past.map(([ts, , excluded]) => [ts, excluded || null]), color: excludedColor, label: t.excludedLine }]
            : []),
        ],
        fMin,
        fMax,
        fTicks,
        2 * 3600e3,
        [[now, t.now]],
        (v) => new Date(v).toLocaleString(lang, { weekday: "short", hour: "2-digit", minute: "2-digit" }),
      );
      this._charts.forecast.gapLimit = slot;
    }
    const buckets = Object.values(h.accuracy?.consumption?.lead_times || {});
    const acc = buckets.find((b) => b.samples);
    const accText = acc
      ? t.accuracy.replace("{mae}", this._power(acc.mae)).replace("{mape}", acc.mape ?? "–")
      : t.notVerified;
    const item = (color, label) => `<span><i style="background:${color}"></i>${esc(label)}</span>`;
    const forecastLegend = `<div class="legend" style="flex-wrap:wrap">${[
      item(primary, t.houseMeasured),
      item(secondary, t.predicted),
      item(forecastColor, t.houseExpected),
      h.has_pv || pvFc.length ? item(pvColor, `${t.pvMeasured} / ${t.pvExpected}`) : "",
      h.has_battery ? item(batteryColor, t.batteryLine) : "",
      h.has_excluded ? item(excludedColor, t.excludedLine) : "",
    ].join("")}</div>`;

    const info = t.daysOfData.replace("{days}", Math.round(h.days_covered)) + (h.imported ? ` · ${t.imported}` : "");
    return `<div class="card"><h2>${esc(t.consumption)} · ${esc(info)}</h2><div class="charts">
      <div class="chart wide"><h3>${esc(t.flowTitle)}</h3>${forecastChart}${forecastLegend}
        <div class="muted">${esc(accText)}</div></div>
      <div class="chart"><h3>${esc(t.last7)}</h3>${week}${weekLegend}</div>
      <div class="chart"><h3>${esc(t.avgDay)}</h3>${avg}
        <div class="legend"><span><i style="background:${primary}"></i>${esc(t.weekday)}</span>
        <span><i style="background:${accent}"></i>${esc(t.weekend)}</span></div></div>
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

  _decisions(s, t) {
    const items = s.decisions.length
      ? `<ul>${s.decisions.map((d) => `<li><time>${this._time(d.time)}</time><span>${esc(d.message)}</span></li>`).join("")}</ul>`
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
      body = [
        this._flows(s, t),
        this._consumption(t),
        this._batteries(s, t),
        this._phases(s, t),
        this._planning(s, t),
        this._accuracy(t),
        this._decisions(s, t),
      ].join("");
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
    this._bindCharts();
    this._showHover();
  }
}

customElements.define("homebatteryassist-panel", HomeBatteryAssistPanel);
