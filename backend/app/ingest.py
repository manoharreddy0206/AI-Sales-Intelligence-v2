"""CSV/Excel validation and transactional import, independent of the web framework.

The rules are the ones the original /api/upload route enforced:
- required columns order_id, customer_id, order_date, amount (extra columns ignored)
- dates must be ISO dates (YYYY-MM-DD), amounts 0 < amount < 1,000,000,000
- non-empty IDs, no duplicate order IDs inside one file
- one invalid row rejects the whole file; existing orders are untouched
- an order ID that already exists is updated in place
"""
import csv
import io
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from .storage import connect

REQUIRED = {"order_id", "customer_id", "order_date", "amount"}
MAX_BYTES = 2_000_000


class UploadError(Exception):
    """A user-facing validation failure. ``status`` is the HTTP status the API returns."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def parse_csv(raw: bytes):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UploadError("CSV must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
        raise UploadError(f"Required columns: {', '.join(sorted(REQUIRED))}")
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
            raise UploadError(f"Invalid data at CSV line {line}: {exc}") from exc
    if not parsed:
        raise UploadError("CSV has no data rows")
    return parsed


def _excel_date_cell(value):
    """Convert one Excel order_date cell without guessing day/month order.

    Real Excel date cells arrive as datetimes and are unambiguous. Text cells are
    passed through unchanged so they meet the same YYYY-MM-DD rule as CSV uploads.
    (The original code ran pd.to_datetime over the whole column, which silently
    read the text "03/04/2025" as 4 March instead of rejecting it.)
    """
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NaT:
        return ""
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def excel_to_csv(raw: bytes) -> bytes:
    try:
        frame = pd.read_excel(io.BytesIO(raw), dtype={"order_id": str, "customer_id": str})
        if "order_date" in frame:
            frame["order_date"] = frame["order_date"].astype(object).map(_excel_date_cell)
        return frame.to_csv(index=False).encode()
    except Exception as exc:
        raise UploadError("Cannot read Excel. Use the first sheet and required columns.") from exc


def parse_upload(filename: str | None, raw: bytes):
    """Validate a whole upload and return (order_id, customer_id, order_date, amount) tuples."""
    if not filename or not filename.lower().endswith((".csv", ".xlsx")):
        raise UploadError("Choose a .csv or .xlsx file")
    if len(raw) > MAX_BYTES:
        raise UploadError("Maximum CSV size is 2 MB", status=413)
    if filename.lower().endswith(".xlsx"):
        raw = excel_to_csv(raw)
    return parse_csv(raw)


def import_rows(db_path, rows, filename: str):
    """Upsert validated rows in one transaction and record the import."""
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        added = updated = unchanged = 0
        for row in rows:
            existing = db.execute("SELECT * FROM orders WHERE order_id=?", (row[0],)).fetchone()
            if existing is None:
                added += 1
            elif tuple(existing) == row:
                unchanged += 1
            else:
                updated += 1
        db.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?) ON CONFLICT(order_id) DO UPDATE SET "
            "customer_id=excluded.customer_id, order_date=excluded.order_date, amount=excluded.amount",
            rows,
        )
        db.execute(
            "INSERT INTO uploads(filename,created_at,added,updated,unchanged) VALUES(?,?,?,?,?)",
            (Path(filename).name, datetime.now(timezone.utc).isoformat(), added, updated, unchanged),
        )
    return {"accepted_rows": len(rows), "added": added, "updated": updated, "unchanged": unchanged, "message": "Upload complete"}


def order_count(db_path) -> int:
    with connect(db_path) as db:
        return db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]


def seed_if_empty(db_path, csv_path: Path) -> dict | None:
    """Load the synthetic sample into an empty database (used by the public demo)."""
    if order_count(db_path):
        return None
    rows = parse_csv(Path(csv_path).read_bytes())
    return import_rows(db_path, rows, f"{Path(csv_path).name} (demo seed)")
