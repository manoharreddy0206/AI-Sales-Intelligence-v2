"""Read-only analytics shared by the dashboard routes and the copilot tools.

The dashboard's metric cards and the copilot's revenue answers both come from
``summary`` so the two cannot disagree for the same date range.
"""
from collections import defaultdict
from datetime import date

from .storage import connect


def read_orders(db_path, start: date | None = None, end: date | None = None):
    """Orders in an inclusive date range, using parameterized SQL."""
    clauses, params = [], []
    if start:
        clauses.append("order_date >= ?")
        params.append(start.isoformat())
    if end:
        clauses.append("order_date <= ?")
        params.append(end.isoformat())
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(db_path) as db:
        return [dict(row) for row in db.execute(f"SELECT * FROM orders{where} ORDER BY order_date, order_id", params)]


def summary(db_path, start: date | None = None, end: date | None = None):
    if start and end and start > end:
        raise ValueError("Start date must precede end date")
    rows = read_orders(db_path, start, end)
    monthly = defaultdict(float)
    for row in rows:
        monthly[row["order_date"][:7]] += row["amount"]
    revenue = round(sum(r["amount"] for r in rows), 2)
    return {
        "orders": len(rows),
        "customers": len({r["customer_id"] for r in rows}),
        "revenue": revenue,
        "average_order": round(revenue / len(rows), 2) if rows else 0,
        "monthly": [{"month": k, "revenue": round(v, 2)} for k, v in sorted(monthly.items())],
    }


def segments(db_path):
    rows = read_orders(db_path)
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


def dataset_info(db_path):
    """Scope facts attached to every copilot answer."""
    with connect(db_path) as db:
        row = db.execute(
            "SELECT COUNT(*) AS orders, COUNT(DISTINCT customer_id) AS customers, MIN(order_date) AS first_date, MAX(order_date) AS last_date FROM orders"
        ).fetchone()
    return dict(row)
