# Spend Lens 🌿

A **stateless** personal-spending analyzer. Load transactions (a demo dataset, a CSV
export, or a pasted bank/Venmo/Fidelity notification email), see where your money goes
across categories and Needs/Wants/Savings buckets, ask questions like *"how much did I
spend on coffee?"*, and export a monthly PDF report.

**Your data is never stored.** Everything lives in your browser tab and is analyzed
in-memory on the server (no database, no disk writes, no logging of financial data).
Close or refresh the tab and it's gone.

## How it works

- **FastAPI** backend with pure, stateless endpoints (`/api/demo`, `/api/parse/*`,
  `/api/analyze`, `/api/query`, `/api/report`) — each takes a payload, computes, and
  keeps nothing.
- The **browser** holds the working dataset in `sessionStorage`; charts render with
  **Chart.js**.
- **Categorization** = an ordered merchant→category rules map (`app/data/merchant_rules.yml`)
  over a taxonomy of Needs/Wants/Savings categories (`app/data/categories.yml`). An optional
  **Claude** fallback categorizes unknown merchants — enabled only when you run locally.
- **PDF reports** are rendered with matplotlib → Jinja2 → WeasyPrint and streamed back in
  memory (never saved).

## Run locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://localhost:8000
```

### Optional: enable the Claude categorization fallback (local only)

```bash
cp .env.example .env
# set ENABLE_LLM=true and ANTHROPIC_API_KEY=... in .env
```

The public deploy ships with `ENABLE_LLM=false` and no key, so no data leaves the server.

## Test

```bash
pip install pytest httpx
pytest
```

## Deploy (Render, Docker)

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, select the repo. `render.yaml` provisions a free Docker
   web service with `ENABLE_LLM=false`.
3. Render builds the `Dockerfile` (which installs the Pango/Cairo libs WeasyPrint needs)
   and gives you a `https://spend-lens.onrender.com` URL.

## Input formats

- **Transactions CSV** — columns (fuzzy, case-insensitive): date; payee/description/merchant;
  amount; category (optional). Matches the common budgeting-spreadsheet layout.
- **Fidelity CSV** — a standard account History export (Run Date, Action, Symbol, Quantity,
  Price, Amount).
- **Pasted email** — Chase purchase alerts, Venmo payments, Wealthfront deposits, and Fidelity
  trade confirmations (plain text or HTML).
- **`.eml` file** — upload a saved email; its subject, body, and date header are extracted and
  run through the same email parser.
