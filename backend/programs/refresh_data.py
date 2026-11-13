#!/usr/bin/env python3
"""Build a private DuckDB, validate it, then publish with a brief API restart.

Downloads/imports/scans never write to the database being served. The only
service interruption is the final handover; failed builds leave the API alone.
"""

import argparse
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import duckdb

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.defaults import CONFIG_PATH, build_theta_scan_plan


@contextmanager
def refresh_lock(path: Path):
    # Shared with deploy-gcp.sh, including when this program is invoked directly.
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another refresh or deployment is running") from None
        yield


def options_summary(conn) -> tuple:
    return conn.execute("SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM options").fetchone()


def validate_stage(stage: Path, original: tuple, expiries: list[str], started: datetime) -> tuple:
    with duckdb.connect(str(stage)) as conn:
        current = options_summary(conn)
        if current[0] < original[0] or current[1] != original[1] or current[2] < original[2]:
            raise RuntimeError("Staged options data lost rows or date coverage")
        for expiry in expiries:
            scan = conn.execute("""
                SELECT s.scan_id, s.tickers_scanned - s.tickers_failed, COUNT(r.ticker)
                FROM theta_scans s LEFT JOIN theta_results r USING (scan_id)
                WHERE s.expiry = ? AND s.created_at >= ?
                GROUP BY s.scan_id, s.tickers_scanned, s.tickers_failed, s.created_at
                ORDER BY s.created_at DESC LIMIT 1
            """, [expiry, started]).fetchone()
            if not scan or scan[2] == 0 or scan[1] != scan[2]:
                raise RuntimeError(f"Missing or incomplete fresh theta scan for {expiry}")
        conn.execute("CHECKPOINT")
    if Path(str(stage) + ".wal").exists():
        raise RuntimeError("Staged database still has a WAL; refusing to publish")
    return current


def run_jobs(stage: Path, config: Path, *, options_only: bool, theta_only: bool):
    env = {**os.environ, "DECAY_DB_PATH": str(stage),
           "DECAY_THETA_FALLBACK_PATH": str(stage.parent / "theta_latest.json"),
           "DECAY_DB_MEMORY_LIMIT": os.environ.get("DECAY_REFRESH_MEMORY_LIMIT", "1GB"),
           "DECAY_DB_THREADS": os.environ.get("DECAY_REFRESH_THREADS", "2")}
    commands = []
    if not theta_only:
        commands.append(["programs/update_flat_files.py", "--strict"])
    if not options_only:
        commands.append(["programs/run_theta_scan.py", "--config", str(config)])
    for command in commands:
        subprocess.run([sys.executable, "-u", *command], cwd=BACKEND_DIR, env=env, check=True)


def service_action(action: str, service: str):
    subprocess.run(["sudo", "-n", "systemctl", action, service], check=True, timeout=90)


def scan_times(path: Path) -> dict:
    with duckdb.connect(str(path), read_only=True) as conn:
        return dict(conn.execute("SELECT CAST(expiry AS VARCHAR), MAX(created_at) FROM theta_scans GROUP BY expiry").fetchall())


def wait_for_health(url: str, expected: tuple, expected_scans: dict, *, timeout: float = 60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=3) as response:
                payload = json.load(response)
            options = payload.get("options") or {}
            actual_scans = {s["expiry"]: datetime.fromisoformat(s["last_scanned"]).replace(tzinfo=None)
                            for s in payload.get("theta_scans", []) if s.get("last_scanned")}
            if (options.get("rows") == expected[0] and options.get("latest_date") == str(expected[2])
                    and actual_scans == expected_scans):
                return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError("API did not serve the expected database after restart")


def sync_path(path: Path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish(stage: Path, live: Path, service: str, health_url: str,
            original: tuple, expected: tuple):
    backup = stage.parent / "previous.duckdb"
    original_scans, expected_scans = scan_times(live), scan_times(stage)
    # A hard link preserves the old inode without another full-size copy.
    os.link(live, backup)
    sync_path(stage)
    sync_path(stage.parent)
    swapped = False
    handover_started = time.monotonic()
    try:
        print("Validated. Briefly stopping API to publish...", flush=True)
        service_action("stop", service)
        os.replace(stage, live)
        swapped = True
        sync_path(live.parent)
        service_action("start", service)
        wait_for_health(health_url, expected, expected_scans)
    except BaseException:
        print("Publication failed; recovering the previous database and API...", flush=True)
        if swapped:
            service_action("stop", service)
            os.replace(backup, live)
            sync_path(live.parent)
        service_action("start", service)
        wait_for_health(health_url, original, original_scans)
        backup.unlink(missing_ok=True)
        raise
    backup.unlink()
    print(f"API handover verified in {time.monotonic() - handover_started:.1f}s", flush=True)


def refresh(live: Path, config: Path, *, service: str, health_url: str,
            options_only: bool = False, theta_only: bool = False,
            reserve_bytes: int = 2 * 1024**3):
    live = live.resolve(strict=True)  # Preserve the backend's symlink to /data.
    if not live.is_file() or live.stat().st_size == 0:
        raise RuntimeError("Live database is missing or empty")
    needed = live.stat().st_size + reserve_bytes
    free = shutil.disk_usage(live.parent).free
    if free < needed:
        raise RuntimeError(f"Insufficient disk space: need {needed / 1024**3:.1f} GiB free, have {free / 1024**3:.1f} GiB")
    expiries = [] if options_only else [s["expiry"] for s in build_theta_scan_plan(config)]
    if not options_only and not expiries:
        raise RuntimeError("No theta scans configured")
    workspace = Path(tempfile.mkdtemp(prefix=".decay-refresh-", dir=live.parent))
    stage = workspace / "options.duckdb"
    started = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        # Holding a read lock prevents another process from modifying the source
        # during the copy/build. Other read-only API workers remain unaffected.
        with duckdb.connect(str(live), read_only=True) as source:
            if Path(str(live) + ".wal").exists():
                raise RuntimeError("Live DB has an outstanding WAL; checkpoint it before refreshing")
            original = options_summary(source)
            if not original[0] or not original[2]:
                raise RuntimeError("Live options database is empty")
            print(f"Building {stage}; live API stays online", flush=True)
            shutil.copy2(live, stage)
            run_jobs(stage, config.resolve(), options_only=options_only, theta_only=theta_only)
            expected = validate_stage(stage, original, expiries, started)
            publish(stage, live, service, health_url, original, expected)
        print(f"Refresh published: {expected[0]:,} rows through {expected[2]}; {len(expiries)} scans validated", flush=True)
    finally:
        if (workspace / "previous.duckdb").exists():
            print(f"Recovery files preserved at {workspace}; check API health before further refreshes", file=sys.stderr)
        else:
            shutil.rmtree(workspace)


def main():
    from programs.download_flat_files import load_project_env
    load_project_env()
    from app.data.db import DB_PATH

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--service", default="decay-api")
    parser.add_argument("--health-url", default="http://127.0.0.1:6173/data-health")
    parser.add_argument("--lock-file", type=Path, default=Path("/tmp/decay-cron.lock"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--options-only", action="store_true")
    mode.add_argument("--theta-only", action="store_true")
    args = parser.parse_args()

    def interrupted(signum, frame):
        raise KeyboardInterrupt("Refresh interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    with refresh_lock(args.lock_file):
        subprocess.run(["systemctl", "is-active", "--quiet", args.service], check=True)
        refresh(args.db, args.config, service=args.service, health_url=args.health_url,
                options_only=args.options_only, theta_only=args.theta_only)


if __name__ == "__main__":
    main()
