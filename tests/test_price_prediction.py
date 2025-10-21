import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from app.predicion_pipline.predict import predict_price
import os

def test_predict_price_default_values():
    """
    Tests the predict_price function with default values.
    """
    dummy_df = pd.DataFrame({
        'strike': [100, 110, 120, 130, 140],
        'last_price': [25, 15, 5, 1, 0.5],
        'bid': [24.9, 14.9, 4.9, 0.9, 0.4],
        'ask': [25.1, 15.1, 5.1, 1.1, 0.6]
    })
    
    result = predict_price(quotes=dummy_df, spot=120, days_forward=30, risk_free_rate=0.02)

    assert isinstance(result, pd.DataFrame)
    assert "Price" in result.columns
    assert "PDF" in result.columns
    assert "CDF" in result.columns
    assert len(result) > 0
