from __future__ import annotations

import re

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from ..categorize import categorize
from ..schemas import Dataset, InvestmentEvent, Transaction

_AMOUNT = r"\$?([\d,]+\.\d{2})"


def _money(s: str) -> float:
    return float(s.replace(",", ""))


def _find_date(text: str) -> str:
    m = re.search(r"(?:on\s+)?([A-Z][a-z]{2,8}\.?\s+\d{1,2},?\s+\d{4})", text)
    if m:
        try:
            return dateparser.parse(m.group(1)).date().isoformat()
        except (ValueError, OverflowError):
            pass
    from datetime import date
    return date.today().isoformat()


def _to_plaintext(text: str) -> str:
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def parse_email_text(raw: str) -> Dataset:
    """Best-effort parse of pasted Chase / Venmo / Wealthfront / Fidelity
    notification text (plain or HTML). Handles one or several pasted messages."""
    text = _to_plaintext(raw)
    txns: list[Transaction] = []
    investments: list[InvestmentEvent] = []

    # Fidelity trade confirmation: "You bought 2 shares of VTI at $275.00"
    for m in re.finditer(
        r"you (bought|sold)\s+([\d,.]+)\s+shares?\s+of\s+([A-Z]{1,5})\s+at\s+" + _AMOUNT,
        text, re.IGNORECASE,
    ):
        qty, price = _money(m.group(2)), _money(m.group(4))
        investments.append(InvestmentEvent(
            date=_find_date(text), source="fidelity",
            kind="buy" if m.group(1).lower() == "bought" else "sell",
            symbol=m.group(3).upper(), quantity=qty, price=price,
            amount=round(qty * price, 2)))

    # Wealthfront deposit: "deposit of $500.00" / "transfer of $500.00"
    for m in re.finditer(r"(?:deposit|transfer|contribution) of\s+" + _AMOUNT, text, re.IGNORECASE):
        investments.append(InvestmentEvent(
            date=_find_date(text), source="wealthfront", kind="deposit",
            amount=_money(m.group(1))))

    # Venmo outgoing: "You paid Jordan $32.00"
    for m in re.finditer(r"you paid\s+(.+?)\s+" + _AMOUNT, text, re.IGNORECASE):
        merchant = f"Venmo - {m.group(1).strip()}"
        cat, bucket = categorize(merchant)
        txns.append(Transaction(
            date=_find_date(text), source="venmo", merchant=merchant,
            amount=_money(m.group(2)), category=cat, bucket=bucket))

    # Venmo incoming: "Miguel paid you $50.00" -> a reimbursement (negative spend).
    # Reconciled against a matching purchase at analysis time (see reconcile.py).
    for m in re.finditer(r"([A-Za-z][\w .'\-]{1,40}?)\s+paid you\s+" + _AMOUNT, text, re.IGNORECASE):
        payer = m.group(1).strip()
        txns.append(Transaction(
            date=_find_date(text), source="venmo", txn_type="reimbursement",
            merchant=f"Venmo - {payer}", description="Reimbursement",
            amount=-_money(m.group(2)), category="Reimbursement", bucket="Uncategorized"))

    # Chase alert: "You made a $12.34 transaction with STARBUCKS" and variants.
    chase_patterns = [
        r"transaction of\s+" + _AMOUNT + r"\s+(?:at|with)\s+(.+?)(?:\s+on|\.|$)",
        r"made a\s+" + _AMOUNT + r"\s+transaction with\s+(.+?)(?:\s+on|\.|$)",
        r"charge(?:d)?(?:\s+of)?\s+" + _AMOUNT + r"\s+(?:at|to)\s+(.+?)(?:\s+on|\.|$)",
    ]
    for pat in chase_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            merchant = m.group(2).strip(" .")
            cat, bucket = categorize(merchant)
            txns.append(Transaction(
                date=_find_date(text), source="chase", merchant=merchant,
                amount=_money(m.group(1)), category=cat, bucket=bucket))

    return Dataset(transactions=txns, investments=investments)
