import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import prediction_inputs
from app.data import underlying
from app.prediction_pipeline.black_scholes import call_value
from app.prediction_pipeline.step2_implied_vol import calculate_IV_averaged
from app.prediction_pipeline.predict import predict_price, predict_price_with_progress, PipelineResult


def chain(spot, maturity, iv=0.3):
    strikes = np.arange(70, 141, 5, dtype=float)
    prices = call_value(spot, strikes, iv, maturity / 365, 0.04)
    return pd.DataFrame({"strike": strikes, "last_price": prices, "bid": prices, "ask": prices})


def test_iv_averaging_uses_each_days_spot():
    chains = {"2025-01-02": chain(100, 60), "2025-01-03": chain(110, 59)}
    result = calculate_IV_averaged(chains, {"2025-01-02": 100, "2025-01-03": 110},
                                   {"2025-01-02": 60, "2025-01-03": 59}, 0.04)
    assert np.allclose(result.iv, 0.3, atol=1e-5)
    with pytest.raises(ValueError, match="contemporaneous"):
        calculate_IV_averaged(chains, {"2025-01-03": 110}, {"2025-01-02": 60, "2025-01-03": 59}, 0.04)


def test_single_day_maturity_is_separate_from_forecast_horizon():
    kwargs = dict(quotes=chain(100, 60), spot=100, days_forward=30,
                  option_days_to_expiry=60, risk_free_rate=0.04)
    result = predict_price(**kwargs)
    assert np.allclose(result.iv_raw_values, 0.3, atol=1e-5)
    streamed = [step for step in predict_price_with_progress(**kwargs) if isinstance(step, PipelineResult)][0]
    pd.testing.assert_frame_equal(result.df, streamed.df)
    assert "clipped_negative_fraction" in result.diagnostics


@pytest.fixture
def mocked_inputs(monkeypatch):
    rows = pd.concat([chain(100, 49).assign(trade_date="2025-01-02"),
                      chain(110, 48).assign(trade_date="2025-01-03")])
    monkeypatch.setattr(prediction_inputs.db, "find_best_expiry_in_range", lambda *a: date(2025, 2, 20))
    monkeypatch.setattr(prediction_inputs.db, "query_chains_range", lambda *a: rows)
    monkeypatch.setattr(prediction_inputs, "daily_closes", lambda *a, **kw: {
        "2025-01-02": 100, "2025-01-03": 110, "2025-11-12": 999})


def test_no_future_prices_and_actual_observation_horizon(mocked_inputs):
    result = prediction_inputs.prepare_prediction("SPY", date(2025, 1, 2), date(2025, 1, 5), date(2025, 2, 4))
    assert result.spots == {"2025-01-02": 100, "2025-01-03": 110}
    assert result.observation == date(2025, 1, 3)
    assert result.days_forward == 32
    assert result.meta["option_days_to_expiry"] == 48
    assert result.meta["requested_obs_date_to"] == "2025-01-05"
    assert result.meta["spot_source"] == "massive_daily_unadjusted"
    assert result.meta["mode"] == "backtest"


def test_unavailable_stock_data_is_explicit(mocked_inputs, monkeypatch):
    monkeypatch.setattr(prediction_inputs, "daily_closes", lambda *a, **kw: {})
    result = prediction_inputs.prepare_prediction("SPY", date(2025, 1, 2), date(2025, 1, 3), date(2025, 2, 4))
    assert result.meta["estimated_spot_dates"] == ["2025-01-02", "2025-01-03"]
    assert result.meta["spot_source"] == "options_estimate"
    assert any("not actual" in warning for warning in result.meta["warnings"])


def test_reversed_dates_rejected(mocked_inputs):
    with pytest.raises(ValueError, match="start"):
        prediction_inputs.prepare_prediction("SPY", date(2025, 1, 5), date(2025, 1, 2), date(2025, 2, 4))


def test_realized_price_is_exact_target_not_later_estimate(monkeypatch):
    monkeypatch.setattr(underlying, "daily_closes", lambda *a, **kw: {"2025-01-06": 110})
    assert underlying.realized_close("SPY", date(2025, 1, 3)) is None
    assert underlying.realized_close("SPY", date(2025, 1, 6))["price"] == 110


def test_daily_bars_cache_dates_and_unadjusted_flag(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from datetime import datetime
    from zoneinfo import ZoneInfo
    calls = []
    timestamp = int(datetime(2025, 1, 3, tzinfo=ZoneInfo("America/New_York")).timestamp() * 1000)
    class Client:
        def list_aggs(self, *args, **kwargs):
            calls.append(kwargs)
            return [SimpleNamespace(timestamp=timestamp, close=123.45)]
    monkeypatch.setattr(underlying, "STOCK_CACHE", tmp_path)
    monkeypatch.setattr(underlying, "get_client", Client)
    assert underlying.daily_closes("SPY", date(2025, 1, 2), date(2025, 1, 3)) == {"2025-01-03": 123.45}
    assert underlying.daily_closes("SPY", date(2025, 1, 2), date(2025, 1, 3), allow_api=False) == {"2025-01-03": 123.45}
    assert calls == [{"adjusted": False, "sort": "asc", "limit": 50000}]


def test_api_and_stream_share_same_metadata(mocked_inputs, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    import json
    monkeypatch.setattr(underlying, "realized_close", lambda *a, **kw: None)
    client = TestClient(app)
    query = "?ticker=SPY&obs_date_from=2025-01-02&obs_date_to=2025-01-05&target_date=2025-02-04&kernel_smooth=false"
    response = client.get("/predict" + query)
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in client.get("/predict-stream" + query).text.splitlines() if line.startswith("data: ")]
    assert events[-1]["result"] == response.json()
    assert "realized_price" not in response.json()["meta"]


def test_chat_does_not_fetch_latest_daily_proxy(mocked_inputs, monkeypatch):
    from app.chat import _run_prediction_tool
    monkeypatch.setattr(prediction_inputs.db, "query_daily_closes", lambda *a: pytest.fail("Must not fetch latest prices"))
    monkeypatch.setattr(underlying, "realized_close", lambda *a, **kw: None)
    result = _run_prediction_tool({"ticker": "SPY", "obs_date_from": "2025-01-02", "obs_date_to": "2025-01-03", "target_date": "2025-02-04"})
    assert result["spot"] == 110
    assert result["expiry_used"] == "2025-02-20"


def test_mcp_matches_point_in_time_inputs(mocked_inputs, monkeypatch):
    from app.prediction_mcp import _run_prediction
    monkeypatch.setattr(underlying, "realized_close", lambda *a, **kw: None)
    result = _run_prediction(ticker="SPY", obs_from=date(2025, 1, 2), obs_to=date(2025, 1, 3),
                             target=date(2025, 2, 4), risk_free_rate=0.04, solver="brent", kernel_smooth=False)
    assert result["spot"] == 110
    assert result["estimated_spot_dates"] == []
    assert result["realized"] is None


def test_historical_chain_never_uses_snapshot_or_legacy_cache(tmp_path, monkeypatch):
    from app.data import fetcher
    legacy = tmp_path / "chain.csv"
    legacy.write_text("invalid legacy live snapshot")
    monkeypatch.setattr(fetcher, "_chain_cache_path", lambda *a: legacy)
    monkeypatch.setattr(fetcher, "_try_snapshot_chain", lambda *a: pytest.fail("Live snapshot in backtest"))
    calls = []
    def historical(client, ticker, observation, expiry, spot, delay):
        calls.append((observation, expiry))
        return chain(100, 60)
    monkeypatch.setattr(fetcher, "_fetch_chain_per_contract", historical)
    result = fetcher.fetch_options_chain("SPY", date(2025, 1, 2), date(2025, 3, 3), spot=100, client=object())
    assert len(result) > 5
    assert calls == [(date(2025, 1, 2), date(2025, 3, 3))]
    assert (tmp_path / "dated_v2_chain.csv").exists()
