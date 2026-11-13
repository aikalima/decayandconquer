"""Shared, conservative research-screen checks for saved and live theta rows."""

from datetime import date, datetime, timezone
from math import isfinite

CATEGORIES = {
    "highest_premium": ("rank_score", "avg_premium", ("call", "put")),
    "expensive_calls": ("call_rank_score", "call_premium", ("call",)),
    "expensive_puts": ("put_rank_score", "put_premium", ("put",)),
}
POLICY = {
    "version": 1,
    "max_age_calendar_days": 4,
    "min_open_interest": 10,
    "max_quote_spread_pct": 20,
    "max_iv_ratio": 2,
    "description": "Research checks, not a trade recommendation. Dated daily marks may qualify, but are not executable quotes. Four calendar days accommodates weekends; it is not an exchange calendar.",
}


def number(value):
    return float(value) if isinstance(value, (int, float)) and isfinite(value) else None


def timestamp(value):
    try:
        if number(value) is not None:
            result = datetime.fromtimestamp(value / 1e9, timezone.utc)
        else:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def assess_row(row, scan=None, *, now=None):
    """Re-evaluate freshness at read time, without altering saved scan data."""
    now = now or datetime.now(timezone.utc)
    scan = scan or {}
    result = {key: None if isinstance(value, float) and not isfinite(value) else value for key, value in row.items()}
    flags = []

    def flag(code, message, side="both", blocking=True):
        flags.append(dict(code=code, message=message, side=side, blocking=blocking))

    def freshness(value, label, side="both"):
        dt = timestamp(value)
        if dt is None:
            flag(f"{label}_unknown", f"{label.replace('_', ' ').capitalize()} date is unknown.", side)
        elif (now - dt).total_seconds() > 4 * 86400:
            flag(f"{label}_stale", f"{label.replace('_', ' ').capitalize()} is over four calendar days old.", side)
        elif (dt - now).total_seconds() > 300:
            flag(f"{label}_future", f"{label.replace('_', ' ').capitalize()} timestamp is in the future.", side)
        if dt and isinstance(value, str) and len(value) == 10:
            return value
        return dt.isoformat() if dt else None

    scanned_at = freshness(scan.get("created_at") or scan.get("scanned_at") or scan.get("scan_id"), "scan")
    try:
        if date.fromisoformat(str(row.get("expiry"))) <= now.date():
            flag("expired", "The contract has expired or expires today.")
        if scan.get("expiry") and str(scan["expiry"]) != str(row.get("expiry")):
            flag("expiry_mismatch", "Contract expiry differs from the requested scan expiry.")
    except ValueError:
        flag("expiry_unknown", "Contract expiry is unknown.")

    spot_at = freshness(row.get("underlying_updated_ns") or row.get("spot_date"), "underlying")
    if row.get("spot_source") not in ("massive_daily_unadjusted", "massive_snapshot"):
        flag("spot_unverified", "Underlying price source is estimated or unverified; rerun this scan.")
    if not number(row.get("spot")) or row["spot"] <= 0:
        flag("spot_invalid", "Underlying price is not positive and finite.")
    hv = number(row.get("hv_20"))
    hv_days = number(row.get("hv_days") or scan.get("hv_days"))
    if row.get("hv_source") != "massive_daily_adjusted":
        flag("hv_unverified", "Historical volatility was not verified against actual adjusted stock closes.")
    if not hv or hv <= 0.01:
        flag("hv_unreliable", "Historical volatility is at or below 1%; ratios are unstable at this baseline.")
    if not hv_days or (number(row.get("hv_observations")) or 0) < hv_days + 1:
        flag("hv_insufficient", "Insufficient stock closes for the requested return window.")
    freshness(row.get("hv_end_date"), "volatility_history")

    ivs = [number(row.get(f"{side}_iv")) or 0 for side in ("call", "put")]
    skew = max(ivs) / min(ivs) if min(ivs) > 0 else None
    if skew is not None and skew >= 2:
        flag("iv_asymmetry", "Call/put IV differs by at least 2x; check timing, distributions and model assumptions.")

    legs = {}
    for side in ("call", "put"):
        source = row.get(f"{side}_price_source") or "unknown"
        stamp_field = {"last_quote": "quote", "day_close": "day", "last_trade": "trade"}.get(source)
        price_at = freshness(row.get(f"{side}_{stamp_field}_updated_ns") if stamp_field else None, f"{side}_price", side)
        bid, ask, mark = [number(row.get(f"{side}_{field}")) for field in ("bid", "ask", "mid")]
        spread = (ask - bid) / ((ask + bid) / 2) * 100 if bid and ask and bid > 0 and ask >= bid else None
        score = 100.0
        if source != "last_quote":
            score -= 35
            flag(f"{side}_mark", f"{side.capitalize()} uses {source}; not an executable bid/ask quote.", side, source not in ("day_close", "last_trade"))
        elif spread is None or spread == 0 or spread >= 20:
            flag(f"{side}_spread", f"{side.capitalize()} quote is missing, crossed, locked or at least 20% wide.", side)
        elif spread >= 10:
            score -= 15
            flag(f"{side}_wide", f"{side.capitalize()} spread exceeds 10% of midpoint.", side, False)
        oi = number(row.get(f"{side}_open_interest"))
        volume = number(row.get(f"{side}_volume"))
        if oi is None or oi < 10:
            flag(f"{side}_liquidity", f"{side.capitalize()} open interest is unknown or below 10 contracts.", side)
        elif oi < 100:
            score -= 12
        if volume is None or volume <= 0:
            flag(f"{side}_volume", f"{side.capitalize()} daily volume is missing or zero.", side)
        if not mark or mark <= 0 or not number(row.get(f"{side}_iv")) or row[f"{side}_iv"] <= 0:
            flag(f"{side}_invalid", f"{side.capitalize()} price or IV is unavailable.", side)
        if row.get(f"{side}_iv_source") not in ("massive_snapshot", "european_no_dividend"):
            flag(f"{side}_iv_unverified", f"{side.capitalize()} IV origin is unknown or substituted from the other side.", side)
        if price_at and spot_at and abs((timestamp(price_at) - timestamp(spot_at)).total_seconds()) > 86400:
            flag(f"{side}_timing", f"{side.capitalize()} and underlying timestamps are more than 24 hours apart.", side)
        legs[side] = dict(price_source=source, price_at=price_at, spread_pct=round(spread, 2) if spread is not None else None, quality_score=max(score, 0))

    eligibility = {}
    ranking = {}
    for category, (score_key, ratio_key, sides) in CATEGORIES.items():
        reasons = [f["message"] for f in flags if f["blocking"] and (f["side"] == "both" or f["side"] in sides)]
        ratio = number(row.get(ratio_key))
        if ratio is None or ratio <= 0:
            reasons.append("Volatility richness is missing or invalid.")
        score = (ratio or 0) * min(legs[s]["quality_score"] for s in sides) / 100
        calculated_score = score
        saved_score = number(row.get(score_key))
        if saved_score is not None:
            score = min(score, max(0, saved_score))
        if score <= 0:
            reasons.append("Quality-adjusted score is zero.")
        result[score_key] = round(score, 4)
        ranking[category] = dict(raw_ratio=ratio, quality_multiplier=min(legs[s]["quality_score"] for s in sides) / 100,
                                 calculated_score=round(calculated_score, 4), saved_score=saved_score, effective_score=result[score_key])
        eligibility[category] = dict(eligible=not reasons, reasons=reasons)
    result["quality"] = dict(scanned_at=scanned_at, underlying_at=spot_at, legs=legs, flags=flags, eligibility=eligibility, ranking=ranking, iv_skew_ratio=skew)
    return result


def rank_rows(rows, category, *, include_flagged=False):
    key = CATEGORIES[category][0]
    selected = [r for r in rows if include_flagged or r["quality"]["eligibility"][category]["eligible"]]
    return sorted(selected, key=lambda r: (-(number(r.get(key)) or 0), str(r.get("ticker", ""))))


def scan_response(rows, scan, *, include_flagged=False, now=None):
    assessed = [assess_row(row, scan, now=now) for row in rows]
    return {
        **{category: rank_rows(assessed, category, include_flagged=include_flagged) for category in CATEGORIES},
        "quality_policy": POLICY,
        "quality_counts": {category: {"eligible": sum(r["quality"]["eligibility"][category]["eligible"] for r in assessed), "total": len(assessed)} for category in CATEGORIES},
        "include_flagged": include_flagged,
    }
