from __future__ import annotations

import base64
import io
from datetime import date
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # headless; no display, no temp files
import matplotlib.pyplot as plt  # noqa: E402
from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402
from weasyprint import HTML  # noqa: E402

from .analytics import analyze  # noqa: E402
from .config import APP_DIR  # noqa: E402
from .schemas import Dataset  # noqa: E402

_GREEN = ["#5f7a4f", "#889d7b", "#b6c7a6", "#3d5430", "#cdd8c1", "#7a8f66"]
_TEMPLATES = APP_DIR / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _fig_to_data_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _bucket_chart(by_bucket: dict) -> str:
    items = [(k, v) for k, v in by_bucket.items() if v and v > 0]
    fig, ax = plt.subplots(figsize=(3.4, 3.4))
    if items:
        labels, values = zip(*items)
        ax.pie(values, labels=labels, autopct="%1.0f%%", colors=_GREEN,
               wedgeprops={"width": 0.42})
    ax.set_title("Spend by bucket")
    return _fig_to_data_uri(fig)


def _category_chart(by_category: list[dict]) -> str:
    top = [c for c in by_category if c["amount"] > 0][:8][::-1]
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    if top:
        ax.barh([c["category"] for c in top], [c["amount"] for c in top], color=_GREEN[0])
    ax.set_title("Top categories")
    ax.set_xlabel("$")
    return _fig_to_data_uri(fig)


def _trend_chart(monthly: list[dict]) -> str:
    fig, ax = plt.subplots(figsize=(5.2, 2.6))
    if monthly:
        ax.plot([m["month"] for m in monthly], [m["total"] for m in monthly],
                marker="o", color=_GREEN[3])
    ax.set_title("Monthly spend")
    ax.set_ylabel("$")
    fig.autofmt_xdate(rotation=30)
    return _fig_to_data_uri(fig)


def generate_pdf(dataset: Dataset, month: Optional[str] = None) -> bytes:
    overall = analyze(dataset, None)
    months = overall["months"]

    if len(months) <= 1:
        # Single-month report (or empty): keep the compact one-page layout.
        result = analyze(dataset, month) if month else overall
        ctx = {
            "multi": False,
            "r": result,
            "charts": {
                "bucket": _bucket_chart(result["by_bucket"]),
                "category": _category_chart(result["by_category"]),
                "trend": _trend_chart(result["monthly"]),
            },
        }
    else:
        # Multi-month: overview + a per-month breakdown.
        months_data = [analyze(dataset, m) for m in months]
        charts_by_month = {
            md["month"]: {
                "bucket": _bucket_chart(md["by_bucket"]),
                "category": _category_chart(md["by_category"]),
            }
            for md in months_data
        }
        grand_total = round(sum(md["summary"]["total_spend"] for md in months_data), 2)
        ctx = {
            "multi": True,
            "overall": overall,
            "months_data": months_data,
            "charts_by_month": charts_by_month,
            "trend_chart": _trend_chart(overall["monthly"]),
            "grand_total": grand_total,
            "avg_month": round(grand_total / len(months), 2),
        }

    html = _env.get_template("report.html").render(
        generated_on=date.today().isoformat(), **ctx,
    )
    return HTML(string=html, base_url=str(_TEMPLATES)).write_pdf()
