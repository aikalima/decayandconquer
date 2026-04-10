"""Tests for backtest scoring logic — no API calls needed."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest
from datetime import date

from backtest import score_prediction
from app.data.fetcher import find_nearest_expiry_friday

DATA_DIR = Path(__file__).parent.parent / "app" / "data"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_gaussian_prediction(mean: float, std: float, n: int = 500) -> pd.DataFrame:
    """Create a synthetic normalised Gaussian PDF/CDF for testing."""
    prices = np.linspace(mean - 4 * std, mean + 4 * std, n)
    pdf = np.exp(-0.5 * ((prices - mean) / std) ** 2) / (std * np.sqrt(2 * np.pi))
    # Normalise
    pdf /= np.trapezoid(pdf, prices)
    from scipy.integrate import cumulative_trapezoid
    cdf = cumulative_trapezoid(pdf, prices, initial=0.0)
    cdf = np.clip(cdf, 0.0, 1.0)
    return pd.DataFrame({"Price": prices, "PDF": pdf, "CDF": cdf})


# ---------------------------------------------------------------------------
# score_prediction tests
# ---------------------------------------------------------------------------

class TestScorePrediction:
    def test_median_gives_50th_percentile(self):
        df = make_gaussian_prediction(100.0, 10.0)
        result = score_prediction(df, 100.0)
        assert abs(result["cdf_percentile"] - 0.5) < 0.02

    def test_low_realized_gives_low_percentile(self):
        df = make_gaussian_prediction(100.0, 10.0)
        result = score_prediction(df, 75.0)
        assert result["cdf_percentile"] < 0.05

    def test_high_realized_gives_high_percentile(self):
        df = make_gaussian_prediction(100.0, 10.0)
        result = score_prediction(df, 125.0)
        assert result["cdf_percentile"] > 0.95

    def test_ci_contains_mean(self):
        df = make_gaussian_prediction(100.0, 10.0)
        result = score_prediction(df, 100.0)
        assert result["ci_90_low"] < 100.0 < result["ci_90_high"]

    def test_ci_width_is_reasonable(self):
        df = make_gaussian_prediction(100.0, 10.0)
        result = score_prediction(df, 100.0)
        width = result["ci_90_high"] - result["ci_90_low"]
        # 90% CI of N(100,10) should be roughly 100 +/- 16.4 -> width ~33
        assert 25 < width < 40

    def test_realized_below_domain_clips_to_zero(self):
        df = make_gaussian_prediction(100.0, 10.0)
        result = score_prediction(df, 0.0)
        assert result["cdf_percentile"] == 0.0

    def test_realized_above_domain_clips_to_one(self):
        df = make_gaussian_prediction(100.0, 10.0)
        result = score_prediction(df, 500.0)
        assert result["cdf_percentile"] == 1.0

    def test_mean_close_to_distribution_mean(self):
        df = make_gaussian_prediction(100.0, 10.0)
        result = score_prediction(df, 100.0)
        assert abs(result["predicted_mean"] - 100.0) < 0.5

    def test_median_close_to_distribution_median(self):
        df = make_gaussian_prediction(100.0, 10.0)
        result = score_prediction(df, 100.0)
        assert abs(result["predicted_median"] - 100.0) < 0.5


# ---------------------------------------------------------------------------
# find_nearest_expiry_friday tests
# ---------------------------------------------------------------------------

class TestExpiryFriday:
    def test_returns_friday(self):
        result = find_nearest_expiry_friday(date(2025, 1, 6), 30)
        assert result.weekday() == 4  # Friday

    def test_snaps_to_third_friday(self):
        # 2025-01-15 + 30d = Feb 14 -> nearest 3rd Friday = Feb 21
        result = find_nearest_expiry_friday(date(2025, 1, 15), 30)
        assert result == date(2025, 2, 21)

    def test_june_avoids_july4(self):
        # 2025-06-01 + 30d = Jul 1 -> nearest 3rd Friday = Jun 20 or Jul 18, not Jul 4
        result = find_nearest_expiry_friday(date(2025, 6, 1), 30)
        assert result in (date(2025, 6, 20), date(2025, 7, 18))
        assert result.weekday() == 4

    def test_90_day_horizon(self):
        # 2025-06-01 + 90d = Aug 30 -> nearest 3rd Friday = Aug 15 or Sep 19
        result = find_nearest_expiry_friday(date(2025, 6, 1), 90)
        assert result == date(2025, 8, 15)

    def test_result_on_or_after_obs(self):
        # Expiry should never be before the observation date
        result = find_nearest_expiry_friday(date(2025, 3, 20), 5)
        assert result >= date(2025, 3, 20)


# ---------------------------------------------------------------------------
# Integration test with existing cached data
# ---------------------------------------------------------------------------

class TestScoringWithRealData:
    def test_score_spy_prediction(self):
        """Run predict_price on existing spy.csv and score against a price."""
        from app.prediction_pipeline.predict import predict_price

        quotes = pd.read_csv(DATA_DIR / "spy.csv")
        result_df = predict_price(
            quotes=quotes, spot=595.0, days_forward=30, risk_free_rate=0.04,
        ).df

        score = score_prediction(result_df, 600.0)
        assert 0.0 <= score["cdf_percentile"] <= 1.0
        assert score["predicted_median"] > 0
        assert score["ci_90_low"] < score["ci_90_high"]
        # Median should be near spot for short-dated options
        assert 500 < score["predicted_median"] < 700
