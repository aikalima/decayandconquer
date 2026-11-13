"""Theta research eligibility must agree across persistence, HTTP and MCP."""

import sys
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

import duckdb
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.theta_quality import assess_row, scan_response
from app import screener
from app.data import db

NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
SCAN = {"scan_id": "test", "created_at": NOW.isoformat(), "expiry": "2026-12-18", "hv_days": 20}


def candidate(**updates):
    row = dict(ticker="SPY", spot=100, expiry="2026-12-18", spot_source="massive_daily_unadjusted",
               spot_date="2026-11-12", hv_source="massive_daily_adjusted", hv_20=.2, hv_days=20,
               hv_observations=21, hv_start_date="2026-10-15", hv_end_date="2026-11-12",
               avg_premium=1.5, rank_score=1.2)
    for side in ("call", "put"):
        row.update({f"{side}_{key}": val for key, val in dict(
            strike=100, bid=3.9, ask=4.1, mid=4, iv=.3, premium=1.5, rank_score=1.2,
            price_source="last_quote", quote_updated_ns=int((NOW - timedelta(hours=16)).timestamp() * 1e9),
            open_interest=1000, volume=100, iv_source="massive_snapshot").items()})
    row.update(updates)
    return row


def eligible(row, category="highest_premium", now=NOW):
    return assess_row(row, SCAN, now=now)["quality"]["eligibility"][category]["eligible"]


def test_fresh_quotes_qualify():
    assert eligible(candidate())
    result = assess_row(candidate(), SCAN, now=NOW)
    assert result["quality"]["underlying_at"] == "2026-11-12"
    assert result["quality"]["ranking"]["highest_premium"]["saved_score"] == 1.2


@pytest.mark.parametrize("updates", [
    {"spot_source": None}, {"hv_source": None}, {"hv_20": .01}, {"hv_20": 0},
    {"hv_observations": 20}, {"call_open_interest": None}, {"call_volume": 0},
    {"call_ask": 3}, {"call_ask": 3.9}, {"call_iv": .8}, {"call_iv": 0},
    {"call_quote_updated_ns": None}, {"rank_score": 0}, {"expiry": "2026-10-16"},
    {"hv_end_date": "2026-08-25"}, {"call_iv_source": None}, {"spot": float("nan")},
])
def test_unreliable_rows_are_excluded(updates):
    assert not eligible(candidate(**updates))


def test_zero_rank_is_not_replaced_with_raw_richness():
    response = scan_response([candidate(rank_score=0)], SCAN, now=NOW)
    assert response["highest_premium"] == []
    included = scan_response([candidate(rank_score=0)], SCAN, include_flagged=True, now=NOW)
    assert included["highest_premium"][0]["rank_score"] == 0


def test_side_checks_do_not_hide_other_valid_leg():
    row = candidate(put_open_interest=0)
    assert eligible(row, "expensive_calls")
    assert not eligible(row, "expensive_puts")
    assert not eligible(row)


def test_daily_mark_is_labeled_and_can_qualify():
    row = candidate(call_price_source="day_close", call_bid=0, call_ask=0,
                    call_day_updated_ns=int((NOW - timedelta(hours=16)).timestamp() * 1e9))
    result = assess_row(row, SCAN, now=NOW)
    assert result["quality"]["eligibility"]["highest_premium"]["eligible"]
    assert result["quality"]["legs"]["call"]["spread_pct"] is None
    assert any(f["code"] == "call_mark" and not f["blocking"] for f in result["quality"]["flags"])


def test_freshness_changes_without_rescanning():
    row = candidate()
    assert eligible(row)
    assert not eligible(row, now=NOW + timedelta(days=5))


def test_future_timestamp_and_mismatched_times_fail():
    assert not eligible(candidate(call_quote_updated_ns=int((NOW + timedelta(days=1)).timestamp() * 1e9)))
    assert not eligible(candidate(call_quote_updated_ns=int((NOW - timedelta(days=3)).timestamp() * 1e9)))


def test_legacy_rows_do_not_require_database_migration_to_read(monkeypatch):
    with duckdb.connect(":memory:") as conn:
        conn.execute("CREATE TABLE theta_results (scan_id VARCHAR, ticker VARCHAR, avg_premium DOUBLE)")
        conn.execute("INSERT INTO theta_results VALUES ('test', 'SPY', 2)")
        monkeypatch.setattr(db, "get_db", lambda: conn)
        rows = db.get_theta_results("test")
        result = scan_response(rows, SCAN, now=NOW, include_flagged=True)
        assert result["quality_counts"]["highest_premium"] == {"eligible": 0, "total": 1}
        assert result["highest_premium"][0]["hv_20"] is None


def test_provenance_persists_and_schema_migration_is_repeatable(monkeypatch):
    with duckdb.connect(":memory:") as conn:
        db._ensure_schema(conn)
        db._ensure_schema(conn)
        monkeypatch.setattr(db, "get_db", lambda: conn)
        db.save_theta_results("test", [candidate()])
        result = db.get_theta_results("test")[0]
        assert result["hv_observations"] == 21
        assert result["spot_source"] == "massive_daily_unadjusted"
        assert result["call_iv_source"] == "massive_snapshot"
        db.save_theta_scan("test", 35, 20, "2026-12-18", 1, 0, 1.5)
        assert db.get_theta_scan("test")["hv_days"] == 20
        saved_at = datetime.fromisoformat(db.get_theta_scan("test")["created_at"]).replace(tzinfo=timezone.utc)
        assert abs((datetime.now(timezone.utc) - saved_at).total_seconds()) < 10
        assert db.get_theta_scan("missing") is None


def test_hv_needs_n_plus_one_closes_and_is_not_floored():
    closes = [100 + i % 3 for i in range(21)]
    assert screener.compute_hv(closes[:20], 20) == 0
    expected = np.std(np.diff(np.log(closes)), ddof=1) * np.sqrt(252)
    assert screener.compute_hv(closes, 20) == pytest.approx(expected)
    assert screener.compute_hv([100] * 21, 20) == 0
    assert screener.compute_beta(closes, closes, 20) == pytest.approx(1)


def test_scanner_uses_actual_history_and_does_not_copy_failed_iv(monkeypatch):
    dates = [(date.today() - timedelta(days=i)).isoformat() for i in range(25, 0, -1)]
    history = dict(zip(dates, [100 + i % 3 for i in range(25)]))
    monkeypatch.setattr(screener, "stock_history", lambda *a: history)
    monkeypatch.setattr(screener, "daily_closes", lambda *a, **kw: {dates[-1]: 101})
    def snapshots(client, ticker, expiry, side):
        return [dict(strike=100, bid=0, ask=0, last_price=2, iv=.3 if side == "call" else 0,
                     price_source="day_close", open_interest=100, volume=20)]
    monkeypatch.setattr(screener, "fetch_snapshot_for_screener", snapshots)
    monkeypatch.setattr(screener, "_solve_iv", lambda *a: 0)
    row = screener.scan_ticker(object(), "SPY", history, date.today() + timedelta(days=30))
    assert row.spot == 101
    assert row.put_iv == 0
    assert row.put_iv_source == "unavailable"
    assert row.hv_observations == 21
    assert row.hv_source == "massive_daily_adjusted"


def test_http_and_mcp_share_eligibility(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main, theta_mcp
    current = datetime.now(timezone.utc)
    scan = {**SCAN, "created_at": current.isoformat()}
    rows = [candidate(rank_score=0)]
    monkeypatch.setattr(main, "get_latest_theta_scan_by_expiry", lambda *a: scan)
    monkeypatch.setattr(main, "get_theta_results", lambda *a: rows)
    monkeypatch.setattr(theta_mcp, "_resolve_scan", lambda *a: scan)
    monkeypatch.setattr(theta_mcp, "get_theta_results", lambda *a: rows)
    response = TestClient(main.app).get("/theta-plays?expiry=2026-12-18&include_flagged=true")
    assert response.status_code == 200
    mcp = theta_mcp.get_theta_plays(expiry="2026-12-18", include_flagged=True)
    assert response.json()["quality_counts"]["highest_premium"] == mcp["quality_counts"]
    assert mcp["rows"][0]["rank_score"] == 0
    assert theta_mcp.get_theta_plays(expiry="2026-12-18")["rows"] == []


def test_fallback_does_not_substitute_another_expiry():
    from app.main import _try_theta_json_fallback
    assert _try_theta_json_fallback("1900-01-01") is None


def test_adjusted_cache_is_separate_from_raw(tmp_path, monkeypatch):
    from app.data import underlying
    from types import SimpleNamespace
    calls = []
    class Client:
        def list_aggs(self, *args, **kwargs):
            calls.append(kwargs["adjusted"])
            return [SimpleNamespace(timestamp=1735880400000, close=50 if kwargs["adjusted"] else 100)]
    monkeypatch.setattr(underlying, "STOCK_CACHE", tmp_path)
    for adjusted, price in ((False, 100), (True, 50), (True, 50), (False, 100)):
        data = underlying.daily_closes("SPY", date(2025, 1, 3), date(2025, 1, 3), adjusted=adjusted, client=Client())
        assert data == {"2025-01-03": price}
    assert calls == [False, True]


def test_wider_stock_cache_serves_smaller_window(tmp_path, monkeypatch):
    from app.data import underlying
    from types import SimpleNamespace
    calls = []
    class Client:
        def list_aggs(self, *args, **kwargs):
            calls.append(args)
            return [SimpleNamespace(timestamp=1735880400000, close=100)]
    monkeypatch.setattr(underlying, "STOCK_CACHE", tmp_path)
    underlying.daily_closes("SPY", date(2025, 1, 1), date(2025, 1, 10), adjusted=True, client=Client())
    assert underlying.daily_closes("SPY", date(2025, 1, 3), date(2025, 1, 3), adjusted=True, client=Client()) == {"2025-01-03": 100}
    assert len(calls) == 1


def test_bulk_stock_backoff_is_bounded_and_never_caches_partial_results(tmp_path, monkeypatch):
    from app.data import underlying
    from types import SimpleNamespace
    waits, calls = [], []
    class Client:
        def list_aggs(self, *args, **kwargs):
            calls.append(1)
            yield SimpleNamespace(timestamp=1735880400000, close=100)
            if len(calls) <= 2:
                raise RuntimeError("too many 429 error responses")
    monkeypatch.setattr(underlying, "STOCK_CACHE", tmp_path)
    monkeypatch.setattr(underlying.time, "sleep", waits.append)
    with pytest.raises(RuntimeError):
        underlying.daily_closes("SPY", date(2025, 1, 3), date(2025, 1, 3), client=Client())
    assert not list(tmp_path.glob('*.json'))
    assert not waits
    result = underlying.daily_closes("SPY", date(2025, 1, 3), date(2025, 1, 3), client=Client(), rate_limit_retries=1)
    assert result == {"2025-01-03": 100}
    assert waits == [65]


def test_snapshot_requests_larger_pages_without_changing_expiry():
    from app.data.fetcher import fetch_snapshot_for_screener
    calls = []
    class Client:
        def list_snapshot_options_chain(self, ticker, params):
            calls.append(params)
            return []
    assert fetch_snapshot_for_screener(Client(), "SPY", date(2026, 12, 18), rate_limit_sleep=0) == []
    assert calls == [{"expiration_date.gte": "2026-12-18", "expiration_date.lte": "2026-12-18", "contract_type": "call", "limit": 250}]


def test_grouped_close_warmup_is_raw_dated_and_cached(tmp_path, monkeypatch):
    from app.data import underlying
    from types import SimpleNamespace
    calls = []
    class Client:
        def get_grouped_daily_aggs(self, day, adjusted):
            calls.append((day, adjusted))
            return [SimpleNamespace(ticker="SPY", timestamp=1735880400000, close=100),
                    SimpleNamespace(ticker="BAD", timestamp=1735794000000, close=99)]
    monkeypatch.setattr(underlying, "STOCK_CACHE", tmp_path)
    for _ in range(2):
        underlying.prefetch_stock_closes(Client(), ["SPY", "BAD"], date(2025, 1, 3))
    assert calls == [(date(2025, 1, 3), False)]
    assert underlying.daily_closes("SPY", date(2025, 1, 3), date(2025, 1, 3), allow_api=False) == {"2025-01-03": 100}
    assert underlying.daily_closes("SPY", date(2025, 1, 3), date(2025, 1, 3), allow_api=False, adjusted=True) == {}
    assert not (tmp_path / 'BAD_2025-01-03_2025-01-03.json').exists()


def test_old_options_universe_uses_latest_available_window(monkeypatch):
    with duckdb.connect(":memory:") as conn:
        conn.execute("CREATE TABLE options (underlying VARCHAR, trade_date DATE, volume BIGINT)")
        conn.execute("INSERT INTO options VALUES ('OLD', '2020-01-01', 1000000), ('A', '2020-03-01', 200), ('B', '2020-03-01', 300)")
        monkeypatch.setattr(db, "get_db", lambda: conn)
        assert db.get_top_tickers_by_volume(limit=100) == ['B', 'A']
        assert db.get_top_tickers_by_volume(limit=1) == ['B']
        conn.execute("DELETE FROM options")
        assert db.get_top_tickers_by_volume() == []
