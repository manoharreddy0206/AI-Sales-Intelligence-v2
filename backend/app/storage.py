"""SQLite access shared by the API routes, the importer and the copilot tools."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, order_date TEXT NOT NULL, amount REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS uploads (id INTEGER PRIMARY KEY, filename TEXT, created_at TEXT, added INTEGER, updated INTEGER, unchanged INTEGER)",
)


@contextmanager
def connect(db_path: Path | str):
    """Open a connection, commit on success, roll back on error, and always close it."""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        for statement in SCHEMA:
            db.execute(statement)
        with db:
            yield db
    finally:
        db.close()
