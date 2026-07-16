from __future__ import annotations

from typing import Optional

import pandas as pd

from .categorize import BUDGET, TAXONOMY
from .reconcile import reconcile
from .schemas import Dataset

BUCKET_ORDER = ["Needs", "Wants", "Savings", "Uncategorized"]


def _txn_frame(dataset: Dataset) -> pd.DataFrame:
    rows = [t.model_dump() for t in dataset.transactions]
    df = pd.DataFrame(rows, columns=[
        "date", "source", "txn_type", "merchant", "description",
        "amount", "category", "bucket",
    ])
    if not df.empty:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
        df["month"] = df["date"].str.slice(0, 7)
    return df


def _round(v: float) -> float:
    return round(float(v), 2)


def analyze(dataset: Dataset, month: Optional[str] = None, reconcile_first: bool = True) -> dict:
    if reconcile_first:
        dataset = reconcile(dataset)
    df = _txn_frame(dataset)

    if df.empty:
        return {
            "months": [], "month": None,
            "summary": {"total_spend": 0.0, "txn_count": 0, "top_category": None},
            "by_category": [], "by_bucket": {}, "monthly": [],
            "budget": {}, "investments": _investments(dataset),
        }

    months = sorted(df["month"].unique())
    month = month if month in months else months[-1]
    cur = df[df["month"] == month]

    # Net spend per category (refunds are negative and net out).
    by_cat = (
        cur.groupby("category")["amount"].sum().sort_values(ascending=False)
    )
    by_category = [
        {"category": c, "bucket": _bucket_of(c), "amount": _round(v)}
        for c, v in by_cat.items()
    ]

    by_bucket_series = cur.groupby("bucket")["amount"].sum()
    by_bucket = {b: _round(by_bucket_series.get(b, 0.0)) for b in BUCKET_ORDER}

    monthly = [
        {"month": m, "total": _round(df[df["month"] == m]["amount"].sum())}
        for m in months
    ]

    total_spend = _round(cur["amount"].sum())
    top_category = by_category[0]["category"] if by_category else None

    return {
        "months": months,
        "month": month,
        "summary": {
            "total_spend": total_spend,
            "txn_count": int(len(cur)),
            "top_category": top_category,
        },
        "by_category": by_category,
        "by_bucket": by_bucket,
        "monthly": monthly,
        "budget": _budget(by_bucket, total_spend),
        "investments": _investments(dataset),
    }


def _bucket_of(category: str) -> str:
    from .categorize import bucket_for
    return bucket_for(category)


def _budget(by_bucket: dict, monthly_burn: float) -> dict:
    """Runway model mirroring ~/Documents/Summary.csv."""
    ef = float(BUDGET["emergency_fund"])
    needs = float(by_bucket.get("Needs", 0.0))
    reserve = BUDGET["reserve_months"] * needs
    usable_cushion = max(0.0, ef - reserve)
    allowable_draw = usable_cushion / BUDGET["draw_months"] if BUDGET["draw_months"] else 0.0
    safe_cap = needs + allowable_draw

    targets = {b: _round(safe_cap * s) for b, s in BUDGET["split"].items()}
    actual = {b: float(by_bucket.get(b, 0.0)) for b in BUDGET["split"]}
    return {
        "emergency_fund": _round(ef),
        "monthly_burn": _round(monthly_burn),
        "runway_months": _round(ef / monthly_burn) if monthly_burn > 0 else None,
        "reserve": _round(reserve),
        "usable_cushion": _round(usable_cushion),
        "safe_monthly_cap": _round(safe_cap),
        "targets": targets,
        "actual": {b: _round(v) for b, v in actual.items()},
        "diff": {b: _round(targets[b] - actual[b]) for b in targets},
    }


def _investments(dataset: Dataset) -> dict:
    events = [e.model_dump() for e in dataset.investments]
    if not events:
        return {"total_deposited": 0.0, "total_invested": 0.0, "total_sold": 0.0,
                "trade_count": 0, "events": []}
    df = pd.DataFrame(events)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    deposited = df.loc[df["kind"] == "deposit", "amount"].sum()
    invested = df.loc[df["kind"] == "buy", "amount"].sum()
    sold = df.loc[df["kind"] == "sell", "amount"].sum()
    trades = int((df["kind"] != "deposit").sum())
    events_sorted = df.sort_values("date").to_dict(orient="records")
    return {
        "total_deposited": _round(deposited),
        "total_invested": _round(invested),
        "total_sold": _round(sold),
        "trade_count": trades,
        "events": events_sorted,
    }


def analyze_all(dataset: Dataset) -> dict:
    """Overall analysis plus a per-month breakdown, reconciled once. Lightweight
    JSON for the browser to render/print — no server-side PDF work."""
    ds = reconcile(dataset)
    overall = analyze(ds, None, reconcile_first=False)
    months = [analyze(ds, m, reconcile_first=False) for m in overall["months"]]
    return {"overall": overall, "months": months}


def query(dataset: Dataset, q: str, month: Optional[str] = None) -> dict:
    dataset = reconcile(dataset)
    df = _txn_frame(dataset)
    q_norm = (q or "").strip().lower()
    if df.empty or not q_norm:
        return {"q": q, "matched_total": 0.0, "count": 0, "rows": [], "matched_categories": []}

    if month and month in set(df["month"]):
        df = df[df["month"] == month]

    matched_categories = [c for c in TAXONOMY if q_norm in c.lower()]
    cat_mask = df["category"].isin(matched_categories)
    text_mask = (
        df["merchant"].str.lower().str.contains(q_norm, na=False, regex=False)
        | df["description"].str.lower().str.contains(q_norm, na=False, regex=False)
    )
    hits = df[cat_mask | text_mask].sort_values("date", ascending=False)

    rows = hits.drop(columns=["month"]).to_dict(orient="records")
    return {
        "q": q,
        "matched_total": _round(hits["amount"].sum()),
        "count": int(len(hits)),
        "rows": rows,
        "matched_categories": matched_categories,
    }
