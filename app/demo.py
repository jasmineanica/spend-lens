from __future__ import annotations

import random
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from .categorize import categorize
from .schemas import Dataset, InvestmentEvent, Transaction

# (merchant, low, high, weight) — sampled to look like a real card feed.
_MERCHANTS = [
    ("Blue Bottle Coffee", 4.5, 7.5, 22),
    ("Starbucks", 4.0, 9.0, 14),
    ("Sweetgreen", 12.0, 18.0, 9),
    ("DoorDash", 18.0, 46.0, 10),
    ("Chipotle", 11.0, 16.0, 7),
    ("Trader Joe's", 25.0, 95.0, 8),
    ("Safeway", 20.0, 120.0, 6),
    ("Uber", 9.0, 34.0, 8),
    ("Lyft", 8.0, 28.0, 5),
    ("Shell Gas Station", 30.0, 62.0, 3),
    ("AMC Theatres", 16.0, 42.0, 2),
    ("Nordstrom", 45.0, 180.0, 2),
    ("Lululemon", 68.0, 128.0, 2),
    ("Equinox Gym", 210.0, 210.0, 1),
    ("BetterHelp Therapy", 90.0, 90.0, 1),
    ("Walgreens Pharmacy", 8.0, 45.0, 3),
    ("Sephora", 22.0, 90.0, 2),
    ("The Alembic Bar", 24.0, 70.0, 3),
    ("Amazon.com", 15.0, 140.0, 6),
    ("Target", 20.0, 110.0, 4),
]

# Recurring monthly bills (merchant, amount, day-of-month).
_RECURRING = [
    ("Greenview Apartments Rent", 2650.0, 1),
    ("PG&E", 84.0, 12),
    ("Comcast Xfinity Internet", 79.0, 15),
    ("Verizon Mobile", 65.0, 18),
    ("Netflix", 15.49, 5),
    ("Spotify", 11.99, 7),
    ("Equinox Gym", 210.0, 3),
]


def _mk(dt: date, merchant: str, amount: float, source: str = "chase",
        txn_type: str = "expense", description: str = "") -> Transaction:
    category, bucket = categorize(merchant, description)
    return Transaction(
        date=dt.isoformat(), source=source, txn_type=txn_type,
        merchant=merchant, description=description,
        amount=round(amount, 2), category=category, bucket=bucket,
    )


def generate(months: int = 3, seed: int = 7) -> Dataset:
    rng = random.Random(seed)
    today = date.today()
    start = (today - relativedelta(months=months - 1)).replace(day=1)

    weighted = [m for m in _MERCHANTS for _ in range(m[3])]
    txns: list[Transaction] = []
    investments: list[InvestmentEvent] = []

    cursor = start
    while cursor <= today:
        # Recurring bills on their day-of-month.
        for merchant, amount, dom in _RECURRING:
            if cursor.day == min(dom, 28):
                txns.append(_mk(cursor, merchant, amount))
        # 1–4 discretionary purchases per day.
        for _ in range(rng.randint(1, 4)):
            merchant, low, high, _w = rng.choice(weighted)
            txns.append(_mk(cursor, merchant, rng.uniform(low, high)))
        cursor += timedelta(days=1)

    # A couple of refunds (negative amounts).
    if txns:
        r = rng.choice([t for t in txns if t.category in ("Clothing", "Household goods")] or txns)
        txns.append(_mk(date.fromisoformat(r.date), r.merchant, -round(r.amount, 2),
                        txn_type="refund", description="Returned item"))

    # A Venmo split (dining) each month.
    m = start
    while m <= today:
        txns.append(_mk(m.replace(day=min(20, 28)), "Venmo - Dinner split", 32.0,
                        source="venmo", description="Group dinner"))
        m += relativedelta(months=1)

    # Wealthfront auto-deposit + a few Fidelity trades per month.
    m = start
    while m <= today:
        investments.append(InvestmentEvent(
            date=m.replace(day=2).isoformat(), source="wealthfront",
            kind="deposit", amount=500.0))
        for sym, qty, price in [("VTI", 2, 275.0), ("SCHD", 5, 28.0)]:
            investments.append(InvestmentEvent(
                date=m.replace(day=6).isoformat(), source="fidelity", kind="buy",
                symbol=sym, quantity=qty, price=price, amount=round(qty * price, 2)))
        m += relativedelta(months=1)

    txns.sort(key=lambda t: t.date)
    return Dataset(transactions=txns, investments=investments)
