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
    # Create a dummy csv file
    data_dir = "app/data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        
    dummy_csv_path = os.path.join(data_dir, "dummy_options.csv")
    dummy_df = pd.DataFrame({
        'strike': [100, 110, 120, 130, 140],
        'last_price': [25, 15, 5, 1, 0.5],
        'bid': [24.9, 14.9, 4.9, 0.9, 0.4],
        'ask': [25.1, 15.1, 5.1, 1.1, 0.6]
    })
    dummy_df.to_csv(dummy_csv_path, index=False)

    response = client.get("/predict")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "price" in data
    assert "pdf" in data
    assert "cdf" in data
    assert isinstance(data["price"], list)
    assert isinstance(data["pdf"], list)
    assert isinstance(data["cdf"], list)
    assert len(data["price"]) > 0
    assert len(data["pdf"]) > 0
    assert len(data["cdf"]) > 0
    
    # Assert that price values are rounded to one decimal place
    for price_value in data["price"]:
        assert isinstance(price_value, float)
        assert round(price_value, 1) == price_value
