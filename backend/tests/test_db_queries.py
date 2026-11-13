"""Query optimizations must preserve results without changing stored data."""

import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.data import db
from programs.benchmark_queries import full_history_daily_closes


@pytest.fixture
def conn(monkeypatch):
    connection = duckdb.connect(":memory:")
    connection.execute("""
        CREATE TABLE options (
            underlying VARCHAR, trade_date DATE, contract_type VARCHAR,
            strike DOUBLE, close DOUBLE, expiry DATE, ticker VARCHAR
        )
    """)
    monkeypatch.setattr(db, "get_db", lambda: connection)
    yield connection
    connection.close()


def add_history(conn, ticker, start, offsets):
    rows = []
    for offset in offsets:
        day = start + timedelta(days=offset)
        rows.extend([
            (ticker, day, "C", 10, 90 + offset),
            (ticker, day, "C", 20, 81 + offset),
            (ticker, day, "C", 1, 0),
            (ticker, day, "C", 2, None),
            (ticker, day, "P", 1, 1000),
        ])
    conn.executemany("INSERT INTO options VALUES (?, ?, ?, ?, ?, '2030-01-18', 'contract')", rows)


@pytest.mark.parametrize("days", [1, 5, 30, 180, 500])
def test_daily_closes_matches_full_history(conn, days):
    # Deliberately old data: optimization must not depend on today's date.
    add_history(conn, "SPY", date(2020, 1, 1), range(400))
    assert db.query_daily_closes("SPY", days) == full_history_daily_closes(conn, "SPY", days)


def test_sparse_history_falls_back(conn):
    add_history(conn, "SPARSE", date(2020, 1, 1), [0, 100, 200, 300, 399])
    assert db.query_daily_closes("SPARSE", 5) == full_history_daily_closes(conn, "SPARSE", 5)
    assert len(db.query_daily_closes("SPARSE", 5)) == 5


def test_inactive_ticker_and_short_history(conn):
    add_history(conn, "OLD", date(2010, 1, 1), [0, 1, 2])
    add_history(conn, "NEW", date(2020, 1, 1), [0])
    assert db.query_daily_closes("OLD", 30) == full_history_daily_closes(conn, "OLD", 30)
    assert db.query_daily_closes("MISSING", 30) == []


def test_empty_and_zero_days(conn):
    assert db.query_daily_closes("SPY", 5) == []
    assert db.query_daily_closes("SPY", 0) == []
    with pytest.raises(ValueError, match="non-negative"):
        db.query_daily_closes("SPY", -1)


def test_existence_includes_nonpositive_prices_and_puts(conn):
    assert not db.has_data("SPY", "2020-01-01")
    conn.execute("INSERT INTO options VALUES ('SPY', '2020-01-01', 'P', 1, 0, '2030-01-18', 'contract')")
    assert db.has_data("SPY", date(2020, 1, 1))
    assert not db.has_data("SPY", "2020-01-02")
    assert not db.has_data("OTHER", "2020-01-01")


def test_new_import_is_visible_without_cache_invalidation(conn):
    add_history(conn, "SPY", date(2020, 1, 1), [0, 1])
    before = db.query_daily_closes("SPY", 1)
    add_history(conn, "SPY", date(2021, 1, 1), [0])
    after = db.query_daily_closes("SPY", 1)
    assert before != after
    assert after == full_history_daily_closes(conn, "SPY", 1)


def test_equal_strikes_have_deterministic_tiebreak(conn):
    conn.execute("""
        INSERT INTO options VALUES
        ('SPY', '2020-01-01', 'C', 10, 95, '2021-02-19', 'later'),
        ('SPY', '2020-01-01', 'C', 10, 92, '2021-01-15', 'B'),
        ('SPY', '2020-01-01', 'C', 10, 90, '2021-01-15', 'A')
    """)
    for _ in range(3):
        assert db.query_daily_closes("SPY", 1) == [("2020-01-01", 100.0)]


def test_queries_work_on_read_only_database(tmp_path, monkeypatch):
    path = tmp_path / "options.duckdb"
    with duckdb.connect(str(path)) as writable:
        writable.execute("""
            CREATE TABLE options AS SELECT 'SPY' AS underlying,
                DATE '2020-01-01' AS trade_date, 'C' AS contract_type,
                10.0 AS strike, 90.0 AS close,
                DATE '2021-01-15' AS expiry, 'contract' AS ticker
        """)
    before = path.stat()
    with duckdb.connect(str(path), read_only=True) as readonly:
        monkeypatch.setattr(db, "get_db", lambda: readonly)
        assert db.query_daily_closes("SPY", 5) == [("2020-01-01", 100.0)]
        assert db.has_data("SPY", "2020-01-01")
    assert path.stat().st_size == before.st_size
    assert path.stat().st_mtime_ns == before.st_mtime_ns
