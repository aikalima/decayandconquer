#!/usr/bin/env python3
"""Purge theta scan data from DuckDB.

Usage:
    python purge_theta.py              # delete all theta data
    python purge_theta.py --days 30    # delete only 30-day DTE scans
    python purge_theta.py --dry-run    # show what would be deleted
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.data.db import get_db, close_db


def main():
    parser = argparse.ArgumentParser(description="Purge theta scan data from DuckDB")
    parser.add_argument("--days", type=int, default=None, help="Only purge scans for this DTE (e.g. 30)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    args = parser.parse_args()

    db = get_db(read_only=args.dry_run)

    # Show current state
    scans = db.execute("SELECT scan_id, days_forward, expiry, tickers_scanned, created_at FROM theta_scans ORDER BY created_at DESC").fetchall()
    if not scans:
        print("No theta scans in database.")
        close_db()
        return

    print(f"Found {len(scans)} scan(s):")
    for s in scans:
        print(f"  {s[0]}  DTE={s[1]}  expiry={s[2]}  tickers={s[3]}  {s[4]}")

    if args.days:
        matching = [s for s in scans if s[1] == args.days]
        print(f"\nMatching DTE={args.days}: {len(matching)} scan(s)")
    else:
        matching = scans

    total_results = db.execute("SELECT COUNT(*) FROM theta_results").fetchone()[0]
    print(f"Total result rows: {total_results}")

    if args.dry_run:
        print("\nDry run — no data deleted.")
        close_db()
        return

    if args.days:
        scan_ids = [s[0] for s in matching]
        for sid in scan_ids:
            db.execute("DELETE FROM theta_results WHERE scan_id = ?", [sid])
            db.execute("DELETE FROM theta_scans WHERE scan_id = ?", [sid])
        print(f"\nDeleted {len(scan_ids)} scan(s) for DTE={args.days}")
    else:
        db.execute("DELETE FROM theta_results")
        db.execute("DELETE FROM theta_scans")
        print(f"\nDeleted all theta data ({len(scans)} scans, {total_results} results)")

    close_db()
    print("Done.")


if __name__ == "__main__":
    main()
