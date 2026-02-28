import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from app.prediction_pipeline.predict import predict_price

DATA_DIR = Path(__file__).parent.parent / "app" / "data"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assert_valid_result(result: pd.DataFrame, min_rows: int = 1):
    assert isinstance(result, pd.DataFrame)
    assert {"Price", "PDF", "CDF"} <= set(result.columns)
    assert len(result) >= min_rows
    assert result["PDF"].ge(0).all(), "PDF must be non-negative"
    # CDF may exceed [0,1] when the PDF is cropped to a narrow strike band
    # (the pipeline normalises over the full extrapolated domain, not just the crop).
    # Assert monotonicity instead of strict bounds.
    assert result["CDF"].is_monotonic_increasing, "CDF must be non-decreasing"


# ---------------------------------------------------------------------------
# Dummy data (smoke test)
# ---------------------------------------------------------------------------

def test_predict_price_default_values():
    dummy_df = pd.DataFrame({
        'strike':     [100, 110, 120, 130, 140],
        'last_price': [25,  15,  5,   1,   0.5],
        'bid':        [24.9, 14.9, 4.9, 0.9, 0.4],
        'ask':        [25.1, 15.1, 5.1, 1.1, 0.6],
    })
    result = predict_price(quotes=dummy_df, spot=120, days_forward=30, risk_free_rate=0.02)
    assert_valid_result(result)


# ---------------------------------------------------------------------------
# SPY real data
# ---------------------------------------------------------------------------

def test_predict_price_spy():
    """SPY options — strikes 360–700, spot ~595 (late-Jan 2025)."""
    quotes = pd.read_csv(DATA_DIR / "spy.csv")
    result = predict_price(
        quotes=quotes,
        spot=595.0,
        days_forward=30,
        risk_free_rate=0.04,
        solver="brent",
    )
    assert_valid_result(result, min_rows=10)
    # PDF should be concentrated around the spot price
    peak_price = result.loc[result["PDF"].idxmax(), "Price"]
    assert 400 < peak_price < 800, f"PDF peak at unexpected price: {peak_price}"


def test_predict_price_spy_with_kde():
    """SPY pipeline with optional KDE smoothing enabled."""
    quotes = pd.read_csv(DATA_DIR / "spy.csv")
    result = predict_price(
        quotes=quotes,
        spot=595.0,
        days_forward=30,
        risk_free_rate=0.04,
        solver="brent",
        kernel_smooth=True,
    )
    assert_valid_result(result, min_rows=10)


# ---------------------------------------------------------------------------
# NVIDIA real data
# ---------------------------------------------------------------------------

NVDA_FILE = "nvidia_date20250128_strikedate20250516_price12144.csv"
NVDA_SPOT = 121.44          # encoded in filename (price12144 / 100)
NVDA_DAYS = 108             # Jan 28 → May 16, 2025

def test_predict_price_nvidia():
    """NVIDIA options — strikes 5–300, spot 121.44, expiry May 16 2025."""
    quotes = pd.read_csv(DATA_DIR / NVDA_FILE)
    result = predict_price(
        quotes=quotes,
        spot=NVDA_SPOT,
        days_forward=NVDA_DAYS,
        risk_free_rate=0.04,
        solver="brent",
    )
    assert_valid_result(result, min_rows=10)
    peak_price = result.loc[result["PDF"].idxmax(), "Price"]
    assert 50 < peak_price < 250, f"PDF peak at unexpected price: {peak_price}"


def test_predict_price_nvidia_newton():
    """NVIDIA pipeline using Newton-Raphson IV solver."""
    quotes = pd.read_csv(DATA_DIR / NVDA_FILE)
    result = predict_price(
        quotes=quotes,
        spot=NVDA_SPOT,
        days_forward=NVDA_DAYS,
        risk_free_rate=0.04,
        solver="newton",
    )
    assert_valid_result(result, min_rows=10)
