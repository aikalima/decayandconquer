"""Read-only MCP server for Theta Plays data.

Run with:
    python -m app.theta_mcp
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from math import exp
from typing import Literal

from mcp.server import MCPServer

from app.data.db import (
    get_available_theta_expiries,
    get_latest_theta_scan,
    get_latest_theta_scan_by_expiry,
    get_theta_results,
    set_read_only,
)

set_read_only(True)
logging.getLogger("app.data.db").setLevel(logging.WARNING)

mcp = MCPServer(
    "decay-theta-plays",
    title="Decay And Conquer Theta Plays",
    description="Read-only access to precomputed Theta Plays option-premium scans.",
    instructions=(
        "Use these tools to inspect precomputed Theta Plays scans. "
        "Results are read-only and may be stale; always check scanned_at."
    ),
    log_level="ERROR",
)

Category = Literal["highest_premium", "expensive_calls", "expensive_puts"]


def _configured_expiries() -> list[dict]:
    try:
        from app.defaults import build_app_defaults

        return build_app_defaults().get("theta", {}).get("expiries", [])
    except Exception:
        return []


def _scan_public(scan: dict | None) -> dict | None:
    if not scan:
        return None
    return {
        "scan_id": scan.get("scan_id"),
        "expiry": scan.get("expiry"),
        "days_forward": scan.get("days_forward"),
        "hv_days": scan.get("hv_days"),
        "tickers_scanned": scan.get("tickers_scanned"),
        "tickers_failed": scan.get("tickers_failed"),
        "scan_time_seconds": scan.get("scan_time_seconds"),
        "scanned_at": scan.get("created_at", ""),
    }


def _resolve_scan(expiry: str | None = None) -> dict | None:
    if expiry:
        try:
            expiry = date.fromisoformat(expiry).isoformat()
        except ValueError:
            raise ValueError("expiry must be a valid YYYY-MM-DD date")
        return get_latest_theta_scan_by_expiry(expiry)

    for item in _configured_expiries():
        configured_expiry = item.get("expiry")
        if not configured_expiry:
            continue
        scan = get_latest_theta_scan_by_expiry(configured_expiry)
        if scan:
            return scan

    return get_latest_theta_scan(None)


def _sort_rows(rows: list[dict], category: Category) -> list[dict]:
    sort_keys = {
        "highest_premium": "rank_score",
        "expensive_calls": "call_rank_score",
        "expensive_puts": "put_rank_score",
    }
    fallback_keys = {
        "highest_premium": "avg_premium",
        "expensive_calls": "call_premium",
        "expensive_puts": "put_premium",
    }
    key = sort_keys[category]
    fallback = fallback_keys[category]
    return sorted(rows, key=lambda row: row.get(key) or row.get(fallback, 0) or 0, reverse=True)


def _round_float(value: object, digits: int = 4) -> object:
    if isinstance(value, float):
        return round(value, digits)
    return value


def _scan_date(scan: dict | None) -> date:
    if scan and scan.get("created_at"):
        try:
            return datetime.fromisoformat(str(scan["created_at"])).date()
        except ValueError:
            pass
    return date.today()


def _spread_pct(bid: object, ask: object, mid: object) -> float | None:
    if not all(isinstance(value, (int, float)) for value in [bid, ask, mid]):
        return None
    if mid <= 0:
        return None
    return round((ask - bid) / mid * 100, 2)


def _quality_diagnostics(row: dict, scan: dict | None = None) -> dict:
    call_mid = row.get("call_mid")
    put_mid = row.get("put_mid")
    call_bid = row.get("call_bid")
    call_ask = row.get("call_ask")
    put_bid = row.get("put_bid")
    put_ask = row.get("put_ask")
    call_iv = row.get("call_iv") or 0
    put_iv = row.get("put_iv") or 0
    spot = row.get("spot")
    call_strike = row.get("call_strike")
    put_strike = row.get("put_strike")

    call_spread_pct = _spread_pct(call_bid, call_ask, call_mid)
    put_spread_pct = _spread_pct(put_bid, put_ask, put_mid)
    bid_ask_same = (
        isinstance(call_bid, (int, float))
        and isinstance(call_ask, (int, float))
        and isinstance(put_bid, (int, float))
        and isinstance(put_ask, (int, float))
        and call_bid > 0
        and call_ask > 0
        and put_bid > 0
        and put_ask > 0
        and call_bid == call_ask
        and put_bid == put_ask
    )

    iv_skew_abs = round(abs(put_iv - call_iv), 4)
    iv_skew_ratio = None
    if call_iv > 0 and put_iv > 0:
        iv_skew_ratio = round(max(call_iv, put_iv) / min(call_iv, put_iv), 2)

    parity = None
    if (
        isinstance(spot, (int, float))
        and isinstance(call_strike, (int, float))
        and isinstance(put_strike, (int, float))
        and isinstance(call_mid, (int, float))
        and isinstance(put_mid, (int, float))
        and abs(call_strike - put_strike) < 0.01
    ):
        expiry = date.fromisoformat(str(row["expiry"]))
        days_to_expiry = max((expiry - _scan_date(scan)).days, 1)
        t = days_to_expiry / 365
        expected = spot - call_strike * exp(-0.04 * t)
        observed = call_mid - put_mid
        gap = observed - expected
        parity = {
            "basis": "European no-dividend approximation",
            "days_to_expiry": days_to_expiry,
            "expected_call_minus_put": round(expected, 4),
            "observed_call_minus_put": round(observed, 4),
            "gap": round(gap, 4),
            "gap_abs": round(abs(gap), 4),
        }

    warnings = [w.strip() for w in str(row.get("quality_warnings") or "").split(";") if w.strip()]
    if row.get("call_price_source") and row.get("call_price_source") != "last_quote":
        warnings.append(f"Call price source is {row.get('call_price_source')}, not bid/ask quote.")
    if row.get("put_price_source") and row.get("put_price_source") != "last_quote":
        warnings.append(f"Put price source is {row.get('put_price_source')}, not bid/ask quote.")
    if bid_ask_same:
        warnings.append("Bid equals ask on both legs; values may be marks or stale quotes, not executable spreads.")
    if iv_skew_ratio and iv_skew_ratio >= 2:
        warnings.append("Large call/put IV skew; verify timing, dividends, earnings, and parity before trusting side-specific premium.")
    if parity and parity["gap_abs"] >= max(0.5, (spot or 0) * 0.0025):
        warnings.append("Put-call parity gap is large under a no-dividend approximation; dividend effects or stale/asynchronous marks may distort IV.")

    return {
        "call_spread_pct": call_spread_pct,
        "put_spread_pct": put_spread_pct,
        "bid_ask_same": bid_ask_same,
        "iv_skew_abs": iv_skew_abs,
        "iv_skew_ratio": iv_skew_ratio,
        "put_iv_minus_call_iv": round(put_iv - call_iv, 4),
        "put_call_parity": parity,
        "quality_score": row.get("quality_score"),
        "rank_score": row.get("rank_score"),
        "call_price_source": row.get("call_price_source"),
        "put_price_source": row.get("put_price_source"),
        "call_open_interest": row.get("call_open_interest"),
        "put_open_interest": row.get("put_open_interest"),
        "call_volume": row.get("call_volume"),
        "put_volume": row.get("put_volume"),
        "call_bid_size": row.get("call_bid_size"),
        "call_ask_size": row.get("call_ask_size"),
        "put_bid_size": row.get("put_bid_size"),
        "put_ask_size": row.get("put_ask_size"),
        "call_quote_updated_ns": row.get("call_quote_updated_ns"),
        "put_quote_updated_ns": row.get("put_quote_updated_ns"),
        "underlying_updated_ns": row.get("underlying_updated_ns"),
        "warnings": list(dict.fromkeys(warnings)),
    }


def _public_row(row: dict, scan: dict | None = None, include_diagnostics: bool = True) -> dict:
    fields = [
        "ticker",
        "spot",
        "expiry",
        "call_strike",
        "call_bid",
        "call_ask",
        "call_mid",
        "call_iv",
        "put_strike",
        "put_bid",
        "put_ask",
        "put_mid",
        "put_iv",
        "hv_20",
        "call_premium",
        "put_premium",
        "avg_premium",
        "call_efficiency",
        "put_efficiency",
        "beta",
        "pct_change_5d",
        "call_price_source",
        "put_price_source",
        "call_open_interest",
        "put_open_interest",
        "call_volume",
        "put_volume",
        "call_bid_size",
        "call_ask_size",
        "put_bid_size",
        "put_ask_size",
        "call_quality_score",
        "put_quality_score",
        "quality_score",
        "call_rank_score",
        "put_rank_score",
        "rank_score",
        "quality_warnings",
    ]
    output = {field: _round_float(row.get(field)) for field in fields}
    if include_diagnostics:
        output["diagnostics"] = _quality_diagnostics(row, scan)
    return output


def _interpret_row(row: dict) -> str:
    avg = row.get("avg_premium", 0) or 0
    call = row.get("call_premium", 0) or 0
    put = row.get("put_premium", 0) or 0
    side = "calls" if call > put else "puts" if put > call else "both sides"
    diagnostics = row.get("diagnostics") or {}
    warnings = diagnostics.get("warnings") or []
    caveat = f" Key caveat: {warnings[0]}" if warnings else ""
    return (
        f"{row.get('ticker')} has an average IV/HV premium of {avg:.2f}x, "
        f"with the richer side currently in {side}. Higher values can indicate "
        "option premium priced above recent realized movement, but scan freshness, "
        "earnings, liquidity, spreads, dividends, and position sizing still matter."
        f"{caveat}"
    )


@mcp.tool(
    description=(
        "List Theta Plays expiries. Configured future expiries are included "
        "with has_scan=false until a batch scan has been saved."
    )
)
def list_theta_expiries(include_configured: bool = True) -> dict:
    """List available and configured Theta Plays expiries."""
    scanned_by_expiry = {item["expiry"]: item for item in get_available_theta_expiries()}
    expiries: list[dict] = []
    seen: set[str] = set()

    if include_configured:
        for item in _configured_expiries():
            expiry = item["expiry"]
            scan = get_latest_theta_scan_by_expiry(expiry)
            scanned = scanned_by_expiry.get(expiry)
            expiries.append({
                "expiry": expiry,
                "name": item.get("name", ""),
                "days_forward": item.get("days_forward"),
                "has_scan": scan is not None,
                "last_scanned": scanned.get("last_scanned", "") if scanned else "",
                "tickers_scanned": scanned.get("tickers_scanned", 0) if scanned else 0,
                "scan": _scan_public(scan),
            })
            seen.add(expiry)

    for scanned in scanned_by_expiry.values():
        expiry = scanned["expiry"]
        if expiry in seen:
            continue
        scan = get_latest_theta_scan_by_expiry(expiry)
        expiries.append({
            "expiry": expiry,
            "name": "",
            "days_forward": scan.get("days_forward") if scan else None,
            "has_scan": True,
            "last_scanned": scanned.get("last_scanned", ""),
            "tickers_scanned": scanned.get("tickers_scanned", 0),
            "scan": _scan_public(scan),
        })

    return {"expiries": sorted(expiries, key=lambda item: item["expiry"])}


@mcp.tool(
    description=(
        "Return ranked Theta Plays rows for a saved scan. category can be "
        "highest_premium, expensive_calls, or expensive_puts."
    )
)
def get_theta_plays(
    expiry: str | None = None,
    category: Category = "highest_premium",
    limit: int = 10,
    include_diagnostics: bool = True,
) -> dict:
    """Get ranked Theta Plays for an expiry."""
    limit = max(1, min(int(limit), 100))
    scan = _resolve_scan(expiry)
    if not scan:
        return {
            "error": "No theta scan results found. Run python programs/run_theta_scan.py --config config/app_defaults.json first.",
            "expiry": expiry,
        }

    rows = _sort_rows(get_theta_results(scan["scan_id"]), category)[:limit]
    return {
        "category": category,
        "limit": limit,
        "scan": _scan_public(scan),
        "rows": [_public_row(row, scan, include_diagnostics) for row in rows],
    }


@mcp.tool(
    description=(
        "Return one ticker's Theta Plays row and a concise interpretation. "
        "If expiry is omitted, the first configured scanned expiry is used."
    )
)
def get_theta_play_detail(ticker: str, expiry: str | None = None) -> dict:
    """Get detailed Theta Plays data for one ticker."""
    normalized = ticker.strip().upper()
    if not normalized:
        return {"error": "ticker is required"}

    scan = _resolve_scan(expiry)
    if not scan:
        return {
            "error": "No theta scan results found. Run python programs/run_theta_scan.py --config config/app_defaults.json first.",
            "ticker": normalized,
            "expiry": expiry,
        }

    for row in get_theta_results(scan["scan_id"]):
        if str(row.get("ticker", "")).upper() == normalized:
            public = _public_row(row, scan)
            return {
                "ticker": normalized,
                "scan": _scan_public(scan),
                "row": public,
                "diagnostics": public["diagnostics"],
                "interpretation": _interpret_row(public),
            }

    return {
        "error": f"{normalized} was not found in the selected theta scan.",
        "ticker": normalized,
        "scan": _scan_public(scan),
    }


@mcp.resource(
    "theta://expiries",
    description="JSON listing configured and scanned Theta Plays expiries.",
    mime_type="application/json",
)
def theta_expiries_resource() -> dict:
    """Expose theta expiries as an MCP resource."""
    return list_theta_expiries(include_configured=True)


if __name__ == "__main__":
    mcp.run()
