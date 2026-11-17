"""HTTP-level checks for the new routes. Skipped when FastAPI is not installed."""
import io
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="FastAPI not installed; HTTP tests need backend/requirements.txt")
from fastapi.testclient import TestClient  # noqa: E402

from app import ingest, main  # noqa: E402

SAMPLE = Path(__file__).parents[1] / "sample_sales.csv"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setenv("COPILOT_PROVIDER", "stub")
    return TestClient(main.app)


def test_health_config_and_copilot(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/config").json()["copilot_mode"] == "stub"
    client.post("/api/upload", files={"file": ("sample_sales.csv", SAMPLE.read_bytes(), "text/csv")})
    r = client.post("/api/copilot", json={"question": "What was revenue last month?"}).json()
    dashboard = client.get("/api/summary?start=2025-07-01&end=2025-07-31").json()
    assert r["evidence"][0]["result"]["revenue"] == dashboard["revenue"] == 5722.58
    assert client.post("/api/copilot", json={"question": ""}).status_code == 422
    assert client.post("/api/copilot", json={"question": "x" * 501}).status_code == 422


def test_demo_mode_blocks_uploads_and_seeds(client, monkeypatch):
    monkeypatch.setattr(main, "DEMO_MODE", True)
    r = client.post("/api/upload", files={"file": ("a.csv", io.BytesIO(b"order_id,customer_id,order_date,amount\nA,C,2025-01-01,1\n"), "text/csv")})
    assert r.status_code == 403
    ingest.seed_if_empty(main.DB_PATH, SAMPLE)
    assert client.get("/api/health").json()["orders"] == 269
