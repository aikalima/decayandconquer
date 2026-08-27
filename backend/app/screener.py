"""Theta Plays screener — find overpriced options to sell.

Scans a watchlist of tickers, compares implied volatility to historical
volatility, and ranks the best candidates for theta strategies (iron condors,
covered calls, cash-secured puts).
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from math import exp
import numpy as np

from app.data.fetcher import (
    get_client,
    fetch_snapshot_for_screener,
    fetch_daily_bars,
    find_nearest_expiry_friday,
    _third_friday,
)
from app.data.db import query_daily_closes
from app.prediction_pipeline.black_scholes import call_value
from scipy.optimize import brentq

logger = logging.getLogger(__name__)

DEFAULT_TICKERS = [
    "SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
    "AMD", "NFLX", "JPM", "BAC", "GS", "XOM", "V", "MA", "CRM", "COST",
    "HD", "BA", "DIS", "COIN", "GE", "TSM", "REGN", "ASML", "RBLX", "USO",
]


@dataclass
class ScreenerRow:
    ticker: str
    spot: float
    expiry: str
    call_strike: float
    call_bid: float
    call_ask: float
    call_mid: float
    call_iv: float
    put_strike: float
    put_bid: float
    put_ask: float
    put_mid: float
    put_iv: float
    hv_20: float
    call_premium: float
    put_premium: float
    avg_premium: float
    call_efficiency: float
    put_efficiency: float
    beta: float
    pct_change_5d: float
    call_price_source: str
    put_price_source: str
    call_open_interest: int
    put_open_interest: int
    call_volume: int
    put_volume: int
    call_bid_size: int
    call_ask_size: int
    put_bid_size: int
    put_ask_size: int
    call_quote_updated_ns: int | None
    put_quote_updated_ns: int | None
    call_day_updated_ns: int | None
    put_day_updated_ns: int | None
    call_trade_updated_ns: int | None
    put_trade_updated_ns: int | None
    underlying_updated_ns: int | None
    call_quality_score: float
    put_quality_score: float
    quality_score: float
    call_rank_score: float
    put_rank_score: float
    rank_score: float
    quality_warnings: str


def compute_hv(closes: list[float], days: int = 20) -> float:
    """Annualized historical volatility from daily closes."""
    if len(closes) < max(days, 5):
        return 0.0
    prices = np.array(closes[-days:])
    log_returns = np.log(prices[1:] / prices[:-1])
    return float(np.std(log_returns) * np.sqrt(252))


def compute_beta(stock_closes: list[float], spy_closes: list[float], days: int = 20) -> float:
    """Beta vs SPY from daily returns."""
    n = min(len(stock_closes), len(spy_closes), days)
    if n < 5:
        return 0.0
    stock = np.array(stock_closes[-n:])
    spy = np.array(spy_closes[-n:])
    sr = np.diff(stock) / stock[:-1]
    mr = np.diff(spy) / spy[:-1]
    if len(sr) < 3:
        return 0.0
    var_m = np.var(mr)
    if var_m == 0:
        return 0.0
    return float(np.cov(sr, mr)[0, 1] / var_m)


def compute_efficiency(bid: float, ask: float) -> float:
    """Bid-ask spread quality (0-100, higher = tighter)."""
    mid = (bid + ask) / 2
    if mid <= 0 or bid <= 0 or ask <= 0:
        return 0.0
    return max(0.0, (1.0 - (ask - bid) / mid)) * 100


def _compact_warning(text: str) -> str:
    return text.replace(";", ",").strip()


def _side_quality(contract: dict, side: str, bid: float, ask: float, mid: float) -> tuple[float, list[str]]:
    """Score one option leg's data quality. Higher means more rankable."""
    score = 100.0
    warnings: list[str] = []
    source = contract.get("price_source", "unknown")
    oi = int(contract.get("open_interest", 0) or 0)
    volume = int(contract.get("volume", 0) or 0)

    if source != "last_quote":
        score -= 35
        warnings.append(f"{side} price uses {source}, not a live bid/ask snapshot")

    if bid <= 0 or ask <= 0:
        score -= 25
        warnings.append(f"{side} has no usable bid/ask spread")
    elif ask < bid:
        score -= 30
        warnings.append(f"{side} ask is below bid")
    else:
        spread_pct = (ask - bid) / mid * 100 if mid > 0 else 100
        if bid == ask:
            score -= 10
            warnings.append(f"{side} bid equals ask; verify the quote")
        if spread_pct >= 20:
            score -= 25
            warnings.append(f"{side} spread is very wide ({spread_pct:.1f}%)")
        elif spread_pct >= 10:
            score -= 15
            warnings.append(f"{side} spread is wide ({spread_pct:.1f}%)")
        elif spread_pct >= 5:
            score -= 8

    if oi <= 0:
        score -= 20
        warnings.append(f"{side} open interest is missing")
    elif oi < 10:
        score -= 25
        warnings.append(f"{side} open interest is very low ({oi})")
    elif oi < 100:
        score -= 12

    if volume <= 0:
        score -= 8
    elif volume < 10:
        score -= 4

    if source == "last_quote" and not contract.get("quote_updated_ns"):
        score -= 5
        warnings.append(f"{side} quote timestamp is missing")

    return max(0.0, min(100.0, score)), [_compact_warning(w) for w in warnings]


def _combined_quality(
    *,
    call_quality: float,
    put_quality: float,
    warnings: list[str],
    spot: float,
    call_strike: float,
    put_strike: float,
    call_mid: float,
    put_mid: float,
    call_iv: float,
    put_iv: float,
    expiry: date,
) -> tuple[float, list[str]]:
    score = (call_quality + put_quality) / 2

    if call_iv > 0 and put_iv > 0:
        skew_ratio = max(call_iv, put_iv) / min(call_iv, put_iv)
        if skew_ratio >= 2:
            score -= 20
            warnings.append(f"call/put IV skew is large ({skew_ratio:.1f}x)")
        elif skew_ratio >= 1.5:
            score -= 10

    if abs(call_strike - put_strike) < 0.01 and call_mid > 0 and put_mid > 0:
        days_to_expiry = max((expiry - date.today()).days, 1)
        t = days_to_expiry / 365
        expected = spot - call_strike * exp(-0.04 * t)
        observed = call_mid - put_mid
        gap_abs = abs(observed - expected)
        if gap_abs >= max(0.5, spot * 0.0025):
            score -= 20
            warnings.append(f"put-call parity gap is large (${gap_abs:.2f})")

    return max(0.0, min(100.0, score)), [_compact_warning(w) for w in warnings]


def _solve_iv(price: float, spot: float, strike: float, t: float, r: float = 0.04) -> float:
    """Quick IV solve via Brent's method. Returns 0 on failure."""
    if price <= 0 or t <= 0:
        return 0.0
    try:
        intrinsic = max(spot - strike, 0.0)
        if price < intrinsic + 0.01:
            return 0.0
        return float(brentq(
            lambda iv: call_value(spot, strike, iv, t, r) - price,
            1e-4, 5.0, xtol=1e-4,
        ))
    except Exception:
        return 0.0


def _candidate_expiries(obs_date: date, days_forward: int) -> list[date]:
    """Generate candidate expiries sorted by proximity to the target date.

    Returns 3-4 monthly expiry candidates so we can fall back if the
    preferred one has no data in the snapshot API.
    """
    target = obs_date + timedelta(days=days_forward)
    candidates = []
    for month_offset in range(-1, 4):
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
    # Sort by distance from target, preferring on-or-after
    candidates.sort(key=lambda d: (0 if d >= target else 1, abs((d - target).days)))
    return candidates


def _find_atm(contracts: list[dict], spot: float) -> dict | None:
    """Find the contract closest to ATM with a valid price."""
    if not contracts:
        return None
    # Filter to contracts with a price
    priced = [c for c in contracts if c.get("last_price", 0) > 0 or (c.get("bid", 0) + c.get("ask", 0)) > 0]
    if not priced:
        return None
    return min(priced, key=lambda c: abs(c["strike"] - spot))


def scan_ticker(
    client,
    ticker: str,
    spy_closes: list[float],
    expiry_date: date,
    hv_days: int = 20,
    candidate_expiries: list[date] | None = None,
) -> ScreenerRow | None:
    """Scan a single ticker for theta play metrics."""
    try:
        # Get daily prices from DuckDB (fast, no API calls)
        # Fall back to API if DB has no data for this ticker
        db_prices = query_daily_closes(ticker, days=max(hv_days + 5, 30))
        if len(db_prices) >= 5:
            closes = [p for _, p in db_prices]
        else:
            logger.info("No DB price data for %s, trying API", ticker)
            closes = fetch_daily_bars(client, ticker, days=max(hv_days + 5, 30))

        if len(closes) < 5:
            logger.warning("Insufficient price history for %s", ticker)
            return None

        spot = closes[-1]
        if spot <= 0:
            logger.warning("No spot price for %s", ticker)
            return None

        # Try candidate expiries until we find one with data
        expiries_to_try = candidate_expiries or [expiry_date]
        calls = []
        puts = []
        used_expiry = expiry_date
        for exp in expiries_to_try:
            calls = fetch_snapshot_for_screener(client, ticker, exp, "call")
            if calls:
                puts = fetch_snapshot_for_screener(client, ticker, exp, "put")
                if puts:
                    used_expiry = exp
                    break

        if not calls or not puts:
            logger.warning("No snapshot data for %s", ticker)
            return None

        # Find ATM contracts
        atm_call = _find_atm(calls, spot)
        atm_put = _find_atm(puts, spot)
        if not atm_call or not atm_put:
            logger.warning("No ATM contracts for %s", ticker)
            return None

        # Compute HV + beta
        hv = compute_hv(closes, hv_days)
        if hv <= 0.01:
            hv = 0.01

        beta = compute_beta(closes, spy_closes, hv_days)

        # 5-day % change
        if len(closes) >= 6:
            pct_5d = (closes[-1] - closes[-6]) / closes[-6] * 100
        else:
            pct_5d = 0.0

        # Keep bid/ask as actual quote fields. Missing quotes use last_price for
        # mid/IV only and carry a non-quote price_source plus quality penalty.
        call_bid = atm_call.get("bid", 0.0) or 0.0
        call_ask = atm_call.get("ask", 0.0) or 0.0
        call_price = atm_call.get("last_price", 0.0) or (call_bid + call_ask) / 2

        put_bid = atm_put.get("bid", 0.0) or 0.0
        put_ask = atm_put.get("ask", 0.0) or 0.0
        put_price = atm_put.get("last_price", 0.0) or (put_bid + put_ask) / 2

        call_mid = (call_bid + call_ask) / 2 if (call_bid > 0 and call_ask > 0) else call_price
        put_mid = (put_bid + put_ask) / 2 if (put_bid > 0 and put_ask > 0) else put_price

        # IV — use API value if available, else compute ourselves
        days_to_expiry = (used_expiry - date.today()).days
        t = max(days_to_expiry, 1) / 365

        call_iv = atm_call.get("iv", 0.0) or 0.0
        if call_iv <= 0 and call_price > 0:
            call_iv = _solve_iv(call_price, spot, atm_call["strike"], t)

        put_iv = atm_put.get("iv", 0.0) or 0.0
        if put_iv <= 0 and put_price > 0:
            # Use put-call parity approximation: put IV ~ call IV at same strike
            # Or solve using call_value on the synthetic call price
            synthetic_call = put_price + spot - atm_put["strike"] * np.exp(-0.04 * t)
            if synthetic_call > 0:
                put_iv = _solve_iv(synthetic_call, spot, atm_put["strike"], t)

        if call_iv <= 0 and put_iv <= 0:
            logger.warning("Could not determine IV for %s", ticker)
            return None

        # If one side failed, use the other
        if call_iv <= 0:
            call_iv = put_iv
        if put_iv <= 0:
            put_iv = call_iv

        call_quality, call_warnings = _side_quality(atm_call, "call", call_bid, call_ask, call_mid)
        put_quality, put_warnings = _side_quality(atm_put, "put", put_bid, put_ask, put_mid)
        quality, warnings = _combined_quality(
            call_quality=call_quality,
            put_quality=put_quality,
            warnings=call_warnings + put_warnings,
            spot=spot,
            call_strike=atm_call["strike"],
            put_strike=atm_put["strike"],
            call_mid=call_mid,
            put_mid=put_mid,
            call_iv=call_iv,
            put_iv=put_iv,
            expiry=used_expiry,
        )

        call_premium = round(call_iv / hv, 2) if hv > 0 else 0.0
        put_premium = round(put_iv / hv, 2) if hv > 0 else 0.0
        avg_premium = round((call_iv + put_iv) / 2 / hv, 2) if hv > 0 else 0.0

        return ScreenerRow(
            ticker=ticker,
            spot=round(spot, 2),
            expiry=str(used_expiry),
            call_strike=atm_call["strike"],
            call_bid=round(call_bid, 2),
            call_ask=round(call_ask, 2),
            call_mid=round(call_mid, 2),
            call_iv=round(call_iv, 4),
            put_strike=atm_put["strike"],
            put_bid=round(put_bid, 2),
            put_ask=round(put_ask, 2),
            put_mid=round(put_mid, 2),
            put_iv=round(put_iv, 4),
            hv_20=round(hv, 4),
            call_premium=call_premium,
            put_premium=put_premium,
            avg_premium=avg_premium,
            call_efficiency=round(compute_efficiency(call_bid, call_ask), 1),
            put_efficiency=round(compute_efficiency(put_bid, put_ask), 1),
            beta=round(beta, 2),
            pct_change_5d=round(pct_5d, 2),
            call_price_source=str(atm_call.get("price_source", "unknown")),
            put_price_source=str(atm_put.get("price_source", "unknown")),
            call_open_interest=int(atm_call.get("open_interest", 0) or 0),
            put_open_interest=int(atm_put.get("open_interest", 0) or 0),
            call_volume=int(atm_call.get("volume", 0) or 0),
            put_volume=int(atm_put.get("volume", 0) or 0),
            call_bid_size=int(atm_call.get("bid_size", 0) or 0),
            call_ask_size=int(atm_call.get("ask_size", 0) or 0),
            put_bid_size=int(atm_put.get("bid_size", 0) or 0),
            put_ask_size=int(atm_put.get("ask_size", 0) or 0),
            call_quote_updated_ns=atm_call.get("quote_updated_ns"),
            put_quote_updated_ns=atm_put.get("quote_updated_ns"),
            call_day_updated_ns=atm_call.get("day_updated_ns"),
            put_day_updated_ns=atm_put.get("day_updated_ns"),
            call_trade_updated_ns=atm_call.get("trade_updated_ns"),
            put_trade_updated_ns=atm_put.get("trade_updated_ns"),
            underlying_updated_ns=atm_call.get("underlying_updated_ns") or atm_put.get("underlying_updated_ns"),
            call_quality_score=round(call_quality, 1),
            put_quality_score=round(put_quality, 1),
            quality_score=round(quality, 1),
            call_rank_score=round(call_premium * min(call_quality, quality) / 100, 2),
            put_rank_score=round(put_premium * min(put_quality, quality) / 100, 2),
            rank_score=round(avg_premium * quality / 100, 2),
            quality_warnings="; ".join(dict.fromkeys(warnings)),
        )

    except Exception as e:
        logger.error("scan_ticker %s failed: %s", ticker, e)
        return None


def scan_all(
    tickers: list[str],
    days_forward: int = 30,
    hv_days: int = 20,
    api_key: str | None = None,
):
    """Generator that yields (stage, progress, row) tuples and final results.

    Yields:
        ("Scanning AAPL (3/30)", progress_pct, ScreenerRow | None)
    Final yield:
        dict with "highest_premium", "expensive_calls", "expensive_puts" sorted lists
    """
    client = get_client(api_key)

    # Target expiry + fallback candidates
    obs_date = date.today()
    expiry_date = find_nearest_expiry_friday(obs_date, days_forward)
    candidate_expiries = _candidate_expiries(obs_date, days_forward)

    # SPY bars for beta — try DuckDB first
    spy_db = query_daily_closes("SPY", days=max(hv_days + 5, 30))
    if len(spy_db) >= 5:
        spy_closes = [p for _, p in spy_db]
    else:
        spy_closes = fetch_daily_bars(client, "SPY", days=max(hv_days + 5, 30))

    results: list[ScreenerRow] = []
    failed: list[str] = []

    for i, ticker in enumerate(tickers):
        stage = f"Scanning {ticker} ({i + 1}/{len(tickers)})"
        progress = int(5 + (i / len(tickers)) * 90)

        row = scan_ticker(client, ticker, spy_closes, expiry_date, hv_days, candidate_expiries)
        if row:
            results.append(row)
        else:
            failed.append(ticker)

        yield (stage, progress, row)

    # Sort into three categories (top 10 each)
    by_avg = sorted(results, key=lambda r: r.rank_score, reverse=True)[:10]
    by_call = sorted(results, key=lambda r: r.call_rank_score, reverse=True)[:10]
    by_put = sorted(results, key=lambda r: r.put_rank_score, reverse=True)[:10]

    yield {
        "highest_premium": [asdict(r) for r in by_avg],
        "expensive_calls": [asdict(r) for r in by_call],
        "expensive_puts": [asdict(r) for r in by_put],
        "tickers_scanned": len(tickers),
        "tickers_failed": failed,
        "expiry": str(expiry_date),
    }
