"""Write the seeded synthetic demo files.

sample_sales.csv    269 orders for 60 customers, Jan-Aug 2025 (unchanged from v2)
sample_updates.csv  re-upload: 10 existing orders with changed amounts, 5 unchanged, 5 new
sample_invalid.csv  4 valid rows followed by a negative amount (whole file must be rejected)
"""
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

HEADER = ["order_id", "customer_id", "order_date", "amount"]
here = Path(__file__).parent


def write(name, data):
    path = here / name
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        writer.writerows(data)
    return path


path = write("sample_sales.csv", rows)
print(f"Wrote {len(rows)} synthetic orders to {path}")

changed = [(oid, cid, day, round(amount + 10, 2)) for oid, cid, day, amount in rows[:10]]
same = rows[10:15]
new = [(f"ORD-{len(rows)+i:04d}", f"C{i:03d}", f"2025-08-{20+i:02d}", 100.0 + i) for i in range(1, 6)]
write("sample_updates.csv", changed + same + new)
print("Wrote sample_updates.csv: 10 changed, 5 unchanged, 5 new")

invalid = rows[:4] + [("ORD-9999", "C001", "2025-08-01", -5)]
write("sample_invalid.csv", invalid)
print("Wrote sample_invalid.csv: 4 valid rows then a negative amount on CSV line 6")
