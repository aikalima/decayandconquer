#!/usr/bin/env python3
"""Run a theta plays scan and store results in DuckDB.

Scans a watchlist of tickers for overpriced options premium (IV vs HV),
saves results to the theta_scans and theta_results tables.

Usage:
    python run_theta_scan.py                        # default 30 tickers, 30 DTE
    python run_theta_scan.py --days-forward 45      # 45 DTE
    python run_theta_scan.py --tickers AAPL,MSFT    # specific tickers
    python run_theta_scan.py --hv-days 30           # 30-day HV lookback
    python run_theta_scan.py --config config/theta_scans.yaml --dry-run
    python run_theta_scan.py --config config/theta_scans.yaml
"""

import argparse
import os
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

sys.path.insert(0, str(BACKEND_DIR))

# Load .env from project root
_env_path = PROJECT_ROOT / ".env"
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


def _ticker_list_from_config(value: object) -> str | list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(t).strip().upper() for t in value if str(t).strip()]
    return str(value)


def _parse_config_date(value: object, label: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{label}: expected YYYY-MM-DD date, got {value!r}") from exc


def _resolve_days_forward(scan: dict, label: str) -> int:
    if "days_forward" in scan and scan["days_forward"] is not None:
        days_forward = int(scan["days_forward"])
    else:
        expiry_value = scan.get("expiry") or scan.get("date") or scan.get("target_date")
        if not expiry_value:
            raise ValueError(f"{label}: set either expiry or days_forward")
        days_forward = (_parse_config_date(expiry_value, label) - date.today()).days

    if days_forward <= 0:
        raise ValueError(f"{label}: days_forward must be positive, got {days_forward}")
    return days_forward


def _resolve_hv_days(value: object, days_forward: int) -> int:
    if value in (None, "", "same_as_days_forward"):
        return days_forward
    return int(value)


def _read_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML is required for --config. Run: pip install -r requirements.txt") from exc

    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML object")
    return data


def _merged_config_value(scan: dict, defaults: dict, key: str, fallback: object = None) -> object:
    return scan[key] if key in scan else defaults.get(key, fallback)


def _systemctl(action: str, service: str) -> None:
    print(f"\n{action.capitalize()}ing {service}...")
    subprocess.run(["sudo", "systemctl", action, service], check=True)


def run_theta_scan(
    *,
    api_key: str | None = None,
    tickers: str | list[str] | None = None,
    top: int | None = None,
    days_forward: int = 30,
    hv_days: int | None = None,
) -> bool:
    # Match HV lookback to DTE if not explicitly set
    if hv_days is None:
        hv_days = days_forward

    # Set API key if provided via flag
    if api_key:
        os.environ["MASSIVE_API_KEY"] = api_key

    # Open DB read-only so the scan works while the server is running
    get_db(read_only=True)

    if tickers:
        if isinstance(tickers, list):
            ticker_list = [t.strip().upper() for t in tickers if t.strip()]
        else:
            ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    elif top:
        print(f"Querying top {top} tickers by volume from DB...")
        ticker_list = get_top_tickers_by_volume(limit=top)
        print(f"Found {len(ticker_list)} tickers")
    else:
        ticker_list = DEFAULT_TICKERS

    scan_id = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    print(f"Scan ID:      {scan_id}")
    print(f"Tickers:      {len(ticker_list)}")
    print(f"DTE:          {days_forward} days")
    print(f"HV lookback:  {hv_days} days")
    print()

    start = time.time()
    results: list[ScreenerRow] = []
    failed: list[str] = []
    expiry = ""

    for item in scan_all(ticker_list, days_forward, hv_days):
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
        return False

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
        fallback = Path(__file__).parent.parent / "app" / "data" / "theta_latest.json"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "scan_id": scan_id, "days_forward": days_forward, "hv_days": hv_days,
            "expiry": expiry, "tickers_scanned": len(ticker_list), "tickers_failed": len(failed),
            "scan_time_seconds": round(elapsed, 1),
            "results": [asdict(r) for r in results],
        }
        fallback.write_text(json.dumps(payload, indent=2))
        print(f"\nCannot write to DuckDB (server running?): {e}")
        print(f"Results saved to {fallback}")
        print("Stop the server and run: python import_theta_json.py")
        return False

    print(f"\nSaving to DuckDB...")
    save_theta_scan(
        scan_id=scan_id,
        days_forward=days_forward,
        hv_days=hv_days,
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
    return True


def run_theta_scans_from_config(config_path: Path, *, api_key: str | None = None, dry_run: bool = False) -> bool:
    config = _read_yaml(config_path)
    defaults = config.get("defaults") or {}
    scans = config.get("scans")
    if not isinstance(defaults, dict):
        raise ValueError(f"{config_path}: defaults must be a YAML object")
    if not isinstance(scans, list) or not scans:
        raise ValueError(f"{config_path}: scans must be a non-empty list")

    continue_on_error = bool(config.get("continue_on_error", True))
    all_ok = True

    for index, scan in enumerate(scans, start=1):
        if not isinstance(scan, dict):
            raise ValueError(f"{config_path}: scans[{index}] must be a YAML object")

        label = str(scan.get("name") or scan.get("expiry") or scan.get("date") or f"scan {index}")
        days_forward = _resolve_days_forward(scan, label)
        hv_days = _resolve_hv_days(_merged_config_value(scan, defaults, "hv_days"), days_forward)
        tickers = _ticker_list_from_config(_merged_config_value(scan, defaults, "tickers"))
        top_value = _merged_config_value(scan, defaults, "top")
        top = int(top_value) if top_value not in (None, "") else None

        if tickers and top:
            raise ValueError(f"{label}: set either tickers or top, not both")

        print()
        print("=" * 72)
        print(f"Theta scan {index}/{len(scans)}: {label}")
        print("=" * 72)
        if dry_run:
            target = scan.get("expiry") or scan.get("date") or scan.get("target_date") or "days-forward"
            universe = f"top {top}" if top else f"{len(tickers)} configured tickers" if isinstance(tickers, list) else "default tickers"
            print(f"Target:       {target}")
            print(f"DTE:          {days_forward} days")
            print(f"HV lookback:  {hv_days} days")
            print(f"Universe:     {universe}")
            continue

        try:
            ok = run_theta_scan(
                api_key=api_key,
                tickers=tickers,
                top=top,
                days_forward=days_forward,
                hv_days=hv_days,
            )
        except Exception as exc:
            all_ok = False
            print(f"ERROR: {label} failed: {exc}")
            close_db()
            if not continue_on_error:
                raise
        else:
            all_ok = all_ok and ok
            if not ok and not continue_on_error:
                break

    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Run theta plays scan")
    parser.add_argument("--api-key", type=str, default=None, help="Massive API key (default: MASSIVE_API_KEY env var)")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated tickers")
    parser.add_argument("--top", type=int, default=None, help="Scan top N tickers by options volume from DB (e.g. --top 500)")
    parser.add_argument("--days-forward", type=int, default=30, help="Target DTE (default: 30)")
    parser.add_argument("--hv-days", type=int, default=None, help="HV lookback days (default: matches --days-forward)")
    parser.add_argument("--config", type=Path, default=None, help="YAML config containing multiple theta scans")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and print computed scan parameters without running")
    parser.add_argument(
        "--manage-service",
        nargs="?",
        const="decay-api",
        default=None,
        help="Stop/start a systemd service around the scan(s); pass without a value for decay-api",
    )
    args = parser.parse_args()

    if args.config and (args.tickers or args.top or args.days_forward != 30 or args.hv_days is not None):
        parser.error("--config cannot be combined with --tickers, --top, --days-forward, or --hv-days")
    if args.dry_run and not args.config:
        parser.error("--dry-run requires --config")

    try:
        if args.manage_service and not args.dry_run:
            _systemctl("stop", args.manage_service)

        if args.config:
            ok = run_theta_scans_from_config(args.config, api_key=args.api_key, dry_run=args.dry_run)
        else:
            ok = run_theta_scan(
                api_key=args.api_key,
                tickers=args.tickers,
                top=args.top,
                days_forward=args.days_forward,
                hv_days=args.hv_days,
            )
    finally:
        if args.manage_service and not args.dry_run:
            _systemctl("start", args.manage_service)

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
