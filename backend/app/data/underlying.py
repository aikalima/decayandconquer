"""Actual daily stock closes, kept separate from the historical options database."""

import json
import math
import os
import re
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.data.fetcher import CACHE_DIR, get_client

STOCK_CACHE = CACHE_DIR / "stock_daily"


def daily_closes(ticker: str, start: date, end: date, *, allow_api: bool = True) -> dict[str, float]:
    """Return unadjusted daily closes, on their actual dates, never a live partial bar.

    Unadjusted prices match the historical option strikes. Exact-range cache
    files expire after one day to pick up provider corrections when online.
    Set allow_api=False for cache-only access.
    """
    ticker = ticker.upper()
    if not re.fullmatch(r"[A-Z0-9.^-]{1,20}", ticker):
        raise ValueError("Invalid stock ticker")
    today = datetime.now(ZoneInfo("America/New_York")).date()
    end = min(end, today - timedelta(days=1))
    if start > end:
        return {}
    path = STOCK_CACHE / f"{ticker}_{start}_{end}.json"
    if path.exists():
        data = json.loads(path.read_text())
        if not allow_api or data.get("fetched_on") == today.isoformat():
            return data["closes"]
    if not allow_api:
        return {}
    bars = get_client().list_aggs(
        ticker, 1, "day", start.isoformat(), end.isoformat(),
        adjusted=False, sort="asc", limit=50000,
    )
    closes = {}
    for bar in bars:
        day = datetime.fromtimestamp(bar.timestamp / 1000, ZoneInfo("America/New_York")).date()
        close = float(bar.close)
        if start <= day <= end and math.isfinite(close) and close > 0:
            closes[day.isoformat()] = close
    STOCK_CACHE.mkdir(parents=True, exist_ok=True)
    # Publish only complete API responses; interrupted requests never poison cache.
    with tempfile.NamedTemporaryFile(mode="w", dir=STOCK_CACHE, delete=False) as output:
        temporary = Path(output.name)
        json.dump({"fetched_on": today.isoformat(), "closes": closes}, output)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return closes


def realized_close(ticker: str, target: date, *, allow_api: bool = True) -> dict | None:
    """Score only an actual close on the requested target date, never a later row."""
    try:
        closes = daily_closes(ticker, target, target, allow_api=allow_api)
        price = closes.get(target.isoformat())
        if price is not None:
            return {"date": target.isoformat(), "price": price, "basis": "Massive unadjusted daily stock close"}
    except Exception:
        pass
    return None
