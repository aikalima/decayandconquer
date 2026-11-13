"""Read-only coverage and freshness diagnostics; never claims an import succeeded."""

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from time import time

from app.data import db


@lru_cache(maxsize=2)
def _coverage(path: str, modified_ns: int, minute: int) -> dict:
    conn = db.get_db(read_only=True)
    row_count, first, last = conn.execute(
        "SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM options"
    ).fetchone()
    if first is None:
        return {"rows": 0, "first_date": None, "latest_date": None, "unverified_weekday_gaps": []}
    observed = {row[0] for row in conn.execute("SELECT DISTINCT trade_date FROM options").fetchall()}
    gaps = []
    cursor = first
    while cursor <= last:
        if cursor.weekday() < 5 and cursor not in observed:
            gaps.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return {"rows": row_count, "first_date": str(first), "latest_date": str(last),
            "unverified_weekday_gaps": gaps}


def get_data_health(today: date | None = None) -> dict:
    today = today or date.today()
    now = datetime.now(timezone.utc)
    result = {"checked_at": now.isoformat(), "status": "unavailable", "options": None,
              "theta_scans": [], "warnings": [],
              "underlying_prices": "Actual daily stock closes are fetched on demand for prediction dates; estimates are explicitly flagged.",
              "coverage_basis": "Dataset-wide weekday coverage; market holidays are not excluded. Not per-ticker completeness.",
              "refresh_status": "unknown"}
    try:
        coverage = _coverage(str(db.DB_PATH), db.DB_PATH.stat().st_mtime_ns, int(time() // 60)).copy()
        last = coverage["latest_date"]
        coverage["age_calendar_days"] = (today - date.fromisoformat(last)).days if last else None
        result["options"] = coverage
        if last is None:
            result["status"] = "empty"
        elif coverage["age_calendar_days"] > 4:
            result["status"] = "stale"
            result["warnings"].append(f"Options data ends {last}. Refresh before interpreting results as current market conditions.")
        else:
            result["status"] = "recent"
        if coverage["unverified_weekday_gaps"]:
            result["warnings"].append("Some weekdays have no options rows. These may be market holidays or missing imports; they have not been classified.")
        try:
            for row in db.get_available_theta_expiries():
                stamp = row.get("last_scanned")
                parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00")) if stamp else None
                if parsed and parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                result["theta_scans"].append({**row, "last_scanned": str(stamp) if stamp else None,
                    "age_hours": round(max(0, (now-parsed).total_seconds()/3600), 1) if parsed else None,
                    "expired": str(row["expiry"]) < today.isoformat()})
        except Exception:
            result["warnings"].append("Theta scan metadata is unavailable.")
    except Exception:
        result["warnings"].append("The local options database is unavailable or locked. Refresh status cannot be determined.")
    return result
