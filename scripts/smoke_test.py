"""Smoke test a running instance (local or hosted). Standard library only.

    python scripts/smoke_test.py http://localhost:8000
"""
import json
import sys
import urllib.request

base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")


def get(path, data=None):
    req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data else None,
                                 headers={"content-type": "application/json"}, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=40) as r:
        body = r.read()
        return r.status, (json.loads(body) if "json" in r.headers.get("content-type", "") else body.decode(errors="replace"))


checks = []


def check(name, ok, detail=""):
    checks.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


status, health = get("/api/health")
check("health", status == 200 and health.get("status") == "ok", json.dumps(health))
status, config = get("/api/config")
check("config", status == 200, json.dumps(config))
status, summary = get("/api/summary")
check("summary has orders", summary.get("orders", 0) > 0, f"orders={summary.get('orders')} revenue={summary.get('revenue')}")
status, answer = get("/api/copilot", {"question": "What was revenue last month?"})
ev = next((e for e in answer.get("evidence", []) if e.get("tool") == "get_revenue_summary" and e.get("status") == "ok"), None)
if ev:
    p = ev["result"]["period"]
    _, dash = get(f"/api/summary?start={p['start']}&end={p['end']}")
    check("copilot revenue == dashboard revenue", ev["result"]["revenue"] == dash["revenue"],
          f"{p['label']}: copilot={ev['result']['revenue']} dashboard={dash['revenue']} mode={answer['mode']} {answer['elapsed_ms']} ms")
else:
    check("copilot answered with a revenue tool call", False, json.dumps(answer)[:300])
status, page = get("/")
check("frontend served at /", status == 200 and "<div id=\"root\">" in page)
status, docs = get("/docs")
check("API docs at /docs", status == 200)
print(f"\n{sum(checks)}/{len(checks)} checks passed against {base}")
sys.exit(0 if all(checks) else 1)
