"""Application defaults computed from a small JSON policy file."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "app_defaults.json"
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def load_app_config(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or CONFIG_PATH
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    max_day = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
               31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(d.day, max_day))


def third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    first_friday = 1 + (4 - first.weekday()) % 7
    return date(year, month, first_friday + 14)


def next_monthly_expiries(today: date, count: int) -> list[date]:
    expiries: list[date] = []
    cursor = date(today.year, today.month, 1)
    while len(expiries) < count:
        exp = third_friday(cursor.year, cursor.month)
        if exp > today:
            expiries.append(exp)
        cursor = add_months(cursor, 1)
    return expiries


def ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def pretty_date(d: date, include_year: bool = False) -> str:
    value = f"{MONTH_NAMES[d.month - 1]} {ordinal(d.day)}"
    return f"{value} {d.year}" if include_year else value


def _db_date_range() -> tuple[date | None, date | None]:
    try:
        from app.data.db import get_db

        row = get_db(read_only=True).execute("SELECT MIN(trade_date), MAX(trade_date) FROM options").fetchone()
        if not row or not row[0] or not row[1]:
            return None, None
        return date.fromisoformat(str(row[0])[:10]), date.fromisoformat(str(row[1])[:10])
    except Exception:
        return None, None


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def build_theta_expiries(config: dict[str, Any], today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    theta_cfg = config.get("theta", {})
    months_forward = int(theta_cfg.get("months_forward", 6))
    expiries = next_monthly_expiries(today, months_forward)
    return [
        {
            "name": f"{MONTH_NAMES[exp.month - 1]} monthly expiry",
            "expiry": exp.isoformat(),
            "days_forward": (exp - today).days,
        }
        for exp in expiries
    ]


def build_app_defaults(config_path: Path | None = None) -> dict[str, Any]:
    config = load_app_config(config_path)
    today = date.today()
    db_min, db_max = _db_date_range()
    latest_data_date = db_max or today - timedelta(days=1)
    earliest_data_date = db_min or date.fromisoformat(config.get("timeline", {}).get("start_date", "2025-01-02"))
    theta_expiries = build_theta_expiries(config, today)

    prediction_cfg = config.get("prediction", {})
    window_months = int(prediction_cfg.get("observation_window_months", 4))
    target_index = int(prediction_cfg.get("target_expiry_index", 1))
    target_index = max(0, min(target_index, len(theta_expiries) - 1))
    target_expiry = date.fromisoformat(theta_expiries[target_index]["expiry"])
    obs_from = _month_start(add_months(latest_data_date, -window_months))

    timeline_cfg = config.get("timeline", {})
    max_timeline = add_months(
        date.fromisoformat(theta_expiries[-1]["expiry"]),
        int(timeline_cfg.get("extra_months_after_latest_expiry", 1)),
    )

    values = {
        "target_month": MONTH_NAMES[target_expiry.month - 1],
        "target_date_pretty": pretty_date(target_expiry, include_year=target_expiry.year != today.year),
        "target_days": str((target_expiry - latest_data_date).days),
        "theta_month": MONTH_NAMES[date.fromisoformat(theta_expiries[0]["expiry"]).month - 1],
    }
    samples = [template.format(**values) for template in config.get("sample_queries", [])]

    return {
        "today": today.isoformat(),
        "latest_data_date": latest_data_date.isoformat(),
        "earliest_data_date": earliest_data_date.isoformat(),
        "prediction": {
            "ticker": prediction_cfg.get("default_ticker", "SPY"),
            "obs_date_from": obs_from.isoformat(),
            "obs_date_to": latest_data_date.isoformat(),
            "target_date": target_expiry.isoformat(),
            "risk_free_rate": float(prediction_cfg.get("risk_free_rate", 0.04)),
            "solver": prediction_cfg.get("solver", "brent"),
            "kernel_smooth": bool(prediction_cfg.get("kernel_smooth", False)),
        },
        "theta": {
            "top": int(config.get("theta", {}).get("top", 100)),
            "hv_days": config.get("theta", {}).get("hv_days", "same_as_days_forward"),
            "expiries": theta_expiries,
        },
        "timeline": {
            "min_date": earliest_data_date.isoformat(),
            "max_date": max_timeline.isoformat(),
        },
        "sample_queries": samples,
    }


def build_theta_scan_plan(config_path: Path | None = None) -> list[dict[str, Any]]:
    config = load_app_config(config_path)
    theta_cfg = config.get("theta", {})
    hv_days = theta_cfg.get("hv_days", "same_as_days_forward")
    top = int(theta_cfg.get("top", 100))
    return [
        {
            "name": item["name"],
            "expiry": item["expiry"],
            "days_forward": item["days_forward"],
            "hv_days": item["days_forward"] if hv_days == "same_as_days_forward" else int(hv_days),
            "top": top,
        }
        for item in build_theta_expiries(config)
    ]
