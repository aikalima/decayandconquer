import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from app.modules.price_preditction import predict_price
import os

def test_predict_price_default_values():
    """
    Tests the predict_price function with default values.
    """
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
    
    result = predict_price(input_csv_path=dummy_csv_path)

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], np.ndarray)
    assert isinstance(result[1], np.ndarray)
    assert len(result[0]) > 0
    assert len(result[1]) > 0
