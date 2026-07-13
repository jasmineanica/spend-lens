from __future__ import annotations

from fastapi.testclient import TestClient

from app import analytics, demo
from app.categorize import categorize
from app.main import app
from app.parse.csv_import import parse_csv, parse_fidelity_csv, parse_transactions_csv
from app.parse.email_text import parse_email_text
from app.report import generate_pdf

client = TestClient(app)


# --- categorizer (rules) ---
def test_rules_categorize():
    assert categorize("Starbucks #123")[0] == "Coffee"
    assert categorize("Uber Eats")[0] == "Dining Out"
    assert categorize("Uber trip 7pm")[0] == "Transportation"
    assert categorize("Safeway")[0] == "Groceries"
    assert categorize("BetterHelp Therapy")[0] == "Therapy / Counseling"
    cat, bucket = categorize("Zzzxyz Unknown Merchant")
    assert cat == "Uncategorized" and bucket == "Uncategorized"


def test_bucket_mapping():
    assert categorize("Blue Bottle Coffee")[1] == "Wants"
    assert categorize("PG&E")[1] == "Needs"


# --- demo + analytics ---
def test_demo_and_analyze():
    ds = demo.generate()
    assert len(ds.transactions) > 30
    assert all(t.category != "" for t in ds.transactions)
    r = analytics.analyze(ds)
    assert r["month"] in r["months"]
    assert r["summary"]["total_spend"] > 0
    assert set(r["by_bucket"]) >= {"Needs", "Wants", "Savings"}
    assert r["budget"]["runway_months"] is not None
    assert r["investments"]["total_deposited"] > 0


def test_query_coffee():
    ds = demo.generate()
    res = analytics.query(ds, "coffee")
    assert res["count"] > 0
    assert res["matched_total"] > 0
    assert "Coffee" in res["matched_categories"]


# --- CSV parsers ---
def test_parse_transactions_csv():
    csv = (
        "Date,Payee / Description,Category,Amount,Bucket\n"
        "2026-07-01,Trader Joe's,,54.20,\n"
        "2026-07-02,Rent,Rent / Mortgage,2650,\n"
        "Totals,,,=SUM(D2:D999),\n"
    )
    txns = parse_transactions_csv(csv)
    assert len(txns) == 2
    assert txns[0].category == "Groceries"          # inferred
    assert txns[1].category == "Rent / Mortgage"    # given


def test_parse_fidelity_csv():
    csv = (
        "Run Date,Action,Symbol,Quantity,Price ($),Amount ($)\n"
        "07/06/2026,YOU BOUGHT,VTI,2,275.00,-550.00\n"
        "07/07/2026,YOU SOLD,SCHD,5,28.00,140.00\n"
    )
    events = parse_fidelity_csv(csv)
    assert [e.kind for e in events] == ["buy", "sell"]
    assert events[0].symbol == "VTI" and events[0].amount == 550.0
    ds = parse_csv("fidelity_history.csv", csv)
    assert len(ds.investments) == 2 and not ds.transactions


# --- email parsers ---
def test_parse_chase_email():
    ds = parse_email_text("You made a $12.34 transaction with STARBUCKS STORE 123 on Jul 3, 2026.")
    assert len(ds.transactions) == 1
    t = ds.transactions[0]
    assert t.amount == 12.34 and t.category == "Coffee" and t.date == "2026-07-03"


def test_parse_venmo_and_investment_email():
    ds = parse_email_text("You paid Jordan $32.00 for dinner")
    assert ds.transactions[0].amount == 32.0 and ds.transactions[0].source == "venmo"
    ds2 = parse_email_text("Your deposit of $500.00 was received. You bought 2 shares of VTI at $275.00.")
    kinds = sorted(e.kind for e in ds2.investments)
    assert kinds == ["buy", "deposit"]


# --- report ---
def test_generate_pdf_bytes():
    ds = demo.generate()
    pdf = generate_pdf(ds)
    assert isinstance(pdf, bytes) and pdf[:4] == b"%PDF"


# --- endpoints ---
def test_endpoints_roundtrip():
    ds = client.get("/api/demo").json()
    assert ds["transactions"]

    r = client.post("/api/analyze", json={"dataset": ds, "month": None})
    assert r.status_code == 200 and r.json()["summary"]["txn_count"] > 0

    q = client.post("/api/query", json={"dataset": ds, "q": "coffee", "month": None})
    assert q.json()["count"] > 0

    rep = client.post("/api/report", json={"dataset": ds, "month": None})
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF"
    assert rep.headers["content-type"] == "application/pdf"

    email = client.post("/api/parse/email",
                        json={"text": "You made a $5.00 transaction with PHILZ COFFEE"})
    assert email.json()["transactions"][0]["category"] == "Coffee"
