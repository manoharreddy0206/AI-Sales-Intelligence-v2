import io
import pandas as pd
from fastapi.testclient import TestClient
from app import main
from app.comparison import compare

def test_import_tracking_excel_and_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'sales.db')
    client = TestClient(main.app)
    raw = b'order_id,customer_id,order_date,amount\nA,C1,2025-01-01,100\n'
    def upload(content):
        return client.post('/api/upload', files={'file': ('sales.csv', content, 'text/csv')})
    assert upload(raw).json()['added'] == 1
    assert upload(raw).json()['unchanged'] == 1
    assert upload(raw.replace(b'100', b'150')).json()['updated'] == 1
    bad = b'order_id,customer_id,order_date,amount\nB,C2,2025-02-01,20\nC,C3,2025-02-02,-1\n'
    assert upload(bad).status_code == 400
    assert len(client.get('/api/uploads').json()) == 3
    assert client.get('/api/summary').json()['revenue'] == 150
    assert client.get('/api/summary?start=2025-02-01').json()['orders'] == 0
    assert client.get('/api/summary?start=2025-03-01&end=2025-01-01').status_code == 400
    buffer = io.BytesIO()
    pd.DataFrame([{'order_id':'B','customer_id':'C2','order_date':'2025-02-01','amount':50}]).to_excel(buffer,index=False)
    assert client.post('/api/upload', files={'file':('sales.xlsx',buffer.getvalue())}).json()['added'] == 1
    assert client.get('/api/summary').json()['revenue'] == 200

def test_comparison_temporal_split():
    from pathlib import Path
    rows = pd.read_csv(Path(__file__).parents[1] / 'sample_sales.csv').to_dict('records')
    result = compare(rows)
    assert result['status'] == 'ok'
    assert result['validation_cutoff'] < result['test_cutoff']
    assert len(result['models']) == 3
    assert result['selected'] in [m['name'] for m in result['models']]
    assert compare([])['status'] == 'needs_data'
