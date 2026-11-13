"""Staged refreshes must never interrupt serving while doing batch work."""

import io
import gzip
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.data import db
from programs import refresh_data as refresh
from programs import update_flat_files as update


@pytest.fixture
def live(tmp_path):
    path = tmp_path / "live.duckdb"
    with duckdb.connect(str(path)) as conn:
        conn.execute("CREATE TABLE options (trade_date DATE)")
        conn.execute("INSERT INTO options VALUES ('2026-11-11')")
        conn.execute("CREATE TABLE theta_scans (scan_id VARCHAR, expiry DATE, created_at TIMESTAMP, tickers_scanned INT, tickers_failed INT)")
        conn.execute("CREATE TABLE theta_results (scan_id VARCHAR, ticker VARCHAR)")
    return path


def read_count_in_other_process(path):
    result = subprocess.run([sys.executable, "-c",
        "import duckdb,sys; c=duckdb.connect(sys.argv[1],read_only=True); print(c.execute('SELECT COUNT(*) FROM options').fetchone()[0])",
        str(path)], check=True, capture_output=True, text=True)
    return int(result.stdout.strip())


def add_rows(stage, **kwargs):
    with duckdb.connect(str(stage)) as conn:
        conn.execute("INSERT INTO options VALUES ('2026-11-12')")


def test_live_database_remains_readable_during_build_and_handover(live, monkeypatch):
    actions = []
    link = live.parent / "backend-link.duckdb"
    link.symlink_to(live)

    def jobs(stage, config, **kwargs):
        assert stage != live and not actions
        add_rows(stage)
        assert read_count_in_other_process(live) == 1

    def healthy(url, expected, scans):
        assert read_count_in_other_process(live) == expected[0] == 2
        assert actions == ["stop", "start"]

    monkeypatch.setattr(refresh, "run_jobs", jobs)
    monkeypatch.setattr(refresh, "service_action", lambda action, service: actions.append(action))
    monkeypatch.setattr(refresh, "wait_for_health", healthy)
    refresh.refresh(link, Path("unused"), service="test", health_url="test", options_only=True, reserve_bytes=0)
    assert link.is_symlink() and read_count_in_other_process(link) == 2
    assert not list(live.parent.glob(".decay-refresh-*"))


@pytest.mark.parametrize("failure", [RuntimeError("download failed"), KeyboardInterrupt()])
def test_failed_or_cancelled_build_never_touches_api_or_live_db(live, monkeypatch, failure):
    def jobs(stage, config, **kwargs):
        add_rows(stage)
        raise failure

    monkeypatch.setattr(refresh, "run_jobs", jobs)
    monkeypatch.setattr(refresh, "service_action", lambda *a: pytest.fail("API must stay running"))
    with pytest.raises(type(failure)):
        refresh.refresh(live, Path("unused"), service="test", health_url="test", options_only=True, reserve_bytes=0)
    assert read_count_in_other_process(live) == 1
    assert not list(live.parent.glob(".decay-refresh-*"))


def test_health_failure_rolls_back_database_and_restarts_api(live, monkeypatch):
    actions, checks = [], []
    monkeypatch.setattr(refresh, "run_jobs", lambda stage, config, **kw: add_rows(stage))
    monkeypatch.setattr(refresh, "service_action", lambda action, service: actions.append(action))

    def healthy(url, expected, scans):
        checks.append(expected[0])
        assert read_count_in_other_process(live) == expected[0]
        if len(checks) == 1:
            raise RuntimeError("unhealthy new API")

    monkeypatch.setattr(refresh, "wait_for_health", healthy)
    with pytest.raises(RuntimeError, match="unhealthy"):
        refresh.refresh(live, Path("unused"), service="test", health_url="test", options_only=True, reserve_bytes=0)
    assert checks == [2, 1]
    assert actions == ["stop", "start", "stop", "start"]
    assert not list(live.parent.glob(".decay-refresh-*"))


def test_failed_rollback_preserves_recovery_copy(live, monkeypatch):
    calls = []
    monkeypatch.setattr(refresh, "run_jobs", lambda stage, config, **kw: add_rows(stage))

    def action(action, service):
        calls.append(action)
        if len(calls) >= 2:
            raise RuntimeError("service failure")

    monkeypatch.setattr(refresh, "service_action", action)
    with pytest.raises(RuntimeError):
        refresh.refresh(live, Path("unused"), service="test", health_url="test", options_only=True, reserve_bytes=0)
    backup, = live.parent.glob(".decay-refresh-*/previous.duckdb")
    assert read_count_in_other_process(backup) == 1


def test_disk_guard_fails_before_copy_or_service_change(live, monkeypatch):
    monkeypatch.setattr(refresh.shutil, "disk_usage", lambda path: SimpleNamespace(free=1))
    monkeypatch.setattr(refresh, "run_jobs", lambda *a, **kw: pytest.fail("no space"))
    with pytest.raises(RuntimeError, match="disk space"):
        refresh.refresh(live, Path("unused"), service="test", health_url="test", options_only=True)
    assert not list(live.parent.glob(".decay-refresh-*"))


def test_shared_lock_rejects_overlap(tmp_path):
    with refresh.refresh_lock(tmp_path / "job.lock"):
        with pytest.raises(RuntimeError, match="Another refresh"):
            with refresh.refresh_lock(tmp_path / "job.lock"):
                pytest.fail("must not acquire twice")


def test_stage_must_have_complete_fresh_scan(live):
    original = (1, date(2026, 11, 11), date(2026, 11, 11))
    started = datetime.now()
    expiry = "2027-01-15"
    with pytest.raises(RuntimeError, match="Missing or incomplete"):
        refresh.validate_stage(live, original, [expiry], started)
    with duckdb.connect(str(live)) as conn:
        conn.execute("INSERT INTO theta_scans VALUES ('new', ?, ?, 2, 0)", [expiry, started + timedelta(seconds=1)])
        conn.execute("INSERT INTO theta_results VALUES ('new', 'SPY')")
    with pytest.raises(RuntimeError, match="Missing or incomplete"):
        refresh.validate_stage(live, original, [expiry], started)
    with duckdb.connect(str(live)) as conn:
        conn.execute("INSERT INTO theta_results VALUES ('new', 'QQQ')")
    assert refresh.validate_stage(live, original, [expiry], started) == original
    with pytest.raises(RuntimeError, match="Missing or incomplete"):
        refresh.validate_stage(live, original, [expiry], started + timedelta(days=1))


def test_stage_cannot_drop_history(live):
    with pytest.raises(RuntimeError, match="lost rows"):
        refresh.validate_stage(live, (2, date(2026, 11, 11), date(2026, 11, 12)), [], datetime.now())


def test_jobs_are_isolated_and_fail_fast(tmp_path, monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(refresh.subprocess, "run", run)
    stage = tmp_path / "stage.duckdb"
    with pytest.raises(subprocess.CalledProcessError):
        refresh.run_jobs(stage, tmp_path / "config.json", options_only=False, theta_only=False)
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert "--strict" in command
    assert kwargs["env"]["DECAY_DB_PATH"] == str(stage)
    assert kwargs["env"]["DECAY_THETA_FALLBACK_PATH"].startswith(str(tmp_path))
    assert kwargs["env"]["DECAY_DB_MEMORY_LIMIT"] == "1GB"


def test_db_path_override_is_respected_by_worker(live):
    output = subprocess.check_output([sys.executable, "-c",
        "from app.data.db import DB_PATH,get_db; print(DB_PATH); print(get_db(read_only=True).execute('select count(*) from options').fetchone()[0])"],
        cwd=refresh.BACKEND_DIR, env={**os.environ, "DECAY_DB_PATH": str(live)}, text=True)
    assert output.splitlines() == [str(live), "1"]


def test_health_check_rejects_old_scan_metadata(monkeypatch):
    stamp = datetime(2026, 11, 13, 12)
    payload = {"options": {"rows": 1, "latest_date": "2026-11-12"}, "theta_scans": []}
    monkeypatch.setattr(refresh, "urlopen", lambda *a, **kw: io.BytesIO(json.dumps(payload).encode()))
    monkeypatch.setattr(refresh.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="expected database"):
        refresh.wait_for_health("unused", (1, None, date(2026, 11, 12)), {"2026-12-18": stamp}, timeout=.01)
    payload["theta_scans"] = [{"expiry": "2026-12-18", "last_scanned": stamp.isoformat() + "+00:00"}]
    refresh.wait_for_health("unused", (1, None, date(2026, 11, 12)), {"2026-12-18": stamp}, timeout=.1)


@pytest.fixture
def strict_update(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["update_flat_files.py", "--strict", "--up-to", "2026-06-25"])
    monkeypatch.setattr(update, "FLAT_FILES_DIR", tmp_path)
    monkeypatch.setattr(update, "find_latest_in_db", lambda: date(2026, 6, 23))
    monkeypatch.setattr(update, "get_s3_client", lambda: object())
    monkeypatch.setattr(update, "list_files", lambda *a: [update.date_to_key(date(2026, 6, 24))])
    monkeypatch.setattr(db, "close_db", lambda: None)
    return tmp_path


def test_strict_mode_requires_live_db_not_filesystem_fallback(strict_update, monkeypatch):
    monkeypatch.setattr(update, "find_latest_in_db", lambda: None)
    monkeypatch.setattr(update, "find_latest_local_file", lambda: pytest.fail("no fallback"))
    with pytest.raises(RuntimeError, match="nonempty"):
        update.main()


def test_strict_mode_aborts_on_download_failure(strict_update, monkeypatch):
    def fail(*args):
        raise RuntimeError("403")
    monkeypatch.setattr(update, "download_file", fail)
    with pytest.raises(RuntimeError, match="Download failed"):
        update.main()


def test_strict_mode_aborts_on_import_failure(strict_update, monkeypatch):
    (strict_update / "2026-06-24.csv.gz").touch()
    monkeypatch.setattr(db, "check_db_writable", lambda: (True, "ok"))
    def fail(*args):
        raise RuntimeError("corrupt file")
    monkeypatch.setattr(db, "import_flat_file", fail)
    with pytest.raises(RuntimeError, match="Import failed"):
        update.main()


def test_strict_mode_skips_unpublished_dates(strict_update, monkeypatch):
    monkeypatch.setattr(update, "list_files", lambda *a: [])
    monkeypatch.setattr(update, "download_file", lambda *a: pytest.fail("no published files"))
    update.main()


def test_strict_mode_aborts_if_listing_is_forbidden(strict_update, monkeypatch):
    def fail(*args):
        raise RuntimeError("S3 listing forbidden")
    monkeypatch.setattr(update, "list_files", fail)
    with pytest.raises(RuntimeError, match="listing forbidden"):
        update.main()


def test_strict_update_imports_a_real_gzip_into_selected_database(tmp_path, monkeypatch):
    path = tmp_path / "options.duckdb"
    monkeypatch.setattr(db, "DB_PATH", path)
    monkeypatch.setattr(db, "_connection", None)
    monkeypatch.setattr(db, "_default_read_only", False)
    with duckdb.connect(str(path)) as conn:
        db._ensure_schema(conn)
        conn.execute("INSERT INTO options (underlying, expiry, contract_type, strike, ticker, trade_date) VALUES ('SPY', '2026-12-18', 'C', 100, 'O:SPY261218C00100000', '2026-06-23')")
    day = date(2026, 6, 24)
    epoch_ns = int(datetime(2026, 6, 24, tzinfo=timezone.utc).timestamp() * 1e9)
    with gzip.open(tmp_path / f"{day}.csv.gz", "wt") as handle:
        handle.write("ticker,volume,open,close,high,low,window_start,transactions\n")
        handle.write(f"O:SPY261218C00100000,100,5,6,7,4,{epoch_ns},20\n")
    monkeypatch.setattr(sys, "argv", ["update_flat_files.py", "--strict", "--up-to", str(day)])
    monkeypatch.setattr(update, "FLAT_FILES_DIR", tmp_path)
    monkeypatch.setattr(update, "get_s3_client", lambda: object())
    monkeypatch.setattr(update, "list_files", lambda *a: [update.date_to_key(day)])
    try:
        update.main()
        with duckdb.connect(str(path), read_only=True) as conn:
            assert refresh.options_summary(conn) == (2, date(2026, 6, 23), day)
        update.main()  # Already-current reruns must not duplicate rows.
    finally:
        db.close_db()
