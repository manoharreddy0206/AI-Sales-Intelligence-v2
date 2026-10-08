import csv
import io
import os
import sqlite3
import pandas as pd
from datetime import datetime, timezone
from collections import defaultdict
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .model import evaluate_repeat_purchase

DB_PATH = Path(os.environ.get("SALES_DB", str(Path(__file__).resolve().parents[1] / "sales.db")))
app = FastAPI(title="AI Sales Intelligence")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, order_date TEXT NOT NULL, amount REAL NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS uploads (id INTEGER PRIMARY KEY, filename TEXT, created_at TEXT, added INTEGER, updated INTEGER, unchanged INTEGER)")
    return db


def read_orders():
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM orders ORDER BY order_date, order_id")]


def parse_csv(raw: bytes):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "CSV must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    required = {"order_id", "customer_id", "order_date", "amount"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise HTTPException(400, f"Required columns: {', '.join(sorted(required))}")
    parsed = []
    seen = set()
    for line, row in enumerate(reader, start=2):
        try:
            oid, cid = row["order_id"].strip(), row["customer_id"].strip()
            day = date.fromisoformat(row["order_date"].strip()).isoformat()
            amount = float(row["amount"])
            if not oid or not cid or oid in seen or not (0 < amount < 1_000_000_000):
                raise ValueError("empty ID, duplicate order ID, or invalid amount")
            seen.add(oid)
            parsed.append((oid, cid, day, amount))
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise HTTPException(400, f"Invalid data at CSV line {line}: {exc}") from exc
    if not parsed:
        raise HTTPException(400, "CSV has no data rows")
    return parsed


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith((".csv", ".xlsx")):
        raise HTTPException(400, "Choose a .csv or .xlsx file")
    raw = await file.read(2_000_001)
    if len(raw) > 2_000_000:
        raise HTTPException(413, "Maximum CSV size is 2 MB")
    if file.filename.lower().endswith('.xlsx'):
        try:
            frame = pd.read_excel(io.BytesIO(raw), dtype={"order_id": str, "customer_id": str})
            if 'order_date' in frame:
                frame['order_date'] = pd.to_datetime(frame['order_date'], errors='raise').dt.strftime('%Y-%m-%d')
            raw = frame.to_csv(index=False).encode()
        except Exception as exc:
            raise HTTPException(400, 'Cannot read Excel. Use the first sheet and required columns.') from exc
    rows = parse_csv(raw)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        added = updated = unchanged = 0
        for row in rows:
            existing = db.execute('SELECT * FROM orders WHERE order_id=?', (row[0],)).fetchone()
            if existing is None:
                added += 1
            elif tuple(existing) == row:
                unchanged += 1
            else:
                updated += 1
        db.executemany("INSERT INTO orders VALUES (?, ?, ?, ?) ON CONFLICT(order_id) DO UPDATE SET customer_id=excluded.customer_id, order_date=excluded.order_date, amount=excluded.amount", rows)
        db.execute('INSERT INTO uploads(filename,created_at,added,updated,unchanged) VALUES(?,?,?,?,?)', (Path(file.filename).name, datetime.now(timezone.utc).isoformat(), added, updated, unchanged))
    return {"accepted_rows": len(rows), "added": added, "updated": updated, "unchanged": unchanged, "message": "Upload complete"}


@app.get('/api/uploads')
def uploads():
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM uploads ORDER BY id DESC LIMIT 20')]


@app.get("/api/summary")
def summary(start: date | None = None, end: date | None = None):
    if start and end and start > end:
        raise HTTPException(400, 'Start date must precede end date')
    rows = [r for r in read_orders() if (not start or r['order_date'] >= start.isoformat()) and (not end or r['order_date'] <= end.isoformat())]
    monthly = defaultdict(float)
    for row in rows:
        monthly[row["order_date"][:7]] += row["amount"]
    revenue = round(sum(r['amount'] for r in rows), 2)
    return {"orders": len(rows), "customers": len({r["customer_id"] for r in rows}), "revenue": revenue, "average_order": round(revenue / len(rows), 2) if rows else 0, "monthly": [{"month": k, "revenue": round(v, 2)} for k, v in sorted(monthly.items())]}


@app.get("/api/segments")
def segments():
    rows = read_orders()
    if not rows:
        return {"as_of": None, "counts": {}, "customers": []}
    as_of = max(date.fromisoformat(r["order_date"]) for r in rows)
    groups = defaultdict(list)
    for row in rows:
        groups[row["customer_id"]].append(row)
    result = []
    for cid, orders in sorted(groups.items()):
        recency = (as_of - max(date.fromisoformat(o["order_date"]) for o in orders)).days
        frequency = len(orders)
        monetary = round(sum(o["amount"] for o in orders), 2)
        segment = "At risk" if recency > 60 else "Loyal" if frequency >= 4 else "Active"
        result.append({"customer_id": cid, "recency_days": recency, "frequency": frequency, "monetary": monetary, "segment": segment})
    counts = {name: sum(c["segment"] == name for c in result) for name in ("Active", "Loyal", "At risk")}
    return {"as_of": as_of.isoformat(), "counts": counts, "customers": result}


@app.post('/api/compare-models')
def compare_models():
    from .comparison import compare
    return compare(read_orders())


@app.get("/api/model-report")
def model_report():
    return evaluate_repeat_purchase(read_orders())
