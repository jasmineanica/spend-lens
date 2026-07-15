from __future__ import annotations

from datetime import date

from .schemas import Dataset, Transaction

# How far a reimbursement can sit from the purchase it offsets.
_DAYS_BEFORE = 3    # reimbursement may arrive up to this many days *before* the charge posts
_DAYS_AFTER = 45    # ...and up to this many days after
_EPS = 0.01


def _d(iso: str) -> date:
    return date.fromisoformat(iso[:10])


def reconcile(dataset: Dataset) -> Dataset:
    """Net incoming Venmo reimbursements against the purchases they split.

    For each reimbursement (a negative Venmo transaction), find the best matching
    expense — same-ish date, and where the amount you paid is at least what you
    were paid back — and re-tag the reimbursement with that purchase's category
    and bucket. That way the reimbursement nets out of the *same* category:
    a $100 dinner + a $50 "Miguel paid you" reads as $50 of Dining Out.

    Unmatched reimbursements keep category 'Reimbursement' but still reduce the
    total (their amount is negative). Returns a new Dataset; inputs are untouched.
    """
    txns: list[Transaction] = [t.model_copy(deep=True) for t in dataset.transactions]
    expenses = [t for t in txns if t.txn_type == "expense" and t.amount > 0]
    reimbursements = [t for t in txns if t.txn_type == "reimbursement"]

    remaining = {id(e): e.amount for e in expenses}

    for r in sorted(reimbursements, key=lambda t: t.date):
        value = -r.amount  # positive magnitude of the reimbursement
        r_date = _d(r.date)

        best = None  # (sort_key, expense)
        for e in expenses:
            if remaining[id(e)] + _EPS < value:
                continue  # can't be reimbursed more than you paid
            delta = (r_date - _d(e.date)).days
            if not (-_DAYS_BEFORE <= delta <= _DAYS_AFTER):
                continue
            # prefer purchases on/before the reimbursement, then closest in time,
            # then the tightest fit (least leftover).
            key = (0 if delta >= 0 else 1, abs(delta), remaining[id(e)] - value)
            if best is None or key < best[0]:
                best = (key, e)

        if best is not None:
            e = best[1]
            r.category = e.category
            r.bucket = e.bucket
            remaining[id(e)] -= value

    return Dataset(transactions=txns, investments=dataset.investments)
