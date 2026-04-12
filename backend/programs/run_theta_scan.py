#!/usr/bin/env python3
"""Run a theta plays scan and store results in DuckDB.

Scans a watchlist of tickers for overpriced options premium (IV vs HV),
saves results to the theta_scans and theta_results tables.

Usage:
    python run_theta_scan.py                        # default 30 tickers, 30 DTE
    python run_theta_scan.py --days-forward 45      # 45 DTE
    python run_theta_scan.py --tickers AAPL,MSFT    # specific tickers
    python run_theta_scan.py --hv-days 30           # 30-day HV lookback
"""

import argparse
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env from project root
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip("'\""))

from app.screener import scan_all, DEFAULT_TICKERS, ScreenerRow
from app.data.db import (
    get_db,
    check_db_writable,
    save_theta_scan,
    save_theta_results,
    get_latest_theta_scan,
    get_top_tickers_by_volume,
    close_db,
)


def main():
    parser = argparse.ArgumentParser(description="Run theta plays scan")
    parser.add_argument("--api-key", type=str, default=None, help="Massive API key (default: MASSIVE_API_KEY env var)")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated tickers")
    parser.add_argument("--top", type=int, default=None, help="Scan top N tickers by options volume from DB (e.g. --top 500)")
    parser.add_argument("--days-forward", type=int, default=30, help="Target DTE (default: 30)")
    parser.add_argument("--hv-days", type=int, default=None, help="HV lookback days (default: matches --days-forward)")
    args = parser.parse_args()

    # Match HV lookback to DTE if not explicitly set
    if args.hv_days is None:
        args.hv_days = args.days_forward

    # Set API key if provided via flag
    if args.api_key:
        os.environ["MASSIVE_API_KEY"] = args.api_key

    # Open DB read-only so the scan works while the server is running
    get_db(read_only=True)

    if args.tickers:
        ticker_list = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.top:
        print(f"Querying top {args.top} tickers by volume from DB...")
        ticker_list = get_top_tickers_by_volume(limit=args.top)
        print(f"Found {len(ticker_list)} tickers")
    else:
        ticker_list = DEFAULT_TICKERS

    scan_id = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    print(f"Scan ID:      {scan_id}")
    print(f"Tickers:      {len(ticker_list)}")
    print(f"DTE:          {args.days_forward} days")
    print(f"HV lookback:  {args.hv_days} days")
    print()

    start = time.time()
    results: list[ScreenerRow] = []
    failed: list[str] = []
    expiry = ""

    for item in scan_all(ticker_list, args.days_forward, args.hv_days):
        if isinstance(item, dict):
            # Final summary from generator
            expiry = item["expiry"]
            failed = item["tickers_failed"]
        else:
            stage, progress, row = item
            status = f"OK  premium={row.avg_premium:.2f}x" if row else "FAILED"
            print(f"  [{progress:3d}%] {stage}  {status}")
            if row:
                results.append(row)

    elapsed = time.time() - start

    print()
    print(f"Scan complete in {elapsed:.1f}s")
    print(f"  Succeeded: {len(results)}")
    print(f"  Failed:    {len(failed)} {failed if failed else ''}")
    print(f"  Expiry:    {expiry}")

    if not results:
        print("\nNo results to save.")
        close_db()
        return

    # Check if DB is writable before attempting save
    close_db()
    ok, msg = check_db_writable()
    if not ok:
        print(f"\nWARNING: {msg}")
    try:
        get_db(read_only=False)
    except Exception as e:
        # Fallback: save to JSON file
        import json
        fallback = Path(__file__).parent / "app" / "data" / "theta_latest.json"
        payload = {
            "scan_id": scan_id, "days_forward": args.days_forward, "hv_days": args.hv_days,
            "expiry": expiry, "tickers_scanned": len(ticker_list), "tickers_failed": len(failed),
            "scan_time_seconds": round(elapsed, 1),
            "results": [asdict(r) for r in results],
        }
        fallback.write_text(json.dumps(payload, indent=2))
        print(f"\nCannot write to DuckDB (server running?): {e}")
        print(f"Results saved to {fallback}")
        print("Stop the server and run: python import_theta_json.py")
        return

    print(f"\nSaving to DuckDB...")
    save_theta_scan(
        scan_id=scan_id,
        days_forward=args.days_forward,
        hv_days=args.hv_days,
        expiry=expiry,
        tickers_scanned=len(ticker_list),
        tickers_failed=len(failed),
        scan_time_seconds=round(elapsed, 1),
    )
    save_theta_results(scan_id, [asdict(r) for r in results])

    print(f"Saved {len(results)} results under scan_id={scan_id}")

    # Show top 5
    print("\nTop 5 by Premium (IV/HV):")
    top = sorted(results, key=lambda r: r.avg_premium, reverse=True)[:5]
    print(f"  {'Ticker':<8} {'Spot':>8} {'IV':>7} {'HV':>7} {'Premium':>8} {'Beta':>6}")
    for r in top:
        avg_iv = (r.call_iv + r.put_iv) / 2 * 100
        print(f"  {r.ticker:<8} ${r.spot:>7.0f} {avg_iv:>6.1f}% {r.hv_20*100:>6.1f}% {r.avg_premium:>7.2f}x {r.beta:>5.2f}")

    close_db()
    print("\nDone.")


if __name__ == "__main__":
    main()
