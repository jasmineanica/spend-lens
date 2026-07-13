from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

TxnType = Literal["expense", "refund"]
TxnSource = Literal["chase", "venmo", "manual", "demo"]
InvestmentSource = Literal["wealthfront", "fidelity", "demo"]
InvestmentKind = Literal["deposit", "buy", "sell"]


class Transaction(BaseModel):
    date: str = Field(description="ISO date, YYYY-MM-DD")
    source: TxnSource = "manual"
    txn_type: TxnType = "expense"
    merchant: str
    description: str = ""
    amount: float = Field(description="Positive for spend, negative for a refund")
    category: str = "Uncategorized"
    bucket: str = "Uncategorized"


class InvestmentEvent(BaseModel):
    date: str
    source: InvestmentSource = "wealthfront"
    kind: InvestmentKind = "deposit"
    symbol: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    amount: float


class Dataset(BaseModel):
    transactions: list[Transaction] = Field(default_factory=list)
    investments: list[InvestmentEvent] = Field(default_factory=list)


class QueryRequest(BaseModel):
    dataset: Dataset
    q: str
    month: Optional[str] = None


class AnalyzeRequest(BaseModel):
    dataset: Dataset
    month: Optional[str] = Field(default=None, description="YYYY-MM; defaults to latest")


class EmailRequest(BaseModel):
    text: str
