import io

from fastapi.testclient import TestClient
from app import main


def test_upload_is_atomic_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    client = TestClient(main.app)
    good = b"order_id,customer_id,order_date,amount\nA,C1,2025-01-01,100\n"
    assert client.post("/api/upload", files={"file": ("sales.csv", io.BytesIO(good), "text/csv")}).status_code == 200
    assert client.post("/api/upload", files={"file": ("sales.csv", io.BytesIO(good), "text/csv")}).status_code == 200
    assert client.get("/api/summary").json()["orders"] == 1
    bad = b"order_id,customer_id,order_date,amount\nB,C2,2025-01-02,40\nC,C3,2025-01-03,-2\n"
    response = client.post("/api/upload", files={"file": ("sales.csv", io.BytesIO(bad), "text/csv")})
    assert response.status_code == 400
    assert client.get("/api/summary").json()["orders"] == 1
