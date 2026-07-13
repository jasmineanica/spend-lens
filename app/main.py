from __future__ import annotations

import io

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import analytics, demo
from .config import APP_DIR, get_settings
from .parse.csv_import import parse_csv
from .parse.email_text import parse_email_text
from .report import generate_pdf
from .schemas import AnalyzeRequest, Dataset, EmailRequest, QueryRequest

app = FastAPI(title="Spend Lens", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "enable_llm": get_settings().enable_llm},
    )


@app.get("/api/demo")
def api_demo() -> Dataset:
    return demo.generate()


@app.post("/api/parse/csv")
async def api_parse_csv(file: UploadFile = File(...)) -> Dataset:
    raw = (await file.read()).decode("utf-8", errors="replace")
    return parse_csv(file.filename or "upload.csv", raw)


@app.post("/api/parse/email")
def api_parse_email(req: EmailRequest) -> Dataset:
    return parse_email_text(req.text)


@app.post("/api/analyze")
def api_analyze(req: AnalyzeRequest) -> dict:
    return analytics.analyze(req.dataset, req.month)


@app.post("/api/query")
def api_query(req: QueryRequest) -> dict:
    return analytics.query(req.dataset, req.q, req.month)


@app.post("/api/report")
def api_report(req: AnalyzeRequest) -> StreamingResponse:
    pdf = generate_pdf(req.dataset, req.month)  # bytes, never written to disk
    filename = f"spend-report-{req.month or 'latest'}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
