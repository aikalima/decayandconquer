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

# Regex to parse OCC ticker: O:{UNDERLYING}{YYMMDD}{C|P}{STRIKE*1000 8-digit}
_OCC_RE = re.compile(r'^O:([A-Z]+)(\d{6})([CP])(\d{8})$')


def get_db() -> duckdb.DuckDBPyConnection:
    """Get or create the DuckDB connection (singleton)."""
    global _connection
    if _connection is None:
        _connection = duckdb.connect(str(DB_PATH))
        _ensure_schema(_connection)
        logger.info("DuckDB opened: %s", DB_PATH)
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


def close_db():
    """Close the database connection."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
