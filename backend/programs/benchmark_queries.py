#!/usr/bin/env python3
"""Compare full-history and optimized queries on an existing, read-only DuckDB.

Run from the repository root:
    backend/.venv/bin/python backend/programs/benchmark_queries.py --repeats 5
"""

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.data import db


# The old full-history query with the same deterministic tie-break as production.
# Previously, equal strikes could yield different prices on successive runs.
FULL_HISTORY_DAILY_CLOSES = """
    WITH daily_spot AS (
        SELECT trade_date, MIN(strike) AS min_strike,
               FIRST(close ORDER BY strike, expiry, ticker) AS min_strike_price
        FROM options
        WHERE underlying = ? AND contract_type = 'C' AND close > 0
        GROUP BY trade_date
        ORDER BY trade_date DESC
        LIMIT ?
    )
    SELECT trade_date, min_strike + min_strike_price AS spot
    FROM daily_spot ORDER BY trade_date
"""


def full_history_daily_closes(conn, ticker, days):
    return [(str(d), float(p)) for d, p in conn.execute(
        FULL_HISTORY_DAILY_CLOSES, [ticker, days]
    ).fetchall()]


def compare(name, baseline, current, repeats):
    expected = baseline()
    actual = current()
    if actual != expected:
        raise AssertionError(f"{name}: result mismatch; benchmark aborted")
    samples = {"baseline_ms": [], "current_ms": []}
    # Warm both paths first, then alternate order to reduce cache/order bias.
    for index in range(repeats):
        calls = [("baseline_ms", baseline), ("current_ms", current)]
        if index % 2:
            calls.reverse()
        for label, call in calls:
            start = perf_counter()
            result = call()
            samples[label].append((perf_counter() - start) * 1000)
            if result != expected:
                raise AssertionError(f"{name}: result changed during measurement")
    baseline_ms = statistics.median(samples["baseline_ms"])
    current_ms = statistics.median(samples["current_ms"])
    return {
        "query": name, "results_equal": True,
        "baseline_median_ms": baseline_ms, "current_median_ms": current_ms,
        "speedup": baseline_ms / current_ms, **samples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=db.DB_PATH)
    parser.add_argument("--tickers", nargs="+", default=["SPY", "NVDA", "MSFT"])
    parser.add_argument("--days", nargs="+", type=int, default=[5, 30, 180])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--json", type=Path, help="Optional output report path")
    args = parser.parse_args()
    if args.repeats < 1 or any(days < 1 for days in args.days):
        parser.error("repeats and days must be positive")
    path = args.db.resolve(strict=True)
    if args.json and (args.json.resolve() == path or args.json.exists()):
        parser.error("JSON report must be a new file, not the database")
    db.DB_PATH = path
    db.set_read_only(True)
    try:
        conn = db.get_db()
        count, first, latest = conn.execute(
            "SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM options"
        ).fetchone()
        if latest is None:
            parser.error("database has no options data")
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": str(path), "database_bytes": path.stat().st_size,
            "duckdb_version": duckdb.__version__,
            "threads": conn.execute("SELECT current_setting('threads')").fetchone()[0],
            "rows": count, "date_range": [str(first), str(latest)],
            "method": "Warm paired queries; alternating order; exact result comparison. Both daily-close paths use the same deterministic tie-break. No API calls.",
            "repeats": args.repeats, "results": [],
        }
        for ticker in args.tickers:
            for days in args.days:
                result = compare(
                    f"daily_closes/{ticker}/{days}",
                    lambda: full_history_daily_closes(conn, ticker, days),
                    lambda: db.query_daily_closes(ticker, days), args.repeats,
                )
                report["results"].append(result)
                print(f"{result['query']}: {result['baseline_median_ms']:.1f} -> "
                      f"{result['current_median_ms']:.1f} ms ({result['speedup']:.2f}x)", flush=True)
            result = compare(
                f"has_data/{ticker}",
                lambda: conn.execute(
                    "SELECT COUNT(*) FROM options WHERE underlying = ? AND trade_date = ? LIMIT 1",
                    [ticker, latest],
                ).fetchone()[0] > 0,
                lambda: db.has_data(ticker, latest), args.repeats,
            )
            report["results"].append(result)
            print(f"{result['query']}: {result['baseline_median_ms']:.1f} -> "
                  f"{result['current_median_ms']:.1f} ms ({result['speedup']:.2f}x)", flush=True)
        if args.json:
            with args.json.open("x") as output:
                output.write(json.dumps(report, indent=2) + "\n")
            print(f"Report: {args.json}")
    finally:
        db.close_db()


if __name__ == "__main__":
    main()
