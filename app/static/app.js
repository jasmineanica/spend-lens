"use strict";

const KEY = "spendlens.dataset";
const charts = {};
let dataset = load();
let currentMonth = null;

function load() {
  try { return JSON.parse(sessionStorage.getItem(KEY)) || blank(); }
  catch { return blank(); }
}
function blank() { return { transactions: [], investments: [] }; }
function save() { sessionStorage.setItem(KEY, JSON.stringify(dataset)); }
function hasData() { return dataset.transactions.length || dataset.investments.length; }

function setStatus(msg) { document.getElementById("status").textContent = msg || ""; }

function mergeData(ds, { replace = false } = {}) {
  if (replace) dataset = blank();
  dataset.transactions.push(...(ds.transactions || []));
  dataset.investments.push(...(ds.investments || []));
  save();
  currentMonth = null; // let analyze pick the latest
  refresh();
}

async function refresh() {
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

function populateMonths(months, selected) {
  const sel = document.getElementById("month-select");
  sel.innerHTML = "";
  months.forEach((m) => {
    const o = document.createElement("option");
    o.value = m; o.textContent = m; if (m === selected) o.selected = true;
    sel.appendChild(o);
  });
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
  mergeData(await r.json(), { replace: true });
};

document.getElementById("file-csv").onchange = async (e) => {
  const file = e.target.files[0]; if (!file) return;
  const isEmail = /\.(eml|mbox)$/i.test(file.name);
  setStatus(isEmail ? "Parsing email file…" : "Parsing CSV…");
  const fd = new FormData(); fd.append("file", file);
  const r = await fetch("/api/parse/upload", { method: "POST", body: fd });
  const ds = await r.json();
  const n = (ds.transactions?.length || 0) + (ds.investments?.length || 0);
  if (!n) { setStatus(isEmail ? "No transactions found in that email file." : "No rows recognized in that CSV."); return; }
  mergeData(ds);
  e.target.value = "";
};

document.getElementById("btn-paste").onclick = () => {
  const p = document.getElementById("paste-panel"); p.hidden = !p.hidden;
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
  document.getElementById("paste-panel").hidden = true;
  mergeData(ds);
};

document.getElementById("month-select").onchange = (e) => {
  currentMonth = e.target.value; refresh();
};

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
  setStatus("Building PDF…");
  const r = await fetch("/api/report", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset, month: currentMonth }) });
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `spend-report-${currentMonth || "latest"}.pdf`;
  a.click(); URL.revokeObjectURL(url);
  setStatus("Report downloaded.");
};

document.getElementById("btn-clear").onclick = () => {
  dataset = blank(); currentMonth = null; sessionStorage.removeItem(KEY);
  document.getElementById("q-result").textContent = "";
  refresh();
};

refresh();
