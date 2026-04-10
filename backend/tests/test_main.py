import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from app.main import app
import os
import pandas as pd

client = TestClient(app)

def test_ping():
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"pong": "Hello, world!"}

def test_predict_price_route():
    response = client.get("/predict?ticker=SPY&obs_date=2025-01-27&target_date=2025-02-28")
    assert response.status_code == 200
    body = response.json()

    # New response shape: { data: {Price, PDF, CDF}, meta: {...} }
    assert "data" in body
    assert "meta" in body

    data = body["data"]
    assert "Price" in data
    assert "PDF" in data
    assert "CDF" in data
    assert len(data["Price"]) > 0

    meta = body["meta"]
    assert meta["ticker"] == "SPY"
    assert meta["obs_date"] == "2025-01-27"
    assert meta["spot"] > 0
