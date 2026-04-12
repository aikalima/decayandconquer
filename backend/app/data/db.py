"""DuckDB database layer for options data.

Provides a read-optimised columnar store for historical options data
(imported from Massive.com flat files). The DB is a single file with
no server process.

Usage:
    from app.data.db import get_db, query_chain

    # Query an options chain
    df = query_chain('AAPL', '2025-06-01', '2025-08-15')
"""

from __future__ import annotations
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "options.duckdb"
FLAT_FILES_DIR = Path(__file__).parent / "flat_files"

_connection: duckdb.DuckDBPyConnection | None = None
_default_read_only: bool = False

# Regex to parse OCC ticker: O:{UNDERLYING}{YYMMDD}{C|P}{STRIKE*1000 8-digit}
_OCC_RE = re.compile(r'^O:([A-Z]+)(\d{6})([CP])(\d{8})$')


def check_db_writable() -> tuple[bool, str]:
    """Check if the DB can be opened for writing. Returns (ok, message)."""
    try:
        conn = duckdb.connect(str(DB_PATH), read_only=False)
        conn.close()
        return True, "DB is writable"
    except duckdb.IOException as e:
        msg = str(e)
        # Extract the locking process info
        if "Conflicting lock" in msg:
            # e.g. "...held in /path/to/app (PID 1234) by user foo..."
            import re
            m = re.search(r'held in (.+?) \(PID (\d+)\) by user (\w+)', msg)
            if m:
                app_path, pid, user = m.groups()
                app_name = app_path.rsplit("/", 1)[-1]
                return False, f"DB is locked by {app_name} (PID {pid}). Close it before writing."
        return False, f"DB is locked: {msg}"
    except Exception as e:
        return False, f"DB check failed: {e}"


def set_read_only(read_only: bool = True):
    """Set the default connection mode. Call before first get_db()."""
    global _default_read_only
    _default_read_only = read_only


def get_db(read_only: bool | None = None) -> duckdb.DuckDBPyConnection:
    """Get or create the DuckDB connection (singleton).

    The server calls set_read_only(True) at startup so it never holds
    a write lock. CLI scripts that need to write call get_db(read_only=False).
    """
    global _connection
    if read_only is None:
        read_only = _default_read_only
    if _connection is None:
        _connection = duckdb.connect(str(DB_PATH), read_only=read_only)
        if not read_only:
            _ensure_schema(_connection)
        logger.info("DuckDB opened: %s (read_only=%s)", DB_PATH, read_only)
    return _connection


def _ensure_schema(conn: duckdb.DuckDBPyConnection):
    """Create tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS options (
            -- Parsed from OCC ticker
            underlying    VARCHAR NOT NULL,   -- e.g. 'AAPL'
            expiry        DATE NOT NULL,      -- option expiration date
            contract_type VARCHAR NOT NULL,   -- 'C' or 'P'
            strike        DOUBLE NOT NULL,    -- strike price in dollars

            -- Full OCC ticker
            ticker        VARCHAR NOT NULL,   -- e.g. 'O:AAPL250815C00200000'

            -- Trading day (human-readable, derived from window_start)
            trade_date    DATE NOT NULL,

            -- OHLCV
            open          DOUBLE,
            high          DOUBLE,
            low           DOUBLE,
            close         DOUBLE,
            volume        BIGINT,
            transactions  INTEGER,

            PRIMARY KEY (ticker, trade_date)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS theta_scans (
            scan_id           VARCHAR PRIMARY KEY,
            days_forward      INTEGER NOT NULL,
            hv_days           INTEGER NOT NULL,
            expiry            DATE NOT NULL,
            tickers_scanned   INTEGER,
            tickers_failed    INTEGER,
            scan_time_seconds DOUBLE,
            created_at        TIMESTAMP DEFAULT current_timestamp
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS theta_results (
            scan_id         VARCHAR NOT NULL,
            ticker          VARCHAR NOT NULL,
            spot            DOUBLE,
            expiry          DATE,
            call_strike     DOUBLE,
            call_bid        DOUBLE,
            call_ask        DOUBLE,
            call_mid        DOUBLE,
            call_iv         DOUBLE,
            put_strike      DOUBLE,
            put_bid         DOUBLE,
            put_ask         DOUBLE,
            put_mid         DOUBLE,
            put_iv          DOUBLE,
            hv_20           DOUBLE,
            call_premium    DOUBLE,
            put_premium     DOUBLE,
            avg_premium     DOUBLE,
            call_efficiency DOUBLE,
            put_efficiency  DOUBLE,
            beta            DOUBLE,
            pct_change_5d   DOUBLE,
            PRIMARY KEY (scan_id, ticker)
        )
    """)


def parse_occ_ticker(ticker: str) -> dict | None:
    """Parse an OCC option ticker into its components.

    'O:AAPL250815C00200000' -> {
        underlying: 'AAPL',
        expiry: date(2025, 8, 15),
        contract_type: 'C',
        strike: 200.0,
    }
    """
    m = _OCC_RE.match(ticker)
    if not m:
        return None
    underlying, date_str, cp, strike_raw = m.groups()
    expiry = date(2000 + int(date_str[:2]), int(date_str[2:4]), int(date_str[4:6]))
    strike = int(strike_raw) / 1000.0
    return {
        "underlying": underlying,
        "expiry": expiry,
        "contract_type": cp,
        "strike": strike,
    }


def ns_to_date(window_start_ns: int) -> date:
    """Convert nanosecond epoch timestamp to a date."""
    return datetime.fromtimestamp(window_start_ns / 1_000_000_000, tz=timezone.utc).date()


def import_flat_file(filepath: Path, conn: duckdb.DuckDBPyConnection | None = None) -> int:
    """Import a single gzipped CSV flat file into the options table.

    Uses pure SQL to parse OCC tickers and convert timestamps — no Python
    row-level loop needed. ~50x faster than the Python-level approach.
    """
    if conn is None:
        conn = get_db()

    # DuckDB parses OCC ticker and timestamp entirely in SQL — no Python loop.
    # OCC format: O:{UNDERLYING}{YYMMDD}{C|P}{STRIKE*1000 8-digit}
    # Parse from the right: last 8 = strike, then 1 char C/P, then 6 digits date,
    # remainder after O: = underlying. Handles tickers with digits like ACB1, AMC2.
    sql = r"""
        INSERT OR IGNORE INTO options
            (underlying, expiry, contract_type, strike, ticker, trade_date,
             open, high, low, close, volume, transactions)
        SELECT
            -- underlying = everything between 'O:' and the 15-char suffix (6date + 1cp + 8strike)
            substr(ticker, 3, length(ticker) - 17) AS underlying,

            -- expiry = 6 digits before C/P, parse as date
            CAST(
                '20' || substr(ticker, length(ticker) - 14, 2)
                || '-' || substr(ticker, length(ticker) - 12, 2)
                || '-' || substr(ticker, length(ticker) - 10, 2)
            AS DATE) AS expiry,

            -- contract_type = single char at position -8 from end
            substr(ticker, length(ticker) - 8, 1) AS contract_type,

            -- strike = last 8 digits / 1000
            CAST(substr(ticker, length(ticker) - 7) AS DOUBLE) / 1000.0 AS strike,

            ticker,

            CAST(epoch_ms(CAST(window_start / 1000000 AS BIGINT)) AS DATE) AS trade_date,

            open, high, low, close, volume, transactions
        FROM read_csv_auto($1)
        WHERE ticker LIKE 'O:%'
          AND length(ticker) > 17
    """
    result = conn.execute(sql, [str(filepath)])

    count = result.fetchone()[0]
    print(f"{filepath.name}: {count:,} rows", flush=True)
    return count


def import_all_flat_files(directory: Path | None = None, conn: duckdb.DuckDBPyConnection | None = None) -> int:
    """Import all .csv.gz files from a directory."""
    directory = directory or FLAT_FILES_DIR
    if conn is None:
        conn = get_db()

    files = sorted(directory.glob("*.csv.gz"))
    if not files:
        logger.warning("No .csv.gz files found in %s", directory)
        return 0

    total = 0
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] ", end="", flush=True)
        total += import_flat_file(f, conn)

    logger.info("Total imported: %d rows from %d files", total, len(files))
    return total


def query_chain(
    underlying: str,
    trade_date: str | date,
    expiry: str | date,
    contract_type: str = "C",
) -> "pd.DataFrame":
    """Query an options chain from the database.

    Returns a DataFrame with columns [strike, last_price, bid, ask]
    matching the format expected by predict_price().
    """
    import pandas as pd

    db = get_db()
    df = db.execute("""
        SELECT strike, close AS last_price, low AS bid, high AS ask
        FROM options
        WHERE underlying = ?
          AND trade_date = ?
          AND expiry = ?
          AND contract_type = ?
          AND close > 0
        ORDER BY strike
    """, [underlying, str(trade_date), str(expiry), contract_type]).fetchdf()

    if df.empty:
        raise ValueError(
            f"No options data in DB for {underlying} on {trade_date} exp {expiry}"
        )

    return df


def query_chains_range(
    underlying: str,
    date_from: str | date,
    date_to: str | date,
    expiry: str | date,
    contract_type: str = "C",
) -> "pd.DataFrame":
    """Query options chains across a date range from the database.

    Returns a DataFrame with columns [trade_date, strike, last_price, bid, ask]
    containing all rows for the underlying in the date range with the given expiry.
    """
    import pandas as pd

    db = get_db()
    df = db.execute("""
        SELECT trade_date, strike, close AS last_price, low AS bid, high AS ask
        FROM options
        WHERE underlying = ?
          AND trade_date BETWEEN ? AND ?
          AND expiry = ?
          AND contract_type = ?
          AND close > 0
        ORDER BY trade_date, strike
    """, [underlying, str(date_from), str(date_to), str(expiry), contract_type]).fetchdf()

    if df.empty:
        raise ValueError(
            f"No options data in DB for {underlying} from {date_from} to {date_to} exp {expiry}"
        )

    return df


def find_best_expiry_in_range(
    underlying: str,
    date_from: str | date,
    date_to: str | date,
    target_expiry: str | date,
    contract_type: str = "C",
) -> date | None:
    """Find the best expiry across a date range — picks the one with most total data points."""
    db = get_db()
    row = db.execute("""
        SELECT expiry, COUNT(*) AS n
        FROM options
        WHERE underlying = ?
          AND trade_date BETWEEN ? AND ?
          AND contract_type = ?
          AND close > 0
        GROUP BY expiry
        HAVING n >= 5
        ORDER BY ABS(expiry - CAST(? AS DATE)), n DESC
        LIMIT 1
    """, [underlying, str(date_from), str(date_to), contract_type, str(target_expiry)]).fetchone()
    return row[0] if row else None


def find_best_expiry(
    underlying: str,
    trade_date: str | date,
    target_expiry: str | date,
    contract_type: str = "C",
) -> date | None:
    """Find the best available expiry in the DB near the target date.

    Picks the expiry closest to target_expiry that has the most contracts,
    with a preference for expiries with at least 5 strikes.
    """
    db = get_db()
    rows = db.execute("""
        SELECT expiry, COUNT(*) AS n
        FROM options
        WHERE underlying = ?
          AND trade_date = ?
          AND contract_type = ?
          AND close > 0
        GROUP BY expiry
        HAVING n >= 5
        ORDER BY ABS(expiry - CAST(? AS DATE)), n DESC
        LIMIT 1
    """, [underlying, str(trade_date), contract_type, str(target_expiry)]).fetchall()

    if rows:
        return rows[0][0]

    # Fallback: pick expiry with most contracts even if < 5
    row = db.execute("""
        SELECT expiry, COUNT(*) AS n
        FROM options
        WHERE underlying = ?
          AND trade_date = ?
          AND contract_type = ?
          AND close > 0
        GROUP BY expiry
        ORDER BY n DESC
        LIMIT 1
    """, [underlying, str(trade_date), contract_type]).fetchone()
    return row[0] if row else None


def has_data(underlying: str, trade_date: str | date) -> bool:
    """Check if the DB has any options data for a ticker on a given date."""
    db = get_db()
    row = db.execute("""
        SELECT COUNT(*) FROM options
        WHERE underlying = ? AND trade_date = ?
        LIMIT 1
    """, [underlying, str(trade_date)]).fetchone()
    return row[0] > 0


def get_stats() -> dict:
    """Return summary statistics about the database."""
    db = get_db()
    row_count = db.execute("SELECT COUNT(*) FROM options").fetchone()[0]
    date_range = db.execute(
        "SELECT MIN(trade_date), MAX(trade_date) FROM options"
    ).fetchone()
    tickers = db.execute(
        "SELECT DISTINCT underlying FROM options ORDER BY underlying"
    ).fetchdf()["underlying"].tolist()

    return {
        "rows": row_count,
        "date_range": (str(date_range[0]), str(date_range[1])) if date_range[0] else None,
        "tickers": tickers,
    }


def query_daily_closes(underlying: str, days: int = 30) -> list[tuple[str, float]]:
    """Get approximate daily close prices for an underlying from options data.

    Uses deep ITM call options (strike + close ≈ spot) to infer the
    underlying's daily price. Returns list of (date_str, price) tuples,
    oldest first.
    """
    db = get_db()
    # For each trade_date, find the lowest-strike call and compute
    # intrinsic value: spot ≈ strike + call_close for deep ITM calls
    rows = db.execute("""
        WITH daily_spot AS (
            SELECT trade_date,
                   -- Deep ITM call: spot ≈ strike + call_price
                   MIN(strike) AS min_strike,
                   FIRST(close ORDER BY strike) AS min_strike_price
            FROM options
            WHERE underlying = ?
              AND contract_type = 'C'
              AND close > 0
            GROUP BY trade_date
            ORDER BY trade_date DESC
            LIMIT ?
        )
        SELECT trade_date, min_strike + min_strike_price AS spot
        FROM daily_spot
        ORDER BY trade_date
    """, [underlying, days]).fetchall()
    return [(str(r[0]), float(r[1])) for r in rows]


def get_top_tickers_by_volume(limit: int = 500, lookback_days: int = 30) -> list[str]:
    """Get the top N tickers by options trading volume over the last N days."""
    db = get_db()
    rows = db.execute("""
        SELECT underlying
        FROM options
        WHERE trade_date >= CURRENT_DATE - ?
          AND volume > 0
        GROUP BY underlying
        HAVING SUM(volume) > 100
        ORDER BY SUM(volume) DESC
        LIMIT ?
    """, [lookback_days, limit]).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Theta Plays persistence
# ---------------------------------------------------------------------------

def save_theta_scan(
    scan_id: str,
    days_forward: int,
    hv_days: int,
    expiry: str,
    tickers_scanned: int,
    tickers_failed: int,
    scan_time_seconds: float,
) -> None:
    """Insert a theta scan metadata row."""
    db = get_db()
    db.execute("""
        INSERT OR REPLACE INTO theta_scans
            (scan_id, days_forward, hv_days, expiry, tickers_scanned, tickers_failed, scan_time_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [scan_id, days_forward, hv_days, expiry, tickers_scanned, tickers_failed, scan_time_seconds])


def save_theta_results(scan_id: str, rows: list[dict]) -> None:
    """Bulk insert theta screener results for a scan."""
    if not rows:
        return
    db = get_db()
    for r in rows:
        db.execute("""
            INSERT OR REPLACE INTO theta_results
                (scan_id, ticker, spot, expiry, call_strike, call_bid, call_ask, call_mid,
                 call_iv, put_strike, put_bid, put_ask, put_mid, put_iv, hv_20,
                 call_premium, put_premium, avg_premium, call_efficiency, put_efficiency,
                 beta, pct_change_5d)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            scan_id, r["ticker"], r["spot"], r["expiry"],
            r["call_strike"], r["call_bid"], r["call_ask"], r["call_mid"], r["call_iv"],
            r["put_strike"], r["put_bid"], r["put_ask"], r["put_mid"], r["put_iv"],
            r["hv_20"], r["call_premium"], r["put_premium"], r["avg_premium"],
            r["call_efficiency"], r["put_efficiency"], r["beta"], r["pct_change_5d"],
        ])


def get_available_theta_expiries() -> list[dict]:
    """Get distinct expiry dates from completed theta scans."""
    db = get_db()
    rows = db.execute("""
        SELECT expiry, MAX(created_at) as last_scanned, MAX(tickers_scanned) as tickers
        FROM theta_scans
        GROUP BY expiry
        ORDER BY expiry
    """).fetchall()
    return [
        {"expiry": str(r[0]), "last_scanned": str(r[1]), "tickers_scanned": r[2]}
        for r in rows
    ]


def get_latest_theta_scan_by_expiry(expiry: str) -> dict | None:
    """Get the most recent theta scan for a specific expiry date."""
    db = get_db()
    row = db.execute("""
        SELECT scan_id, days_forward, hv_days, expiry, tickers_scanned,
               tickers_failed, scan_time_seconds, created_at
        FROM theta_scans
        WHERE expiry = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, [expiry]).fetchone()
    if not row:
        return None
    return {
        "scan_id": row[0], "days_forward": row[1], "hv_days": row[2],
        "expiry": str(row[3]), "tickers_scanned": row[4], "tickers_failed": row[5],
        "scan_time_seconds": row[6], "created_at": str(row[7]),
    }


def get_latest_theta_scan(days_forward: int | None = None) -> dict | None:
    """Get the most recent theta scan metadata, optionally filtered by DTE."""
    db = get_db()
    if days_forward is not None:
        row = db.execute("""
            SELECT scan_id, days_forward, hv_days, expiry, tickers_scanned,
                   tickers_failed, scan_time_seconds, created_at
            FROM theta_scans
            WHERE days_forward = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, [days_forward]).fetchone()
    else:
        row = db.execute("""
            SELECT scan_id, days_forward, hv_days, expiry, tickers_scanned,
                   tickers_failed, scan_time_seconds, created_at
            FROM theta_scans
            ORDER BY created_at DESC
            LIMIT 1
        """).fetchone()
    if not row:
        return None
    return {
        "scan_id": row[0], "days_forward": row[1], "hv_days": row[2],
        "expiry": str(row[3]), "tickers_scanned": row[4], "tickers_failed": row[5],
        "scan_time_seconds": row[6], "created_at": str(row[7]),
    }


def get_theta_results(scan_id: str) -> list[dict]:
    """Get all theta results for a given scan."""
    db = get_db()
    df = db.execute("""
        SELECT ticker, spot, expiry, call_strike, call_bid, call_ask, call_mid,
               call_iv, put_strike, put_bid, put_ask, put_mid, put_iv, hv_20,
               call_premium, put_premium, avg_premium, call_efficiency, put_efficiency,
               beta, pct_change_5d
        FROM theta_results
        WHERE scan_id = ?
        ORDER BY avg_premium DESC
    """, [scan_id]).fetchdf()
    # Convert any Timestamp/date columns to strings for JSON serialization
    if "expiry" in df.columns:
        df["expiry"] = df["expiry"].astype(str)
    return df.to_dict(orient="records")


def close_db():
    """Close the database connection."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
