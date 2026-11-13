"""Actual daily stock closes, kept separate from the historical options database."""

import json
import math
import os
import re
import tempfile
import time
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.data.fetcher import CACHE_DIR, get_client

STOCK_CACHE = CACHE_DIR / "stock_daily"
logger = logging.getLogger(__name__)


def _publish_cache(path, payload):
    STOCK_CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=STOCK_CACHE, delete=False) as output:
        temporary = Path(output.name)
        json.dump(payload, output)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def prefetch_stock_closes(client, tickers: list[str], day: date):
    """Warm raw close caches with one grouped request when the plan permits it."""
    today = datetime.now(ZoneInfo("America/New_York")).date()
    if day >= today:
        return
    path = STOCK_CACHE / f"_market_raw_{day}.json"
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
        if data.get("fetched_on") != today.isoformat():
            closes = {}
            for bar in client.get_grouped_daily_aggs(day, adjusted=False):
                observed = datetime.fromtimestamp(bar.timestamp / 1000, ZoneInfo("America/New_York")).date()
                if observed == day and bar.close is not None and math.isfinite(bar.close) and bar.close > 0:
                    closes[bar.ticker] = float(bar.close)
            data = {"fetched_on": today.isoformat(), "closes": closes}
            _publish_cache(path, data)
        for ticker in tickers:
            price = data["closes"].get(ticker)
            if price is not None:
                _publish_cache(STOCK_CACHE / f"{ticker}_{day}_{day}.json", {
                    "fetched_on": today.isoformat(), "start": str(day), "end": str(day),
                    "adjusted": False, "closes": {str(day): price},
                })
    except Exception:
        logger.warning("Bulk stock closes unavailable; falling back to individual dated requests")


def daily_closes(ticker: str, start: date, end: date, *, allow_api: bool = True, adjusted: bool = False, client=None, rate_limit_retries: int = 0) -> dict[str, float]:
    """Return dated daily closes, never a live partial bar.

    Unadjusted prices match the historical option strikes. Exact-range cache
    files expire after one day to pick up provider corrections when online.
    Use adjusted=True for split-adjusted volatility history, not strike pricing.
    Set allow_api=False for cache-only access.
    """
    ticker = ticker.upper()
    if not re.fullmatch(r"[A-Z0-9.^-]{1,20}", ticker):
        raise ValueError("Invalid stock ticker")
    today = datetime.now(ZoneInfo("America/New_York")).date()
    end = min(end, today - timedelta(days=1))
    if start > end:
        return {}
    path = STOCK_CACHE / f"{ticker}_{start}_{end}{'_adjusted' if adjusted else ''}.json"
    if path.exists():
        data = json.loads(path.read_text())
        if not allow_api or data.get("fetched_on") == today.isoformat():
            return data["closes"]
    # A complete wider download can serve several expiry/HV windows.
    for cached_path in sorted(STOCK_CACHE.glob(f"{ticker}_*.json")):
        if cached_path == path:
            continue
        try:
            cached = json.loads(cached_path.read_text())
            if (cached.get("adjusted") == adjusted
                    and cached.get("start", "9999") <= start.isoformat()
                    and cached.get("end", "") >= end.isoformat()
                    and (not allow_api or cached.get("fetched_on") == today.isoformat())):
                return {day: close for day, close in cached["closes"].items() if start.isoformat() <= day <= end.isoformat()}
        except (ValueError, KeyError, OSError):
            continue
    if not allow_api:
        return {}
    api = client or get_client()
    for attempt in range(rate_limit_retries + 1):
        try:
            bars = list(api.list_aggs(
                ticker, 1, "day", start.isoformat(), end.isoformat(),
                adjusted=adjusted, sort="asc", limit=50000,
            ))
            break
        except Exception as exc:
            # urllib3 exposes exhausted HTTP-status retries through ResponseError text.
            if "429" not in str(exc) or attempt >= rate_limit_retries:
                raise
            logger.warning("Stock data rate limited for %s; waiting 65 seconds before retry %s", ticker, attempt + 1)
            time.sleep(65)
    closes = {}
    for bar in bars:
        day = datetime.fromtimestamp(bar.timestamp / 1000, ZoneInfo("America/New_York")).date()
        close = float(bar.close)
        if start <= day <= end and math.isfinite(close) and close > 0:
            closes[day.isoformat()] = close
    # Publish only complete API responses; interrupted requests never poison cache.
    _publish_cache(path, {"fetched_on": today.isoformat(), "start": start.isoformat(), "end": end.isoformat(), "adjusted": adjusted, "closes": closes})
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
