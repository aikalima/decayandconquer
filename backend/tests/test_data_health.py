import sys
from datetime import date
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import data_health


@pytest.fixture
def conn(tmp_path, monkeypatch):
    path = tmp_path / "options.duckdb"
    path.touch()
    connection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE options(trade_date DATE)")
    monkeypatch.setattr(data_health.db, "DB_PATH", path)
    monkeypatch.setattr(data_health.db, "get_db", lambda **kw: connection)
    monkeypatch.setattr(data_health.db, "get_available_theta_expiries", lambda: [])
    data_health._coverage.cache_clear()
    yield connection
    connection.close()
    data_health._coverage.cache_clear()


def test_empty_database(conn):
    health = data_health.get_data_health(date(2025, 1, 10))
    assert health["status"] == "empty"
    assert health["options"]["latest_date"] is None


def test_stale_and_unclassified_gaps(conn):
    conn.execute("INSERT INTO options VALUES ('2025-01-06'), ('2025-01-08')")
    health = data_health.get_data_health(date(2025, 1, 20))
    assert health["status"] == "stale"
    assert health["options"]["age_calendar_days"] == 12
    assert health["options"]["unverified_weekday_gaps"] == ["2025-01-07"]
    assert "holidays" in health["coverage_basis"]
    assert health["refresh_status"] == "unknown"


def test_unavailable_not_reported_as_empty(conn, monkeypatch):
    monkeypatch.setattr(data_health.db, "DB_PATH", Path("/not/a/database"))
    assert data_health.get_data_health()["status"] == "unavailable"
