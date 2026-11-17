"""Import behaviour, tested without the web framework."""
import io
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from app import analytics, ingest
from app.storage import connect

BACKEND = Path(__file__).parents[1]
SAMPLE = BACKEND / "sample_sales.csv"


def load(db, name):
    raw = (BACKEND / name).read_bytes()
    return ingest.import_rows(db, ingest.parse_upload(name, raw), name)


def stored(db):
    with connect(db) as c:
        return c.execute("SELECT COUNT(*), ROUND(SUM(amount), 2) FROM orders").fetchone()


def upload_count(db):
    with connect(db) as c:
        return c.execute("SELECT COUNT(*) FROM uploads").fetchone()[0]


def test_sample_then_changed_reupload_then_invalid(tmp_path):
    db = tmp_path / "s.db"
    first = load(db, "sample_sales.csv")
    assert (first["accepted_rows"], first["added"]) == (269, 269)
    assert tuple(stored(db)) == (269, 54233.7)

    second = load(db, "sample_updates.csv")
    assert (second["accepted_rows"], second["added"], second["updated"], second["unchanged"]) == (20, 5, 10, 5)
    # +10 on ten orders, plus five new orders of 101..105.
    assert tuple(stored(db)) == (274, round(54233.7 + 100 + 515, 2))

    with pytest.raises(ingest.UploadError, match="line 6"):
        load(db, "sample_invalid.csv")
    assert tuple(stored(db)) == (274, round(54233.7 + 615, 2))
    assert upload_count(db) == 2


def test_failure_mid_import_rolls_back_everything(tmp_path):
    db = tmp_path / "f.db"
    load(db, "sample_sales.csv")
    before = tuple(stored(db))
    # Fault injection: the database aborts on the 3rd row, after rows 1-2 were written.
    raw = sqlite3.connect(db)
    raw.execute("CREATE TRIGGER boom BEFORE INSERT ON orders WHEN NEW.order_id='FAULT' BEGIN SELECT RAISE(ABORT, 'injected'); END")
    raw.commit()
    raw.close()
    rows = [("N1", "C1", "2025-08-01", 10.0), ("ORD-0001", "C001", "2025-01-01", 999.0), ("FAULT", "C2", "2025-08-02", 5.0)]
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        ingest.import_rows(db, rows, "fault.csv")
    assert tuple(stored(db)) == before
    assert upload_count(db) == 1
    with connect(db) as c:
        assert c.execute("SELECT amount FROM orders WHERE order_id='ORD-0001'").fetchone()[0] == 303.08


@pytest.mark.parametrize("line,reason", [
    ("B,C1,2025-01-01,\"1,200\"", "thousands separator"),
    ("B,C1,2025-01-01,$100", "currency symbol"),
    ("B,C1,2025-01-01,0", "zero amount"),
    ("B,C1,03/04/2025,10", "non-ISO date"),
    ("B,,2025-01-01,10", "empty customer"),
    ("A,C1,2025-01-02,10", "duplicate order id in file"),
])
def test_csv_rejections(line, reason):
    raw = f"order_id,customer_id,order_date,amount\nA,C1,2025-01-01,10\n{line}\n".encode()
    with pytest.raises(ingest.UploadError):
        ingest.parse_csv(raw)


def xlsx(rows):
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    return buf.getvalue()


def test_excel_text_dates_follow_the_csv_rule():
    # Regression: v2 parsed the text "03/04/2025" as 2025-03-04 (month-first) and stored it.
    raw = xlsx([{"order_id": "X1", "customer_id": "C1", "order_date": "03/04/2025", "amount": 10}])
    with pytest.raises(ingest.UploadError, match="line 2"):
        ingest.parse_upload("orders.xlsx", raw)


def test_excel_real_date_cells_and_iso_text_are_accepted():
    raw = xlsx([
        {"order_id": "X1", "customer_id": "C1", "order_date": datetime(2025, 4, 3), "amount": 10},
        {"order_id": "X2", "customer_id": "C1", "order_date": "2025-04-05", "amount": 12.5},
    ])
    assert ingest.parse_upload("orders.xlsx", raw) == [("X1", "C1", "2025-04-03", 10.0), ("X2", "C1", "2025-04-05", 12.5)]


def test_seed_only_fills_an_empty_database(tmp_path):
    db = tmp_path / "seed.db"
    assert ingest.seed_if_empty(db, SAMPLE)["added"] == 269
    assert ingest.seed_if_empty(db, SAMPLE) is None
    assert ingest.order_count(db) == 269


def test_dashboard_month_matches_independent_sql(tmp_path):
    db = tmp_path / "m.db"
    load(db, "sample_sales.csv")
    from datetime import date
    s = analytics.summary(db, date(2025, 7, 1), date(2025, 7, 31))
    with connect(db) as c:
        n, total = c.execute("SELECT COUNT(*), SUM(amount) FROM orders WHERE order_date BETWEEN '2025-07-01' AND '2025-07-31'").fetchone()
    assert (s["orders"], s["revenue"]) == (n, round(total, 2)) == (29, 5722.58)
    month = next(m for m in analytics.summary(db)["monthly"] if m["month"] == "2025-07")
    assert month["revenue"] == s["revenue"]
