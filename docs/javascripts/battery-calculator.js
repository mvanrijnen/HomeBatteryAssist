// Battery calculator (docs page battery-calculator): does a home battery pay
// on a dynamic contract without net metering (the Netherlands from 2027)?
// Runs in the reader's browser only; nothing is sent anywhere.
(function () {
  const TEXT = {
    en: {
      params: "Parameters",
      market: "Market prices (EPEX, excl. VAT)",
      b1: ["When charging from the grid", "B1"],
      b2: ["When discharging", "B2: using or exporting"],
      bz: ["At a solar surplus", "Bz: when you would export your solar"],
      supplier: "Supplier and tax",
      oin: ["Purchase fee", "o_in, incl. VAT"],
      ouit: ["Sales fee", "o_uit, taken off the export price"],
      eb: ["Energy tax", "EB, incl. VAT"],
      btw: ["VAT", ""],
      battery: "Battery",
      eta: ["Round-trip efficiency", "η"],
      cost: ["Purchase price", ""],
      cycles: ["Number of cycles", "realistic, not the specification"],
      kwh: ["Usable capacity", ""],
      marge: ["Margin wanted", "what you want to keep at least"],
      reset: "Default values (example: Essent dynamic 2027)",
      result: "Result per kWh",
      resultInfo: "“Find the break-even” looks for the lowest market price B2 (in whole cents) at which that case pays, margin included, and sets B2 to it.",
      scen: ["Grid charge → use yourself", "Grid charge → export", "Store solar → use yourself"],
      needs: ["Needed: spread all-in ≥ {v}", "Needed: market price B2 ≥ {v}", "Needed: buy price all-in when used ≥ {v}"],
      inclMargin: "(incl. margin {v})",
      pays: "pays", paysNot: "does not pay",
      find: "Find the break-even",
      found: "Pays from B2 = {need} (excl. VAT). B2 is now {b2}: buy price all-in {allIn}, market spread with {from} {spread} (excl. VAT).",
      mid: "Intermediate results",
      rows: [
        "Wear per kWh in or out (S)", "Buy price all-in when charging", "Buy price all-in when discharging",
        "Export price when discharging", "Export price at a solar surplus", "Cost of 1 kWh from the battery (grid)",
        "Cost of 1 kWh from the battery (solar)",
      ],
      table: "Per market price when charging",
      tableInfo: "Charging from the grid at this market price (excl. VAT, like B1). The spread and the market price later include your margin. The row of your B1 is marked.",
      cols: ["Market price charging (excl. VAT)", "Buy price charging (all-in)", "Cost of 1 kWh from the battery", "Spread needed (use yourself)", "Min. market price later (export, excl. VAT)"],
      formulas: "Formulas",
      formulaText: `Buy (all-in)      P_in  = B × (1 + VAT) + o_in + EB
Export (2027)     P_uit = B − o_uit
Wear              S     = purchase ÷ cycles ÷ kWh ÷ 2

Cost of a kWh from the battery, grid   K_net = P_in(B1) ÷ η + 2·S
Cost of a kWh from the battery, solar  K_zon = P_uit(Bz) ÷ η + 2·S

Grid charge → use yourself    profit = P_in(B2)  − K_net
Grid charge → export          profit = P_uit(B2) − K_net
Store solar → use yourself    profit = P_in(B2)  − K_zon

Pays when profit > margin wanted`,
      decimal: ".",
    },
    nl: {
      params: "Parameters",
      market: "Beursprijzen (EPEX, excl. btw)",
      b1: ["Bij laden uit het net", "B1"],
      b2: ["Bij ontladen", "B2: gebruiken of terugleveren"],
      bz: ["Bij zonneoverschot", "Bz: als je zon zou terugleveren"],
      supplier: "Leverancier en belasting",
      oin: ["Inkoopvergoeding", "o_in, incl. btw"],
      ouit: ["Verkoopvergoeding", "o_uit, gaat af van teruglevering"],
      eb: ["Energiebelasting", "EB, incl. btw"],
      btw: ["Btw", ""],
      battery: "Accu",
      eta: ["Rendement heen en terug", "η"],
      cost: ["Aanschafprijs", ""],
      cycles: ["Aantal cycli", "realistisch, niet de specificatie"],
      kwh: ["Bruikbare capaciteit", ""],
      marge: ["Gewenste marge", "wat je minimaal wilt overhouden"],
      reset: "Standaardwaarden (voorbeeld: Essent dynamisch 2027)",
      result: "Uitkomst per kWh",
      resultInfo: "“Bepaal omslagpunt” zoekt de laagste beursprijs B2 (op hele centen) waarbij dat scenario loont, inclusief je marge, en zet B2 daarop.",
      scen: ["Net laden → zelf gebruiken", "Net laden → terugleveren", "Zon opslaan → zelf gebruiken"],
      needs: ["Nodig: spread all-in ≥ {v}", "Nodig: beursprijs B2 ≥ {v}", "Nodig: inkoop all-in bij gebruik ≥ {v}"],
      inclMargin: "(incl. marge {v})",
      pays: "loont", paysNot: "loont niet",
      find: "Bepaal omslagpunt",
      found: "Loont vanaf B2 = {need} (excl. btw). B2 staat nu op {b2}: inkoop all-in {allIn}, beursspread met {from} {spread} (excl. btw).",
      mid: "Tussenresultaten",
      rows: [
        "Slijtage per kWh erin of eruit (S)", "Inkoopprijs all-in bij laden", "Inkoopprijs all-in bij ontladen",
        "Verkoopprijs bij ontladen", "Verkoopprijs bij zonneoverschot", "Kosten 1 kWh uit accu (netstroom)",
        "Kosten 1 kWh uit accu (zonnestroom)",
      ],
      table: "Per beursprijs bij laden",
      tableInfo: "Laden uit het net bij deze beursprijs (excl. btw, zoals B1). De spread en de beursprijs later zijn inclusief je gewenste marge. De regel van jouw B1 is gemarkeerd.",
      cols: ["Beursprijs laden (excl. btw)", "Inkoopprijs laden (all-in)", "Kosten 1 kWh uit accu", "Spread nodig (zelf gebruiken)", "Min. beursprijs later (terugleveren, excl. btw)"],
      formulas: "Formules",
      formulaText: `Inkoop (all-in)     P_in  = B × (1 + btw) + o_in + EB
Verkoop (2027)      P_uit = B − o_uit
Slijtage            S     = aanschaf ÷ cycli ÷ kWh ÷ 2

Kosten kWh uit accu, netstroom    K_net = P_in(B1) ÷ η + 2·S
Kosten kWh uit accu, zonnestroom  K_zon = P_uit(Bz) ÷ η + 2·S

Net laden → zelf gebruiken    winst = P_in(B2)  − K_net
Net laden → terugleveren      winst = P_uit(B2) − K_net
Zon opslaan → zelf gebruiken  winst = P_in(B2)  − K_zon

Loont als winst > gewenste marge`,
      decimal: ",",
    },
  };
  const FIELDS = [
    ["market", [["b1", 0.25, 0.01, "€"], ["b2", 0.4, 0.01, "€"], ["bz", 0.05, 0.01, "€"]]],
    ["supplier", [["oin", 0.0149, 0.0001, "€"], ["ouit", 0.02165, 0.0001, "€"], ["eb", 0.1065, 0.0001, "€"], ["btw", 21, 1, "%"]]],
    ["battery", [["eta", 85, 1, "%"], ["cost", 1100, 50, "€"], ["cycles", 3000, 100, ""], ["kwh", 4.1, 0.1, "kWh"], ["marge", 0.05, 0.01, "€"]]],
  ];
  const IDS = FIELDS.flatMap(([, list]) => list.map(([id]) => id));

  function start() {
    const root = document.getElementById("battery-calculator");
    if (!root) return;
    const t = (document.documentElement.lang || "").startsWith("nl") ? TEXT.nl : TEXT.en;
    const fmt = (v, d) => v.toFixed(d).replace(".", t.decimal);
    const euro = (v) => (v < 0 ? "−€ " : "€ ") + fmt(Math.abs(v), 4);
    const euro2 = (v) => (v < 0 ? "−€ " : "€ ") + fmt(Math.abs(v), 2);
    const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, k) => values[k]);
    const field = ([id, value, step, unit]) => {
      const [label, hint] = t[id];
      const pre = unit === "€" ? `<span>€</span>` : "";
      const post = unit && unit !== "€" ? `<span>${unit}</span>` : "";
      return `<label class="bc-field">${label}${hint ? `<small>${hint}</small>` : ""}
        <span class="bc-input">${pre}<input id="bc-${id}" type="number" step="${step}" value="${value}">${post}</span></label>`;
    };
    root.innerHTML = `
      <div class="bc-box"><h3>${t.params}</h3><div class="bc-params">${FIELDS.map(([group, list]) =>
        `<div class="bc-group"><h4>${t[group]}</h4>${list.map(field).join("")}</div>`).join("")}</div>
        <button type="button" class="bc-button" id="bc-reset">${t.reset}</button></div>
      <div class="bc-box"><h3>${t.result}</h3><div class="bc-cards" id="bc-cards"></div><p class="bc-muted">${t.resultInfo}</p></div>
      <div class="bc-box"><h3>${t.mid}</h3><div id="bc-rows"></div></div>
      <div class="bc-box"><h3>${t.table}</h3><p class="bc-muted">${t.tableInfo}</p><div class="bc-tablewrap"><table id="bc-table"></table></div></div>
      <div class="bc-box"><h3>${t.formulas}</h3><pre class="bc-formula">${t.formulaText}</pre></div>`;

    const num = (id) => parseFloat(document.getElementById(`bc-${id}`).value) || 0;
    let told = null; // the break-even told on a card: { i, text }
    let breakEven = [0, 0, 0];

    function calc() {
      const p = Object.fromEntries(IDS.map((id) => [id, num(id)]));
      const vat = p.btw / 100, eta = p.eta / 100 || 1;
      const S = p.cycles && p.kwh ? p.cost / p.cycles / p.kwh / 2 : 0;
      const pin = (b) => b * (1 + vat) + p.oin + p.eb;
      const puit = (b) => b - p.ouit;
      const in1 = pin(p.b1), in2 = pin(p.b2), out2 = puit(p.b2), outz = puit(p.bz);
      const kNet = in1 / eta + 2 * S, kZon = outz / eta + 2 * S;
      const profits = [in2 - kNet, out2 - kNet, in2 - kZon];
      const needs = [in1 * (1 / eta - 1) + 2 * S + p.marge, kNet + p.ouit + p.marge, kZon + p.marge];
      document.getElementById("bc-cards").innerHTML = profits.map((v, i) =>
        `<div class="bc-card"><strong>${t.scen[i]}</strong><span class="bc-value">${euro(v)}</span>
          <span class="bc-pill ${v > p.marge ? "bc-yes" : "bc-no"}">${v > p.marge ? t.pays : t.paysNot}</span>
          <span class="bc-muted">${fill(t.needs[i], { v: euro(needs[i]) })}${p.marge ? ` ${fill(t.inclMargin, { v: euro2(p.marge) })}` : ""}</span>
          <button type="button" class="bc-button" data-be="${i}">${t.find}</button>
          ${told && told.i === i ? `<span class="bc-told">${told.text}</span>` : ""}</div>`).join("");
      const toB = (allIn) => (allIn - p.oin - p.eb) / (1 + vat);
      breakEven = [toB(kNet + p.marge), kNet + p.ouit + p.marge, toB(kZon + p.marge)];
      const mid = [S, in1, in2, out2, outz, kNet, kZon];
      document.getElementById("bc-rows").innerHTML = mid.map((v, i) =>
        `<div class="bc-row"><span>${t.rows[i]}</span><b>${euro(v)}</b></div>`).join("");
      // Market prices 0.00 to 1.00 by 5 cents, plus B1 itself (marked).
      const prices = Array.from({ length: 21 }, (_, i) => Math.round(i * 5) / 100);
      if (!prices.some((b) => Math.abs(b - p.b1) < 1e-9)) prices.push(p.b1);
      prices.sort((x, y) => x - y);
      let rows = "";
      for (const b of prices) {
        const a = pin(b);
        const k = a / eta + 2 * S;
        const mine = Math.abs(b - p.b1) < 1e-9;
        rows += `<tr class="${mine ? "bc-hl" : ""}"><td>${mine ? "B1 " : ""}${euro2(b)}</td><td>${euro(a)}</td>
          <td>${euro(k)}</td><td>${euro(k - a + p.marge)}</td><td>${euro(k + p.ouit + p.marge)}</td></tr>`;
      }
      document.getElementById("bc-table").innerHTML =
        `<thead><tr>${t.cols.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>${rows}</tbody>`;
    }

    // Per case: the lowest B2 (whole cent up) at which it pays, margin
    // included; B2 is set to it and the card says so.
    document.getElementById("bc-cards").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-be]");
      if (!button) return;
      const i = Number(button.dataset.be);
      const need = breakEven[i];
      const b2 = Math.floor(need * 100 + 1e-9) / 100 + 0.01;
      const allIn = b2 * (1 + num("btw") / 100) + num("oin") + num("eb");
      const from = i === 2 ? ["Bz", num("bz")] : ["B1", num("b1")];
      document.getElementById("bc-b2").value = b2.toFixed(2);
      told = { i, text: fill(t.found, { need: euro(need), b2: euro2(b2), allIn: euro2(allIn), from: from[0], spread: euro(b2 - from[1]) }) };
      calc();
    });
    const defaults = Object.fromEntries(IDS.map((id) => [id, document.getElementById(`bc-${id}`).value]));
    IDS.forEach((id) => document.getElementById(`bc-${id}`).addEventListener("input", () => {
      told = null;
      calc();
    }));
    document.getElementById("bc-reset").addEventListener("click", () => {
      IDS.forEach((id) => (document.getElementById(`bc-${id}`).value = defaults[id]));
      told = null;
      calc();
    });
    calc();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
