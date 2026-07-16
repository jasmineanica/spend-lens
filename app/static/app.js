"use strict";

// State is in-memory only, so a page refresh wipes everything. `stash` keeps a
// copy of the user's imported data for this session so they can Clear (e.g. to
// peek at the demo) and later Reload their own data.
const charts = {};
let dataset = blank();
let stash = null;
let viewingDemo = false;
let currentMonth = null;
let months = [];

function blank() { return { transactions: [], investments: [] }; }
function clone(x) { return JSON.parse(JSON.stringify(x)); }
function has(ds) { return !!(ds && (ds.transactions.length || ds.investments.length)); }
function hasData() { return has(dataset); }
function scrollDash() {
  if (hasData()) document.getElementById("dash").scrollIntoView({ behavior: "smooth", block: "start" });
}
function setStatus(msg) { document.getElementById("status").textContent = msg || ""; }

async function loadDemo(ds) {
  dataset = ds;            // demo replaces the current view (kept separate from imports)
  viewingDemo = true;
  currentMonth = null;
  await refresh();
  scrollDash();
}

async function importData(ds) {
  if (viewingDemo) { dataset = blank(); viewingDemo = false; }  // don't mix demo with imports
  dataset.transactions.push(...(ds.transactions || []));
  dataset.investments.push(...(ds.investments || []));
  if (!stash) stash = blank();
  stash.transactions.push(...(ds.transactions || []));
  stash.investments.push(...(ds.investments || []));
  currentMonth = null;
  await refresh();
  scrollDash();
}

function updateStashUI() {
  document.getElementById("stash-actions").hidden = !has(stash);
}

async function refresh() {
  updateStashUI();
  document.getElementById("empty").hidden = hasData();
  document.getElementById("dash").hidden = !hasData();
  if (!hasData()) { setStatus(""); return; }

  const res = await fetch("/api/analyze", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset, month: currentMonth }),
  });
  const r = await res.json();
  currentMonth = r.month;
  setStatus(`${dataset.transactions.length} transactions loaded`);
  populateMonths(r.months, r.month);
  renderCards(r);
  renderCharts(r);
  renderBudget(r.budget);
  renderInvest(r.investments);
}

function populateMonths(monthList, selected) {
  months = monthList || [];
  const sel = document.getElementById("month-select");
  sel.innerHTML = "";
  months.forEach((m) => {
    const o = document.createElement("option");
    o.value = m; o.textContent = m; if (m === selected) o.selected = true;
    sel.appendChild(o);
  });
  updateMonthNav();
}

function updateMonthNav() {
  const i = months.indexOf(currentMonth);
  document.getElementById("btn-prev-month").disabled = i <= 0;
  document.getElementById("btn-next-month").disabled = i < 0 || i >= months.length - 1;
}

function stepMonth(delta) {
  const j = months.indexOf(currentMonth) + delta;
  if (j < 0 || j >= months.length) return;
  currentMonth = months[j];
  refresh();
}

function money(v) { return "$" + Number(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

function renderCards(r) {
  document.getElementById("c-total").textContent = money(r.summary.total_spend);
  document.getElementById("c-count").textContent = r.summary.txn_count;
  document.getElementById("c-top").textContent = r.summary.top_category || "—";
  document.getElementById("c-runway").textContent =
    r.budget.runway_months ? r.budget.runway_months.toFixed(1) + " mo" : "—";
}

const GREEN = ["#5f7a4f", "#889d7b", "#b6c7a6", "#3d5430", "#cdd8c1", "#7a8f66", "#a4b58f"];

function draw(id, config) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), config);
}

function renderCharts(r) {
  const buckets = Object.entries(r.by_bucket).filter(([, v]) => v > 0);
  draw("chart-bucket", {
    type: "doughnut",
    data: { labels: buckets.map((b) => b[0]),
      datasets: [{ data: buckets.map((b) => b[1]), backgroundColor: GREEN }] },
    options: { plugins: { title: { display: true, text: "Spend by bucket" } } },
  });

  const cats = r.by_category.filter((c) => c.amount > 0).slice(0, 8);
  draw("chart-category", {
    type: "bar",
    data: { labels: cats.map((c) => c.category),
      datasets: [{ data: cats.map((c) => c.amount), backgroundColor: GREEN[0] }] },
    options: { indexAxis: "y", plugins: { legend: { display: false },
      title: { display: true, text: "Top categories" } } },
  });

  draw("chart-trend", {
    type: "line",
    data: { labels: r.monthly.map((m) => m.month),
      datasets: [{ data: r.monthly.map((m) => m.total), borderColor: GREEN[3],
        backgroundColor: "rgba(95,122,79,.15)", fill: true, tension: 0.25 }] },
    options: { plugins: { legend: { display: false },
      title: { display: true, text: "Monthly spend" } } },
  });
}

function renderBudget(b) {
  const rows = ["Needs", "Wants", "Savings"].map((k) => `
    <tr><td>${k}</td><td class="num">${money(b.targets[k])}</td>
    <td class="num">${money(b.actual[k])}</td><td class="num">${money(b.diff[k])}</td></tr>`).join("");
  document.getElementById("budget-table").innerHTML =
    `<tr><th>Bucket</th><th class="num">Target</th><th class="num">Actual</th><th class="num">Diff</th></tr>${rows}
     <tr><td colspan="4" style="color:#6b7860;font-size:.85rem">
     Emergency fund ${money(b.emergency_fund)} · runway ${b.runway_months ? b.runway_months.toFixed(1) + " mo" : "—"} ·
     safe cap ${money(b.safe_monthly_cap)}</td></tr>`;
}

function renderInvest(inv) {
  document.getElementById("invest-summary").innerHTML = `
    <p><strong>Deposited:</strong> ${money(inv.total_deposited)}</p>
    <p><strong>Invested (buys):</strong> ${money(inv.total_invested)}</p>
    <p><strong>Trades:</strong> ${inv.trade_count}</p>`;
}

// --- printable report (client-side; browser "Save as PDF") ---
const CHART_GREEN = ["#5f7a4f", "#889d7b", "#b6c7a6", "#3d5430", "#cdd8c1", "#7a8f66", "#a4b58f"];
function esc(s) { return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function svgWrap(title, w, h, body) {
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Helvetica,Arial,sans-serif">` +
    `<text x="0" y="14" font-size="12" font-weight="bold" fill="#3d5430">${esc(title)}</text>${body}</svg>`;
}
function donutSVG(pairs, title) {
  pairs = pairs.filter((p) => p[1] > 0);
  const total = pairs.reduce((a, p) => a + p[1], 0);
  const cx = 70, cy = 105, r = 52, sw = 24, circ = 2 * Math.PI * r;
  let off = 0, segs = "", leg = "", ly = 46;
  pairs.forEach((p, i) => {
    const seg = total ? circ * p[1] / total : 0;
    segs += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${CHART_GREEN[i % 7]}" stroke-width="${sw}" stroke-dasharray="${seg.toFixed(2)} ${(circ - seg).toFixed(2)}" stroke-dashoffset="${(-off).toFixed(2)}" transform="rotate(-90 ${cx} ${cy})"/>`;
    off += seg;
    leg += `<rect x="150" y="${ly - 9}" width="10" height="10" fill="${CHART_GREEN[i % 7]}"/><text x="166" y="${ly}" font-size="10">${esc(p[0])} ${(total ? p[1] / total * 100 : 0).toFixed(0)}%</text>`;
    ly += 18;
  });
  return svgWrap(title, 300, 210, pairs.length ? segs + leg : `<text x="${cx}" y="${cy}" font-size="10" text-anchor="middle">no data</text>`);
}
function hbarSVG(pairs, title) {
  pairs = pairs.filter((p) => p[1] > 0).slice(0, 8);
  const maxv = Math.max(1, ...pairs.map((p) => p[1])), bx = 118, bw = 200;
  let y = 34, rows = "";
  pairs.forEach((p) => {
    const w = bw * p[1] / maxv;
    rows += `<text x="0" y="${y + 11}" font-size="10">${esc(p[0].slice(0, 18))}</text><rect x="${bx}" y="${y}" width="${w.toFixed(1)}" height="14" rx="2" fill="#5f7a4f"/><text x="${(bx + w + 5).toFixed(1)}" y="${y + 11}" font-size="9" fill="#4a553f">$${Math.round(p[1]).toLocaleString()}</text>`;
    y += 22;
  });
  return svgWrap(title, 360, Math.max(60, y + 6), rows || `<text x="0" y="40" font-size="10">no data</text>`);
}
function lineSVG(points, title) {
  const w = 360, h = 150, pad = 26, maxv = Math.max(1, ...points.map((p) => p[1])), n = points.length;
  const px = (i) => pad + (w - 2 * pad) * (n > 1 ? i / (n - 1) : 0.5);
  const py = (v) => h - pad - (h - 2 * pad) * (v / maxv);
  let dots = "", labels = "";
  points.forEach((p, i) => {
    dots += `<circle cx="${px(i).toFixed(1)}" cy="${py(p[1]).toFixed(1)}" r="2.5" fill="#3d5430"/>`;
    labels += `<text x="${px(i).toFixed(1)}" y="${h - 6}" font-size="8" text-anchor="middle">${esc(String(p[0]).slice(2))}</text>`;
  });
  let poly = "";
  if (n > 1) poly = `<polyline points="${points.map((p, i) => `${px(i).toFixed(1)},${py(p[1]).toFixed(1)}`).join(" ")}" fill="none" stroke="#3d5430" stroke-width="2"/>`;
  return svgWrap(title, w, h, (poly + dots + labels) || `<text x="0" y="40" font-size="10">no data</text>`);
}

function prCards(items) {
  return `<div class="pr-cards">${items.map(([l, v]) => `<div class="pr-card"><div class="l">${esc(l)}</div><div class="v">${esc(v)}</div></div>`).join("")}</div>`;
}
function prCatTable(byCat) {
  return `<table><tr><th>Category</th><th>Bucket</th><th class="num">Amount</th></tr>` +
    byCat.map((c) => `<tr><td>${esc(c.category)}</td><td>${esc(c.bucket)}</td><td class="num">${money(c.amount)}</td></tr>`).join("") + `</table>`;
}
function runwayStr(b) { return b.runway_months ? b.runway_months.toFixed(1) + " mo" : "—"; }

function buildPrintReport(all) {
  const o = all.overall, md = all.months, multi = md.length > 1;
  const today = new Date().toLocaleDateString();
  let html = `<h1>🌿 Spend Lens report</h1>`;
  if (multi) {
    const grand = md.reduce((a, m) => a + m.summary.total_spend, 0);
    html += `<p class="pr-sub">${md.length} months (${o.months[0]} – ${o.months[o.months.length - 1]}) · generated ${today} · data never stored</p>`;
    html += prCards([["Total spend", money(grand)], ["Months", md.length], ["Avg / month", money(grand / md.length)], ["Top category", o.summary.top_category || "—"]]);
    html += `<div class="pr-trend">${lineSVG(o.monthly.map((m) => [m.month, m.total]), "Monthly spend")}</div>`;
    html += `<h2>Monthly totals</h2><table><tr><th>Month</th><th class="num">Total spend</th></tr>` +
      o.monthly.map((m) => `<tr><td>${m.month}</td><td class="num">${money(m.total)}</td></tr>`).join("") + `</table>`;
    md.forEach((m) => {
      html += `<div class="pr-month"><h2>${m.month}</h2>` +
        prCards([["Spend", money(m.summary.total_spend)], ["Transactions", m.summary.txn_count], ["Top category", m.summary.top_category || "—"], ["Runway", runwayStr(m.budget)]]) +
        `<div class="pr-charts"><div>${donutSVG(Object.entries(m.by_bucket), "Spend by bucket")}</div><div>${hbarSVG(m.by_category.map((c) => [c.category, c.amount]), "Top categories")}</div></div>` +
        prCatTable(m.by_category) + `</div>`;
    });
  } else {
    const r = md[0] || o;
    html += `<p class="pr-sub">Month ${r.month || "—"} · generated ${today} · data never stored</p>`;
    html += prCards([["Total spend", money(r.summary.total_spend)], ["Transactions", r.summary.txn_count], ["Top category", r.summary.top_category || "—"], ["Runway", runwayStr(r.budget)]]);
    html += `<div class="pr-charts"><div>${donutSVG(Object.entries(r.by_bucket), "Spend by bucket")}</div><div>${hbarSVG(r.by_category.map((c) => [c.category, c.amount]), "Top categories")}</div></div>`;
    html += `<div class="pr-trend">${lineSVG(r.monthly.map((m) => [m.month, m.total]), "Monthly spend")}</div>`;
    html += `<h2>By category</h2>` + prCatTable(r.by_category);
    const b = r.budget;
    html += `<h2>Budget vs. actual &amp; runway</h2><table><tr><th>Bucket</th><th class="num">Target</th><th class="num">Actual</th><th class="num">Diff</th></tr>` +
      Object.keys(b.targets).map((k) => `<tr><td>${k}</td><td class="num">${money(b.targets[k])}</td><td class="num">${money(b.actual[k])}</td><td class="num">${money(b.diff[k])}</td></tr>`).join("") + `</table>`;
  }
  if (o.investments && o.investments.events.length) {
    const inv = o.investments;
    html += `<h2>Investments</h2><p class="pr-sub">Deposited ${money(inv.total_deposited)} · invested ${money(inv.total_invested)} · ${inv.trade_count} trades</p>`;
  }
  html += `<p class="pr-foot">Spend Lens · generated in your browser. Figures are computed from the data you loaded and are not stored anywhere.</p>`;
  document.getElementById("print-report").innerHTML = html;
}

function showReportStatus(txt, spin = true) {
  const rs = document.getElementById("report-status");
  document.getElementById("report-status-text").textContent = txt;
  rs.querySelector(".spinner").style.display = spin ? "" : "none";
  rs.hidden = false;
}
function hideReportStatus() { document.getElementById("report-status").hidden = true; }

// --- actions ---
document.getElementById("btn-start").onclick = () => {
  const landing = document.getElementById("landing");
  document.getElementById("app-view").hidden = false; // reveal beneath the overlay
  landing.classList.add("fade-out");                  // fade the splash out
  setTimeout(() => { landing.hidden = true; }, 450);  // remove after the transition
};

document.getElementById("btn-demo").onclick = async () => {
  setStatus("Loading demo data…");
  const r = await fetch("/api/demo");
  await loadDemo(await r.json());
};

document.getElementById("btn-reload").onclick = async () => {
  if (!has(stash)) return;
  dataset = clone(stash); viewingDemo = false; currentMonth = null;
  await refresh(); scrollDash();
};

document.getElementById("btn-clear-import").onclick = () => {
  stash = null;
  if (!viewingDemo) { dataset = blank(); currentMonth = null; }
  document.getElementById("q-result").textContent = "";
  refresh();
};

const progressWrap = document.getElementById("progress-wrap");
const progressFill = document.getElementById("progress-fill");
const progressLabel = document.getElementById("progress-label");

function showProgress(indeterminate, label) {
  progressWrap.hidden = false;
  progressWrap.classList.toggle("indeterminate", !!indeterminate);
  if (!indeterminate) progressFill.style.width = "0%";
  progressLabel.textContent = label || "";
}
function updateProgress(done, total, found) {
  progressWrap.classList.remove("indeterminate");
  const pct = total ? Math.round((done / total) * 100) : 0;
  progressFill.style.width = pct + "%";
  const mb = (n) => (n / 1048576).toFixed(1);
  const foundStr = found != null ? ` · ${found.toLocaleString()} transactions found` : "";
  progressLabel.textContent = total
    ? `Scanned ${mb(done)} / ${mb(total)} MB (${pct}%)${foundStr}`
    : `Parsing…${foundStr}`;
}
function hideProgress() {
  progressWrap.hidden = true;
  progressWrap.classList.remove("indeterminate");
  progressFill.style.width = "0%";
  progressLabel.textContent = "";
}

// Stream NDJSON progress from the server while a (possibly large) mbox is parsed.
async function parseMboxStreaming(file) {
  showProgress(true, "Reading file…");
  const fd = new FormData(); fd.append("file", file);
  const resp = await fetch("/api/parse/mbox-stream", { method: "POST", body: fd });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "", result = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, idx).trim(); buf = buf.slice(idx + 1);
      if (!line) continue;
      const msg = JSON.parse(line);
      if (msg.type === "progress") updateProgress(msg.processed, msg.total, msg.found);
      else if (msg.type === "result") result = msg.dataset;
    }
  }
  hideProgress();
  return result;
}

document.getElementById("file-csv").onchange = async (e) => {
  const file = e.target.files[0]; if (!file) return;
  const isMbox = /\.mbox$/i.test(file.name);
  const isEmail = /\.(eml|mbox)$/i.test(file.name);
  try {
    let ds;
    if (isMbox) {
      ds = await parseMboxStreaming(file);
    } else {
      showProgress(true, isEmail ? "Parsing email…" : "Parsing CSV…");
      const fd = new FormData(); fd.append("file", file);
      const r = await fetch("/api/parse/upload", { method: "POST", body: fd });
      ds = await r.json();
      hideProgress();
    }
    const n = (ds?.transactions?.length || 0) + (ds?.investments?.length || 0);
    if (!n) {
      setStatus(isEmail ? "No transactions found in that email file." : "No rows recognized in that CSV.");
    } else {
      await importData(ds);
    }
  } catch (err) {
    hideProgress();
    setStatus("Upload failed: " + err.message);
  }
  e.target.value = "";
};

document.getElementById("btn-paste-go").onclick = async () => {
  const text = document.getElementById("paste-text").value.trim();
  if (!text) return;
  setStatus("Parsing email…");
  const r = await fetch("/api/parse/email", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }) });
  const ds = await r.json();
  const n = (ds.transactions?.length || 0) + (ds.investments?.length || 0);
  if (!n) { setStatus("Couldn't find a transaction in that text."); return; }
  document.getElementById("paste-text").value = "";
  await importData(ds);
};

document.getElementById("month-select").onchange = (e) => {
  currentMonth = e.target.value; refresh();
};
document.getElementById("btn-prev-month").onclick = () => stepMonth(-1);
document.getElementById("btn-next-month").onclick = () => stepMonth(1);

document.getElementById("q-go").onclick = doQuery;
document.getElementById("q-input").addEventListener("keydown", (e) => { if (e.key === "Enter") doQuery(); });
async function doQuery() {
  const q = document.getElementById("q-input").value.trim();
  if (!q || !hasData()) return;
  const r = await fetch("/api/query", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset, q, month: currentMonth }) });
  const res = await r.json();
  document.getElementById("q-result").textContent =
    `${money(res.matched_total)} across ${res.count} transaction(s) in ${currentMonth}.`;
}

document.getElementById("btn-report").onclick = async () => {
  if (!hasData()) return;
  const btn = document.getElementById("btn-report");
  btn.disabled = true;
  showReportStatus("Preparing report…");
  try {
    const r = await fetch("/api/analyze-all", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset, month: null }) });
    if (!r.ok) { showReportStatus(`Report failed (${r.status}).`, false); return; }
    buildPrintReport(await r.json());
    hideReportStatus();
    // Browser renders the printable report and opens the native print / Save-as-PDF dialog.
    window.print();
  } catch (err) {
    showReportStatus("Report error: " + err.message, false);
  } finally {
    btn.disabled = false;
  }
};

document.getElementById("btn-clear").onclick = () => {
  dataset = blank(); viewingDemo = false; currentMonth = null;
  document.getElementById("q-result").textContent = "";
  refresh();  // stash is kept so "Reload my data" stays available
};

refresh();
