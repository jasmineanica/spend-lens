from __future__ import annotations

import time
from datetime import date
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from . import svgcharts
from .analytics import analyze
from .config import APP_DIR
from .reconcile import reconcile
from .schemas import Dataset

_TEMPLATES = APP_DIR / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _bucket_chart(by_bucket: dict) -> str:
    return svgcharts.donut(list(by_bucket.items()), "Spend by bucket")


def _category_chart(by_category: list[dict]) -> str:
    return svgcharts.hbar([(c["category"], c["amount"]) for c in by_category], "Top categories")


def _trend_chart(monthly: list[dict]) -> str:
    return svgcharts.line([(m["month"], m["total"]) for m in monthly], "Monthly spend")


def _fmt_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} seconds"
    minutes, secs = divmod(seconds, 60)
    return f"{int(minutes)} min {secs:.0f} sec"


# Placeholder swapped for the real elapsed time after rendering but before the
# (fast) PDF serialization, so the report can state its own build time.
_GEN_TOKEN = "__GEN_SECS__"


# Above this many months, per-month charts are skipped (tables kept) to keep the
# PDF fast and light; the overview trend chart still shows the full time series.
_MAX_CHART_MONTHS = 12


def generate_pdf(dataset: Dataset, month: Optional[str] = None) -> bytes:
    t0 = time.monotonic()
    dataset = reconcile(dataset)  # reconcile ONCE, then reuse for every month
    overall = analyze(dataset, None, reconcile_first=False)
    months = overall["months"]

    if len(months) <= 1:
        # Single-month report (or empty): keep the compact one-page layout.
        result = analyze(dataset, month, reconcile_first=False) if month else overall
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
        months_data = [analyze(dataset, m, reconcile_first=False) for m in months]
        show_charts = len(months) <= _MAX_CHART_MONTHS
        charts_by_month = {
            md["month"]: {
                "bucket": _bucket_chart(md["by_bucket"]),
                "category": _category_chart(md["by_category"]),
            }
            for md in months_data
        } if show_charts else {}
        grand_total = round(sum(md["summary"]["total_spend"] for md in months_data), 2)
        ctx = {
            "multi": True,
            "overall": overall,
            "months_data": months_data,
            "charts_by_month": charts_by_month,
            "charts_omitted": not show_charts,
            "trend_chart": _trend_chart(overall["monthly"]),
            "grand_total": grand_total,
            "avg_month": round(grand_total / len(months), 2),
        }

    html = _env.get_template("report.html").render(
        generated_on=date.today().isoformat(), gen_time=_GEN_TOKEN, **ctx,
    )
    html = html.replace(_GEN_TOKEN, _fmt_duration(time.monotonic() - t0))
    return HTML(string=html, base_url=str(_TEMPLATES)).write_pdf()
