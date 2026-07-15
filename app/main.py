from __future__ import annotations

import io
import json

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import analytics, demo
from .config import APP_DIR, get_settings
from .parse.csv_import import parse_csv
from .parse.email_text import parse_email_text
from .parse.eml_import import _MAX_MBOX_MESSAGES, _split_mbox, parse_eml, parse_mbox
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


@app.post("/api/parse/upload")
async def api_parse_upload(file: UploadFile = File(...)) -> Dataset:
    """Dispatch an uploaded file by type: .mbox / .eml -> email parser, else CSV."""
    raw = await file.read()
    name = (file.filename or "").lower()
    ctype = (file.content_type or "").lower()
    if name.endswith(".mbox") or ctype == "application/mbox":
        return parse_mbox(raw)
    if name.endswith(".eml") or ctype.startswith("message/"):
        return parse_eml(raw)
    return parse_csv(file.filename or "upload.csv", raw.decode("utf-8", errors="replace"))


@app.post("/api/parse/mbox-stream")
async def api_parse_mbox_stream(file: UploadFile = File(...)) -> StreamingResponse:
    """Parse a (potentially large) mbox, streaming NDJSON progress as it goes.

    Emits {"type":"progress","processed","total"} lines then a final
    {"type":"result","dataset":...}. Nothing is stored — the dataset is streamed
    to the browser and discarded server-side."""
    raw = await file.read()
    messages = _split_mbox(raw)[:_MAX_MBOX_MESSAGES]
    total = len(messages)

    def gen():
        txns, inv = [], []
        yield json.dumps({"type": "progress", "processed": 0, "total": total}) + "\n"
        for i, msg in enumerate(messages, 1):
            ds = parse_eml(msg)
            txns.extend(t.model_dump() for t in ds.transactions)
            inv.extend(e.model_dump() for e in ds.investments)
            if i % 50 == 0 or i == total:
                yield json.dumps({"type": "progress", "processed": i, "total": total}) + "\n"
        yield json.dumps({"type": "result",
                          "dataset": {"transactions": txns, "investments": inv}}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


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
