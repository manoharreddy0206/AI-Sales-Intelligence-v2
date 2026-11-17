import logging
import os
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import analytics, ingest
from .copilot import service as copilot
from .model import evaluate_repeat_purchase

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("SALES_DB", str(BACKEND_DIR / "sales.db")))
DEMO_MODE = os.environ.get("DEMO_MODE", "").lower() in {"1", "true", "yes"}
SEED_CSV = Path(os.environ.get("SEED_CSV", str(BACKEND_DIR / "sample_sales.csv")))
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", str(BACKEND_DIR.parent / "frontend" / "dist")))
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
COPILOT_RATE_LIMIT = int(os.environ.get("COPILOT_RATE_LIMIT_PER_10_MIN", "30"))

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("sales")


@asynccontextmanager
async def lifespan(_app):
    if DEMO_MODE:
        seeded = ingest.seed_if_empty(DB_PATH, SEED_CSV)
        log.info("demo mode: %s", f"seeded {seeded['added']} orders" if seeded else "database already populated")
    yield


app = FastAPI(title="AI Sales Intelligence", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


def read_orders():
    return analytics.read_orders(DB_PATH)


@app.get("/api/health")
def health():
    return {"status": "ok", "orders": ingest.order_count(DB_PATH), "demo_mode": DEMO_MODE, "copilot_mode": copilot.provider_mode()}


@app.get("/api/config")
def config():
    return {"demo_mode": DEMO_MODE, "uploads_enabled": not DEMO_MODE, "copilot_mode": copilot.provider_mode(), "copilot_model": copilot.provider_model()}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if DEMO_MODE:
        raise HTTPException(403, "Uploads are disabled in the public demo, which uses a seeded synthetic dataset. Run locally to upload files.")
    raw = await file.read(ingest.MAX_BYTES + 1)
    try:
        rows = ingest.parse_upload(file.filename, raw)
    except ingest.UploadError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    return ingest.import_rows(DB_PATH, rows, file.filename)


@app.get("/api/uploads")
def uploads():
    from .storage import connect
    with connect(DB_PATH) as db:
        return [dict(r) for r in db.execute("SELECT * FROM uploads ORDER BY id DESC LIMIT 20")]


@app.get("/api/summary")
def summary(start: date | None = None, end: date | None = None):
    try:
        return analytics.summary(DB_PATH, start, end)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/segments")
def segments():
    return analytics.segments(DB_PATH)


@app.post("/api/compare-models")
def compare_models():
    from .comparison import compare
    return compare(read_orders())


@app.get("/api/model-report")
def model_report():
    return evaluate_repeat_purchase(read_orders())


class CopilotContext(BaseModel):
    start: date | None = None
    end: date | None = None


class CopilotRequest(BaseModel):
    question: str = Field(min_length=1, max_length=copilot.MAX_QUESTION_CHARS)
    context: CopilotContext | None = None


_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _rate_limited(client: str) -> bool:
    """Per-client sliding window; only enforced in the public demo."""
    if not DEMO_MODE:
        return False
    now = time.monotonic()
    with _hits_lock:
        window = _hits[client]
        while window and now - window[0] > 600:
            window.popleft()
        if len(window) >= COPILOT_RATE_LIMIT:
            return True
        window.append(now)
    return False


@app.post("/api/copilot")
def copilot_answer(body: CopilotRequest, request: Request):
    if _rate_limited(request.client.host if request.client else "unknown"):
        raise HTTPException(429, "Demo copilot limit reached. Try again in a few minutes.")
    context = body.context.model_dump() if body.context else {}
    return copilot.answer(body.question, DB_PATH, context=context)


if FRONTEND_DIST.is_dir():
    # Single-service deployment: FastAPI also serves the built React app.
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
