from __future__ import annotations

import io
import math

import pandas as pd
from dateutil import parser as dateparser

from ..categorize import bucket_for, categorize
from ..schemas import Dataset, InvestmentEvent, Transaction


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _pick(cols: list[str], *needles: str) -> str | None:
    for c in cols:
        for n in needles:
            if n in c:
                return c
    return None


def _iso(value) -> str | None:
    try:
        return dateparser.parse(str(value)).date().isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def _cell(value) -> str:
    """Stringify a cell, treating pandas NaN/None as empty."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _num(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace("$", "").replace(",", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        f = float(s)
        return None if math.isnan(f) else f
    except ValueError:
        return None


def _is_fidelity(cols: list[str]) -> bool:
    return _pick(cols, "run date", "action") is not None and _pick(cols, "symbol") is not None


def parse_transactions_csv(text: str) -> list[Transaction]:
    """Parse a generic / ~/Documents-style transactions CSV.

    Recognized columns (case-insensitive, fuzzy): date; payee/description/merchant;
    amount; category (optional). Rows without a usable date+amount are skipped
    (handles the spreadsheet's formula/total rows)."""
    df = _norm_cols(pd.read_csv(io.StringIO(text)))
    cols = list(df.columns)
    c_date = _pick(cols, "date")
    c_merchant = _pick(cols, "payee", "description", "merchant", "name")
    c_amount = _pick(cols, "amount")
    c_category = _pick(cols, "category")
    if not (c_date and c_amount):
        return []

    out: list[Transaction] = []
    for _, row in df.iterrows():
        iso = _iso(row.get(c_date))
        amount = _num(row.get(c_amount))
        if iso is None or amount is None:
            continue
        merchant = _cell(row.get(c_merchant)) if c_merchant else ""
        if not merchant:
            continue
        given = _cell(row.get(c_category)) if c_category else ""
        if given:
            category, bucket = given, bucket_for(given)
        else:
            category, bucket = categorize(merchant)
        out.append(Transaction(
            date=iso, source="manual",
            txn_type="refund" if amount < 0 else "expense",
            merchant=merchant, amount=round(amount, 2),
            category=category, bucket=bucket,
        ))
    return out


def parse_fidelity_csv(text: str) -> list[InvestmentEvent]:
    """Parse a Fidelity account History CSV export."""
    # Fidelity exports have preamble lines; find the header row.
    lines = text.splitlines()
    header_idx = next(
        (i for i, ln in enumerate(lines) if "run date" in ln.lower() and "action" in ln.lower()),
        0,
    )
    df = _norm_cols(pd.read_csv(io.StringIO("\n".join(lines[header_idx:]))))
    cols = list(df.columns)
    c_date = _pick(cols, "run date", "date")
    c_action = _pick(cols, "action")
    c_symbol = _pick(cols, "symbol")
    c_qty = _pick(cols, "quantity")
    c_price = _pick(cols, "price")
    c_amount = _pick(cols, "amount")

    out: list[InvestmentEvent] = []
    for _, row in df.iterrows():
        iso = _iso(row.get(c_date)) if c_date else None
        if iso is None:
            continue
        action = str(row.get(c_action, "")).lower() if c_action else ""
        if "bought" in action or "buy" in action:
            kind = "buy"
        elif "sold" in action or "sell" in action:
            kind = "sell"
        elif "deposit" in action or "contribution" in action:
            kind = "deposit"
        else:
            continue
        amount = _num(row.get(c_amount)) if c_amount else None
        out.append(InvestmentEvent(
            date=iso, source="fidelity", kind=kind,
            symbol=(_cell(row.get(c_symbol)) or None) if c_symbol else None,
            quantity=_num(row.get(c_qty)) if c_qty else None,
            price=_num(row.get(c_price)) if c_price else None,
            amount=abs(amount) if amount is not None else 0.0,
        ))
    return out


def parse_csv(filename: str, text: str) -> Dataset:
    """Dispatch by header: Fidelity history -> investments, else transactions."""
    try:
        cols = [str(c).strip().lower() for c in pd.read_csv(io.StringIO(text), nrows=0).columns]
    except Exception:
        cols = []
    if _is_fidelity(cols) or "fidelity" in filename.lower():
        return Dataset(transactions=[], investments=parse_fidelity_csv(text))
    return Dataset(transactions=parse_transactions_csv(text), investments=[])
