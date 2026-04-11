#!/usr/bin/env python3
"""Download and import newest flat files into DuckDB.

Determines the latest flat file in app/data/flat_files/, downloads all
trading days from the day after that up to today, and imports them.

Usage:
    python update_flat_files.py                # download + import new files
    python update_flat_files.py --dry-run      # show what would be downloaded
    python update_flat_files.py --download-only # download but don't import
"""

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from download_flat_files import get_s3_client, download_file, date_to_key

FLAT_FILES_DIR = Path(__file__).parent / "app" / "data" / "flat_files"


def find_latest_in_db() -> date | None:
    """Find the most recent trade_date actually imported into DuckDB."""
    try:
        from app.data.db import get_db
        conn = get_db()
        result = conn.execute("SELECT MAX(trade_date) FROM options").fetchone()
        if result and result[0]:
            return date.fromisoformat(str(result[0]))
    except Exception:
        pass
    return None


def find_latest_local_file() -> date | None:
    """Find the most recent flat file date on disk (fallback)."""
    files = sorted(FLAT_FILES_DIR.glob("*.csv.gz"))
    if not files:
        return None
    latest = None
    for f in files:
        try:
            d = date.fromisoformat(f.stem.replace(".csv", ""))
            if latest is None or d > latest:
                latest = d
        except ValueError:
            continue
    return latest


def trading_days_between(start: date, end: date) -> list[date]:
    """Generate potential trading days (weekdays) between start and end exclusive/inclusive."""
    days = []
    current = start + timedelta(days=1)
    while current <= end:
        # Skip weekends
        if current.weekday() < 5:  # Mon=0, Fri=4
            days.append(current)
        current += timedelta(days=1)
    return days


def main():
    parser = argparse.ArgumentParser(description="Download and import newest flat files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded")
    parser.add_argument("--download-only", action="store_true", help="Download but don't import")
    parser.add_argument("--up-to", type=str, default=None, help="End date (default: today)")
    args = parser.parse_args()

    FLAT_FILES_DIR.mkdir(parents=True, exist_ok=True)

    # Use DB as source of truth; fall back to filesystem
    try:
        latest = find_latest_in_db()
        source = "DB"
    except Exception:
        latest = None
        source = "DB (unavailable)"

    if latest is None:
        latest = find_latest_local_file()
        source = "filesystem (DB unavailable or empty)"
    if latest is None:
        print("No existing data found. Use download_flat_files.py for initial bulk download.")
        sys.exit(1)

    # Close DB so the backend can keep running during download
    try:
        from app.data.db import close_db
        close_db()
    except Exception:
        pass

    end_date = date.fromisoformat(args.up_to) if args.up_to else date.today()

    # Don't try to download today if it's before market close (or weekend)
    # S3 files typically appear after market close, so skip today
    if end_date >= date.today():
        end_date = date.today() - timedelta(days=1)

    print(f"Latest data ({source}): {latest}")
    print(f"Downloading up to: {end_date}")

    if latest >= end_date:
        print("Already up to date!")
        return

    candidates = trading_days_between(latest, end_date)
    if not candidates:
        print("No new trading days to download.")
        return

    print(f"Found {len(candidates)} potential trading days to download")
    print()

    if args.dry_run:
        for d in candidates:
            key = date_to_key(d)
            local = FLAT_FILES_DIR / f"{d.isoformat()}.csv.gz"
            status = "EXISTS" if local.exists() else "DOWNLOAD"
            print(f"  {status}  {d.isoformat()}  {key}")
        return

    # Download
    client = get_s3_client()
    downloaded = []
    failed = []

    for i, d in enumerate(candidates, 1):
        key = date_to_key(d)
        local = FLAT_FILES_DIR / f"{d.isoformat()}.csv.gz"

        if local.exists():
            print(f"[{i}/{len(candidates)}]  SKIP {d.isoformat()} (exists)")
            downloaded.append(local)
            continue

        print(f"[{i}/{len(candidates)}]", end="")
        try:
            download_file(client, key, FLAT_FILES_DIR)
            if local.exists():
                downloaded.append(local)
            else:
                # File might not exist on S3 (holiday)
                print(f"  MISSING {d.isoformat()} (probably a holiday)")
                failed.append(d)
        except Exception as e:
            print(f"  FAILED {d.isoformat()}: {e}")
            failed.append(d)

    print()
    print(f"Downloaded: {len(downloaded)} files")
    if failed:
        print(f"Missing/failed: {len(failed)} ({', '.join(str(d) for d in failed)})")

    if args.download_only:
        print("Skipping import (--download-only)")
        return

    # Import new files into DuckDB
    new_files = [f for f in downloaded if f.exists()]
    if not new_files:
        print("No new files to import.")
        return

    print()
    print(f"Importing {len(new_files)} files into DuckDB...")

    from app.data.db import import_flat_file, get_stats, close_db

    start = time.time()
    total_rows = 0
    for i, f in enumerate(new_files, 1):
        print(f"[{i}/{len(new_files)}] ", end="", flush=True)
        try:
            total_rows += import_flat_file(f)
        except Exception as e:
            print(f"  IMPORT FAILED {f.name}: {e}")

    elapsed = time.time() - start
    print()
    print(f"Imported {total_rows:,} rows in {elapsed:.1f}s")

    # Show updated stats
    stats = get_stats()
    print(f"DB total:   {stats['rows']:,} rows")
    print(f"Date range: {stats['date_range']}")
    print(f"Tickers:    {len(stats['tickers'])} unique")
    close_db()


if __name__ == "__main__":
    main()
