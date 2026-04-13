"""Options heat map data generator.

Fetches live options snapshots across multiple expiries and assembles
a grid of call vs put activity (volume, OI, premium) by strike × expiry.
"""

from __future__ import annotations
import logging
from datetime import date, timedelta

from app.data.fetcher import (
    get_client,
    fetch_snapshot_for_screener,
    _third_friday,
)
from app.data.db import query_daily_closes

logger = logging.getLogger(__name__)


def _future_expiries(from_date: date, count: int = 6) -> list[date]:
    """Generate the next N monthly expiry dates (third Fridays) from a date."""
    expiries = []
    y, m = from_date.year, from_date.month
    while len(expiries) < count:
        fri = _third_friday(y, m)
        if fri > from_date:
            expiries.append(fri)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return expiries


def generate_heatmap(
    ticker: str,
    num_expiries: int = 6,
    strike_range: float = 0.15,
    api_key: str | None = None,
):
    """Generator yielding (stage, progress) tuples then a final result dict.

    The result contains the full heat map grid data:
    {ticker, spot, expiries, strikes, cells}
    """
    client = get_client(api_key)

    # Spot from DuckDB
    daily = query_daily_closes(ticker, 5)
    spot = daily[-1][1] if daily else 0.0

    if spot <= 0:
        yield {"error": f"No price data for {ticker}"}
        return

    # Determine expiry dates
    today = date.today()
    expiries = _future_expiries(today, num_expiries)

    yield (f"Found {len(expiries)} expiries for {ticker}", 5)

    # Fetch snapshots for each expiry
    all_calls: dict[str, list[dict]] = {}
    all_puts: dict[str, list[dict]] = {}
    valid_expiries = []

    for i, exp in enumerate(expiries):
        exp_str = str(exp)
        pct = int(5 + (i / len(expiries)) * 85)

        yield (f"Fetching {ticker} {exp_str} ({i + 1}/{len(expiries)})", pct)

        calls = fetch_snapshot_for_screener(client, ticker, exp, "call")
        puts = fetch_snapshot_for_screener(client, ticker, exp, "put")

        # Use spot from snapshot if we got it
        if not spot and calls:
            spot = calls[0].get("spot", 0.0)

        if calls or puts:
            all_calls[exp_str] = calls
            all_puts[exp_str] = puts
            valid_expiries.append(exp_str)

    if not valid_expiries:
        yield {"error": f"No options data found for {ticker}"}
        return

    # Collect all strikes within range of spot
    lo = spot * (1 - strike_range)
    hi = spot * (1 + strike_range)
    all_strikes = set()
    for contracts in list(all_calls.values()) + list(all_puts.values()):
        for c in contracts:
            s = c["strike"]
            if lo <= s <= hi:
                all_strikes.add(s)

    strikes = sorted(all_strikes)

    # Limit to ~25 strikes for readability
    if len(strikes) > 25:
        step = len(strikes) // 25
        strikes = strikes[::step]

    yield ("Building heat map grid", 92)

    # Build cells
    cells = []
    for exp_str in valid_expiries:
        # Index calls and puts by strike
        call_by_strike = {c["strike"]: c for c in all_calls.get(exp_str, [])}
        put_by_strike = {p["strike"]: p for p in all_puts.get(exp_str, [])}

        for strike in strikes:
            call = call_by_strike.get(strike, {})
            put = put_by_strike.get(strike, {})

            call_vol = call.get("volume", 0) or 0
            put_vol = put.get("volume", 0) or 0
            call_oi = call.get("open_interest", 0) or 0
            put_oi = put.get("open_interest", 0) or 0
            call_bid = call.get("bid", 0) or 0
            call_ask = call.get("ask", 0) or 0
            put_bid = put.get("bid", 0) or 0
            put_ask = put.get("ask", 0) or 0
            call_mid = (call_bid + call_ask) / 2 if (call_bid + call_ask) > 0 else (call.get("last_price", 0) or 0)
            put_mid = (put_bid + put_ask) / 2 if (put_bid + put_ask) > 0 else (put.get("last_price", 0) or 0)
            call_iv = call.get("iv", 0) or 0
            put_iv = put.get("iv", 0) or 0

            cells.append({
                "strike": strike,
                "expiry": exp_str,
                "call_volume": call_vol,
                "put_volume": put_vol,
                "call_oi": call_oi,
                "put_oi": put_oi,
                "call_mid": round(call_mid, 2),
                "put_mid": round(put_mid, 2),
                "call_iv": round(call_iv, 4),
                "put_iv": round(put_iv, 4),
                "net_volume": call_vol - put_vol,
                "net_oi": call_oi - put_oi,
                "net_premium": round(call_vol * call_mid - put_vol * put_mid, 2),
            })

    yield {
        "ticker": ticker,
        "spot": round(spot, 2),
        "expiries": valid_expiries,
        "strikes": strikes,
        "cells": cells,
    }
