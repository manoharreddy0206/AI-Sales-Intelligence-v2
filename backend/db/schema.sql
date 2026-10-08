-- Reference schema; the API creates these tables automatically.
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    order_date TEXT NOT NULL,
    amount REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY,
    filename TEXT,
    created_at TEXT,
    added INTEGER,
    updated INTEGER,
    unchanged INTEGER
);
