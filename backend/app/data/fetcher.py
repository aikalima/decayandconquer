"""Data fetching and caching layer for the Massive.com (formerly Polygon.io) API.

Provides functions to fetch historical options chains and stock prices,
with automatic CSV caching so backtests are reproducible offline.
"""

from __future__ import annotations
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# Options Starter tier — much higher rate limit
DEFAULT_RATE_LIMIT_SLEEP = 0.2


def get_client(api_key: str | None = None):
    """Create a Massive REST client.

    Reads MASSIVE_API_KEY from the environment if no key is provided.
    """
    from massive import RESTClient

    key = api_key or os.environ.get("MASSIVE_API_KEY", "")
    if not key:
        raise ValueError(
            "No API key provided. Set MASSIVE_API_KEY env var or pass api_key="
        )
    return RESTClient(api_key=key)


def build_occ_ticker(
    underlying: str, expiry: date, call_put: str, strike: float
) -> str:
    """Build an OCC-format option ticker symbol.

    Example: SPY, 2025-02-21, "C", 595.0 -> "O:SPY250221C00595000"
    """
    date_str = expiry.strftime("%y%m%d")
    strike_int = int(round(strike * 1000))
    return f"O:{underlying}{date_str}{call_put}{strike_int:08d}"


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _third_friday(year: int, month: int) -> date:
    """Return the third Friday of a given month (standard options expiry)."""
    # First day of month
    first = date(year, month, 1)
    # Weekday of first day (Mon=0 ... Sun=6)
    # First Friday: day = 1 + (4 - first.weekday()) % 7
    first_friday = 1 + (4 - first.weekday()) % 7
    third_friday = first_friday + 14
    return date(year, month, third_friday)


def find_nearest_expiry_friday(obs_date: date, days_forward: int) -> date:
    """Find the standard monthly options expiry (third Friday) nearest to
    obs_date + days_forward.

    Generates third-Friday candidates for surrounding months and picks
    the closest one that is on or after obs_date.
    """
    target = obs_date + timedelta(days=days_forward)

    # Generate candidates: third Friday of target month +/- 1 month
    candidates = []
    for month_offset in range(-1, 3):
        y = target.year
        m = target.month + month_offset
        if m < 1:
            m += 12
            y -= 1
        elif m > 12:
            m -= 12
            y += 1
        fri = _third_friday(y, m)
        if fri >= obs_date:
            candidates.append(fri)

    if not candidates:
        # Fallback: just snap to nearest Friday
        weekday = target.weekday()
        delta = (4 - weekday) % 7
        if delta > 3:
            delta -= 7
        return target + timedelta(days=delta)

    # Pick the candidate closest to the target date
    return min(candidates, key=lambda d: abs((d - target).days))


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _chain_cache_path(ticker: str, on_date: date, expiry_date: date) -> Path:
    return CACHE_DIR / f"{ticker}_{on_date.isoformat()}_chain_{expiry_date.isoformat()}.csv"


def _spot_cache_path(ticker: str, on_date: date) -> Path:
    return CACHE_DIR / f"{ticker}_{on_date.isoformat()}_spot.csv"


# ---------------------------------------------------------------------------
# Stock prices
# ---------------------------------------------------------------------------

def fetch_spot_price(
    ticker: str,
    on_date: date,
    client=None,
    api_key: str | None = None,
    rate_limit_sleep: float = DEFAULT_RATE_LIMIT_SLEEP,
) -> float:
    """Get the closing stock price for a ticker on a given date.

    Looks back up to 5 trading days if the exact date has no data
    (weekend/holiday). Caches the result.
    """
    cache_path = _spot_cache_path(ticker, on_date)
    if cache_path.exists():
        df = pd.read_csv(cache_path)
        return float(df.iloc[0]["close"])

    if client is None:
        client = get_client(api_key)

    # Look back up to 7 calendar days to find a trading day
    from_date = on_date - timedelta(days=7)
    time.sleep(rate_limit_sleep)
    bars = list(client.list_aggs(ticker, 1, "day", str(from_date), str(on_date), limit=10))

    if not bars:
        raise ValueError(f"No price data for {ticker} near {on_date}")

    # Take the last (most recent) bar
    bar = bars[-1]
    df = pd.DataFrame([{"date": on_date.isoformat(), "close": bar.close}])
    df.to_csv(cache_path, index=False)
    logger.info("fetch_spot_price: %s on %s -> %.2f (cached)", ticker, on_date, bar.close)
    return float(bar.close)


# ---------------------------------------------------------------------------
# Options chains
# ---------------------------------------------------------------------------

def _try_snapshot_chain(
    client,
    ticker: str,
    expiry_date: date,
    rate_limit_sleep: float,
) -> pd.DataFrame | None:
    """Try fetching chain via the snapshot endpoint (fast path, one call)."""
    try:
        time.sleep(rate_limit_sleep)
        rows = []
        for o in client.list_snapshot_options_chain(
            ticker,
            params={
                "expiration_date.gte": str(expiry_date),
                "expiration_date.lte": str(expiry_date),
                "contract_type": "call",
            },
        ):
            strike = o.details.strike_price if hasattr(o, "details") else None
            if strike is None:
                continue

            last_price = 0.0
            bid = 0.0
            ask = 0.0

            if hasattr(o, "day") and o.day:
                last_price = getattr(o.day, "close", 0.0) or 0.0

            if hasattr(o, "last_quote") and o.last_quote:
                bid = getattr(o.last_quote, "bid", 0.0) or 0.0
                ask = getattr(o.last_quote, "ask", 0.0) or 0.0

            # Fall back to last_trade if day.close is missing
            if last_price == 0.0 and hasattr(o, "last_trade") and o.last_trade:
                last_price = getattr(o.last_trade, "price", 0.0) or 0.0

            if last_price > 0:
                rows.append({
                    "strike": strike,
                    "last_price": last_price,
                    "bid": bid if bid > 0 else last_price,
                    "ask": ask if ask > 0 else last_price,
                })

        if rows:
            df = pd.DataFrame(rows).sort_values("strike").reset_index(drop=True)
            logger.info("Snapshot chain: %s exp %s -> %d contracts", ticker, expiry_date, len(df))
            return df
    except Exception as e:
        logger.warning("Snapshot chain failed for %s: %s", ticker, e)

    return None


def _fetch_chain_per_contract(
    client,
    ticker: str,
    on_date: date,
    expiry_date: date,
    spot: float,
    rate_limit_sleep: float,
) -> pd.DataFrame:
    """Fallback: construct OCC tickers and fetch per-contract OHLC.

    Generates call strikes from 0.5x to 1.5x spot and fetches daily
    bars for each. Slower but works when snapshot endpoint is down.
    """
    # Generate strike candidates — tighter range with wider steps
    # to minimize API calls. Most probability mass is within +/-30% of spot.
    if spot > 200:
        step = 5.0
    elif spot > 50:
        step = 2.5
    else:
        step = 1.0

    lo = max(step, round(spot * 0.7 / step) * step)
    hi = round(spot * 1.3 / step) * step
    strikes = np.arange(lo, hi + step, step)

    logger.info(
        "Per-contract fallback: %s, %d candidate strikes [%.0f-%.0f], exp %s",
        ticker, len(strikes), lo, hi, expiry_date,
    )

    rows = []
    for strike in strikes:
        occ = build_occ_ticker(ticker, expiry_date, "C", strike)
        try:
            time.sleep(rate_limit_sleep)
            bars = list(client.list_aggs(
                occ, 1, "day", str(on_date), str(on_date), limit=1,
            ))
            if not bars:
                # Try previous trading day
                from_date = on_date - timedelta(days=5)
                bars = list(client.list_aggs(
                    occ, 1, "day", str(from_date), str(on_date), limit=10,
                ))
            if bars:
                bar = bars[-1]
                rows.append({
                    "strike": strike,
                    "last_price": bar.close,
                    "bid": bar.low,
                    "ask": bar.high,
                })
        except Exception as e:
            logger.debug("No data for %s: %s", occ, e)

    if not rows:
        raise ValueError(
            f"No options data found for {ticker} on {on_date} exp {expiry_date}"
        )

    df = pd.DataFrame(rows).sort_values("strike").reset_index(drop=True)
    logger.info("Per-contract chain: %s on %s -> %d contracts", ticker, on_date, len(df))
    return df


def fetch_options_chain(
    ticker: str,
    on_date: date,
    expiry_date: date,
    spot: float | None = None,
    client=None,
    api_key: str | None = None,
    rate_limit_sleep: float = DEFAULT_RATE_LIMIT_SLEEP,
) -> pd.DataFrame:
    """Fetch a historical call options chain.

    Checks cache first. Tries the snapshot endpoint, falls back to
    per-contract OHLC if that fails.

    Returns:
        DataFrame with columns [strike, last_price, bid, ask] sorted
        by strike — ready for predict_price().
    """
    cache_path = _chain_cache_path(ticker, on_date, expiry_date)
    if cache_path.exists():
        logger.info("Cache hit: %s", cache_path.name)
        return pd.read_csv(cache_path)

    if client is None:
        client = get_client(api_key)

    # Build a list of expiry candidates to try (primary + adjacent months)
    candidates = [expiry_date]
    for offset in [-1, 1, -2, 2]:
        y, m = expiry_date.year, expiry_date.month + offset
        if m < 1:
            m += 12
            y -= 1
        elif m > 12:
            m -= 12
            y += 1
        alt = _third_friday(y, m)
        if alt >= on_date and alt not in candidates:
            candidates.append(alt)

    if spot is None:
        spot = fetch_spot_price(ticker, on_date, client, rate_limit_sleep=rate_limit_sleep)

    for exp in candidates:
        # Try snapshot first (fast)
        df = _try_snapshot_chain(client, ticker, exp, rate_limit_sleep)

        # Fallback to per-contract OHLC
        if df is None:
            try:
                df = _fetch_chain_per_contract(
                    client, ticker, on_date, exp, spot, rate_limit_sleep,
                )
            except ValueError:
                logger.info("No data for %s exp %s, trying next expiry", ticker, exp)
                continue

        if df is not None and len(df) >= 5:
            if exp != expiry_date:
                logger.info("Using alternative expiry %s (requested %s)", exp, expiry_date)
            # Cache under the original requested expiry for consistency
            df.to_csv(cache_path, index=False)
            logger.info("Cached chain -> %s (%d rows)", cache_path.name, len(df))
            return df

    raise ValueError(
        f"No options data found for {ticker} on {on_date} near expiry {expiry_date}. "
        f"Tried: {[str(c) for c in candidates]}"
    )
