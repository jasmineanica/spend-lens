from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app import analytics, demo
from app.categorize import categorize
from app.main import app
from app.parse.csv_import import parse_csv, parse_fidelity_csv, parse_transactions_csv
from app.parse.email_text import parse_email_text
from app.parse.eml_import import eml_to_text, parse_eml, parse_mbox
from app.reconcile import reconcile
from app.report import generate_pdf
from app.schemas import Dataset, Transaction

SAMPLE_EML = (
    b"From: alerts@chase.com\r\n"
    b"To: jasmine@example.com\r\n"
    b"Subject: Transaction alert\r\n"
    b"Date: Fri, 3 Jul 2026 10:00:00 -0700\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"You made a $12.34 transaction with STARBUCKS STORE 123.\r\n"
)

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


# --- .eml upload ---
def test_eml_to_text_and_parse():
    text = eml_to_text(SAMPLE_EML)
    assert "STARBUCKS" in text and "Jul 3, 2026" in text  # body + date header
    ds = parse_eml(SAMPLE_EML)
    assert len(ds.transactions) == 1
    t = ds.transactions[0]
    assert t.amount == 12.34 and t.category == "Coffee" and t.date == "2026-07-03"


def _mbox_msg(sender, subject, date_str, body):
    return (
        f"From {sender} {date_str}\r\n"
        f"From: {sender}\r\nSubject: {subject}\r\nDate: {date_str}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n{body}\r\n"
    ).encode()


def test_parse_mbox_multiple_messages():
    mbox = (
        _mbox_msg("alerts@chase.com", "alert", "Fri, 3 Jul 2026 10:00:00 -0700",
                  "You made a $12.34 transaction with STARBUCKS.")
        + b"\n"
        + _mbox_msg("alerts@chase.com", "alert", "Sat, 4 Jul 2026 09:00:00 -0700",
                    "You made a $54.20 transaction with SAFEWAY.")
        + b"\n"
        + _mbox_msg("news@example.com", "Newsletter", "Sun, 5 Jul 2026 09:00:00 -0700",
                    "Nothing financial here.")
    )
    ds = parse_mbox(mbox)
    assert len(ds.transactions) == 2  # newsletter yields nothing
    cats = {t.category for t in ds.transactions}
    dates = {t.date for t in ds.transactions}
    assert cats == {"Coffee", "Groceries"}
    assert dates == {"2026-07-03", "2026-07-04"}  # per-message dates preserved


def test_mbox_stream_endpoint():
    mbox = (
        _mbox_msg("alerts@chase.com", "a", "Fri, 3 Jul 2026 10:00:00 -0700",
                  "You made a $4.50 transaction with PHILZ COFFEE.")
        + b"\n"
        + _mbox_msg("alerts@chase.com", "a", "Sat, 4 Jul 2026 10:00:00 -0700",
                    "You made a $54.20 transaction with SAFEWAY.")
    )
    r = client.post("/api/parse/mbox-stream",
                    files={"file": ("takeout.mbox", mbox, "application/mbox")})
    assert r.status_code == 200
    lines = [json.loads(ln) for ln in r.text.splitlines() if ln.strip()]
    assert any(ln["type"] == "progress" for ln in lines)
    assert lines[-1]["type"] == "result"
    assert len(lines[-1]["dataset"]["transactions"]) == 2


def test_upload_endpoint_dispatch():
    # .eml routes to the email parser
    eml = client.post("/api/parse/upload",
                      files={"file": ("alert.eml", SAMPLE_EML, "message/rfc822")})
    assert eml.json()["transactions"][0]["category"] == "Coffee"
    # .csv still routes to the CSV parser
    csv = "Date,Description,Amount\n2026-07-01,Trader Joe's,54.20\n"
    up = client.post("/api/parse/upload",
                     files={"file": ("txns.csv", csv, "text/csv")})
    assert up.json()["transactions"][0]["category"] == "Groceries"


# --- reimbursement / split reconciliation ---
def test_parse_incoming_venmo_reimbursement():
    ds = parse_email_text("Miguel paid you $50.00")
    assert len(ds.transactions) == 1
    t = ds.transactions[0]
    assert t.txn_type == "reimbursement" and t.amount == -50.0
    assert t.merchant == "Venmo - Miguel" and t.source == "venmo"


def test_reconcile_nets_split_into_category():
    ds = Dataset(transactions=[
        Transaction(date="2026-07-01", source="chase", merchant="Ticketmaster",
                    amount=100.0, category="Entertainment", bucket="Wants"),
        Transaction(date="2026-07-02", source="venmo", txn_type="reimbursement",
                    merchant="Venmo - Miguel", amount=-50.0,
                    category="Reimbursement", bucket="Uncategorized"),
    ])
    reimb = [t for t in reconcile(ds).transactions if t.txn_type == "reimbursement"][0]
    assert reimb.category == "Entertainment" and reimb.bucket == "Wants"

    r = analytics.analyze(ds, "2026-07")
    ent = next(c for c in r["by_category"] if c["category"] == "Entertainment")
    assert ent["amount"] == 50.0          # $100 - $50 nets to $50
    assert r["by_bucket"]["Wants"] == 50.0
    assert r["summary"]["total_spend"] == 50.0


def test_reconcile_unmatched_still_reduces_total():
    ds = Dataset(transactions=[
        Transaction(date="2026-07-01", source="chase", merchant="Rent",
                    amount=30.0, category="Rent / Mortgage", bucket="Needs"),
        Transaction(date="2026-07-02", source="venmo", txn_type="reimbursement",
                    merchant="Venmo - Sam", amount=-50.0,
                    category="Reimbursement", bucket="Uncategorized"),
    ])
    # $50 reimbursement can't match a $30 charge; stays 'Reimbursement' but still nets.
    reimb = [t for t in reconcile(ds).transactions if t.txn_type == "reimbursement"][0]
    assert reimb.category == "Reimbursement"
    assert analytics.analyze(ds, "2026-07")["summary"]["total_spend"] == -20.0


# --- report ---
def test_generate_pdf_bytes():
    ds = demo.generate()  # spans ~3 months -> multi-month report path
    pdf = generate_pdf(ds)
    assert isinstance(pdf, bytes) and pdf[:4] == b"%PDF"


def test_single_month_report():
    ds = Dataset(transactions=[
        Transaction(date="2026-07-10", source="chase", merchant="Starbucks",
                    amount=5.0, category="Coffee", bucket="Wants"),
    ])
    pdf = generate_pdf(ds, "2026-07")
    assert pdf[:4] == b"%PDF"


def test_multi_month_report():
    ds = Dataset(transactions=[
        Transaction(date="2026-05-10", source="chase", merchant="Safeway",
                    amount=40.0, category="Groceries", bucket="Needs"),
        Transaction(date="2026-06-10", source="chase", merchant="Starbucks",
                    amount=5.0, category="Coffee", bucket="Wants"),
        Transaction(date="2026-07-10", source="chase", merchant="Uber",
                    amount=15.0, category="Transportation", bucket="Needs"),
    ])
    pdf = generate_pdf(ds)
    assert pdf[:4] == b"%PDF" and len(pdf) > 1000


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
