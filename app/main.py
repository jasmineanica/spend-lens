from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import analytics, demo
from .config import APP_DIR, get_settings
from .parse.csv_import import parse_csv
from .parse.email_text import parse_email_text
from .parse.eml_import import _MAX_MBOX_MESSAGES, iter_mbox_messages, parse_eml, parse_mbox
from .report import generate_pdf
from .schemas import AnalyzeRequest, Dataset, EmailRequest, QueryRequest

app = FastAPI(title="Spend Lens", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


def _asset_version() -> str:
    """Hash the front-end assets so their ?v= query busts browser caches on
    every change (no more stale JS/CSS after a deploy)."""
    h = hashlib.sha1()
    for rel in ("static/app.js", "static/styles.css", "templates/dashboard.html"):
        try:
            h.update((APP_DIR / rel).read_bytes())
        except OSError:
            pass
    return h.hexdigest()[:8]


ASSET_VERSION = _asset_version()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "enable_llm": get_settings().enable_llm,
         "asset_version": ASSET_VERSION},
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
    # Copy the upload to our own temp file in chunks (bounded memory). We can't
    # read the UploadFile inside the generator below — FastAPI closes it once
    # this handler returns — so we own a temp file and delete it when done.
    tmp = tempfile.NamedTemporaryFile(prefix="spendlens_", suffix=".mbox", delete=False)
    size = 0
    try:
        while chunk := await file.read(1024 * 1024):
            tmp.write(chunk)
            size += len(chunk)
    finally:
        tmp.close()
    path = tmp.name

    def gen():
        txns, inv = [], []
        count = 0
        done = 0
        try:
            yield json.dumps({"type": "progress", "processed": 0, "total": size}) + "\n"
            with open(path, "rb") as f:
                for msg in iter_mbox_messages(f):
                    count += 1
                    done += len(msg)
                    if count > _MAX_MBOX_MESSAGES:
                        break
                    try:
                        ds = parse_eml(msg)
                        txns.extend(t.model_dump() for t in ds.transactions)
                        inv.extend(e.model_dump() for e in ds.investments)
                    except Exception:
                        pass  # skip a malformed message, keep going
                    if count % 200 == 0:
                        yield json.dumps({"type": "progress", "processed": min(done, size) if size else done,
                                          "total": size, "found": len(txns)}) + "\n"
            yield json.dumps({"type": "result", "found": len(txns),
                              "dataset": {"transactions": txns, "investments": inv}}) + "\n"
        finally:
            try:
                os.remove(path)  # never persist the user's email data
            except OSError:
                pass

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
