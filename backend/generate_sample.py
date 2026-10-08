import csv
import random
from datetime import date, timedelta
from pathlib import Path

rng = random.Random(42)
start = date(2025, 1, 1)
rows = []
for customer in range(1, 61):
    propensity = rng.uniform(0.15, 0.85)
    for month in range(8):
        if month == 0 or rng.random() < propensity:
            day = start + timedelta(days=month * 30 + rng.randrange(25))
            rows.append((f"ORD-{len(rows)+1:04d}", f"C{customer:03d}", day.isoformat(), round(rng.uniform(25, 400), 2)))
path = Path(__file__).with_name("sample_sales.csv")
with path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["order_id", "customer_id", "order_date", "amount"])
    writer.writerows(rows)
print(f"Wrote {len(rows)} synthetic orders to {path}")
