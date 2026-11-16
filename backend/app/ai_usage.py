"""Durable, cross-worker request budgets, separate from the read-only market DB."""
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

logger = logging.getLogger(__name__)
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "var" / "ai_usage.sqlite3"


def limits() -> dict:
    try:
        values = {key: int(os.getenv(env, default)) for key, env, default in (
            ("per_minute", "AI_REQUESTS_PER_MINUTE", "4"),
            ("per_user_daily", "AI_USER_REQUESTS_PER_DAY", "100"),
            ("per_user_monthly", "AI_USER_REQUESTS_PER_MONTH", "200"),
            ("daily", "AI_REQUESTS_PER_DAY", "100"),
            ("monthly", "AI_REQUESTS_PER_MONTH", "200"),
            ("concurrent", "AI_MAX_CONCURRENT", "2"),
        )}
        if any(value < 0 for value in values.values()):
            raise ValueError("Negative limit")
        return values
    except ValueError as exc:
        raise HTTPException(503, "AI limits are not configured correctly.") from exc


@contextmanager
def connection():
    conn = None
    try:
        path = Path(os.getenv("AI_USAGE_DB_PATH", str(DEFAULT_PATH)))
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        conn = sqlite3.connect(path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE IF NOT EXISTS ai_requests (
            id TEXT PRIMARY KEY, subject TEXT NOT NULL, endpoint TEXT NOT NULL,
            started REAL NOT NULL, finished REAL, status TEXT NOT NULL,
            model_responses INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            thinking_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS ai_requests_started ON ai_requests(started)")
        conn.commit()
        yield conn
    except (sqlite3.Error, OSError) as exc:
        logger.error("AI usage storage unavailable (%s)", type(exc).__name__)
        raise HTTPException(503, "AI usage controls are temporarily unavailable. Please try later.") from exc
    finally:
        if conn is not None:
            conn.close()


def _periods(now: float) -> tuple[float, float]:
    day = datetime.fromtimestamp(now, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return day.timestamp(), day.replace(day=1).timestamp()


def reserve(subject: str, endpoint: str) -> str:
    quota, now = limits(), time.time()
    day, month = _periods(now)
    with connection() as conn:
        # Serialize check + insert across Uvicorn processes. In-memory counters
        # would grant each worker its own allowance and reset on every restart.
        conn.execute("BEGIN IMMEDIATE")
        recent = conn.execute("SELECT count(*) FROM ai_requests WHERE subject=? AND started>?",
                              (subject, now - 60)).fetchone()[0]
        daily = conn.execute("SELECT count(*) FROM ai_requests WHERE started>=?", (day,)).fetchone()[0]
        monthly = conn.execute("SELECT count(*) FROM ai_requests WHERE started>=?", (month,)).fetchone()[0]
        user_daily, user_monthly = conn.execute(
            "SELECT coalesce(sum(started>=?),0),count(*) FROM ai_requests WHERE subject=? AND started>=?",
            (day, subject, month)).fetchone()
        # Dead workers may leave reservations behind. The lease is much longer
        # than the 180s chat timeout / two 45s news calls; attempts stay charged.
        conn.execute("UPDATE ai_requests SET status='abandoned', finished=? WHERE status='running' AND started<?",
                     (now, now - 600))
        active = conn.execute("SELECT count(*) FROM ai_requests WHERE status='running'").fetchone()[0]
        reason = None
        if monthly >= quota["monthly"]:
            reason = "The monthly AI request budget is exhausted (resets on the first, UTC)."
        elif daily >= quota["daily"]:
            reason = "The daily AI request budget is exhausted (resets at midnight UTC)."
        elif user_monthly >= quota["per_user_monthly"]:
            reason = "Your monthly AI request allowance is exhausted (resets on the first, UTC)."
        elif user_daily >= quota["per_user_daily"]:
            reason = "Your daily AI request allowance is exhausted (resets at midnight UTC)."
        elif recent >= quota["per_minute"]:
            reason = "Too many AI requests. Wait a minute before trying again."
        elif active >= quota["concurrent"]:
            reason = "AI is busy. Wait for a running request to finish."
        if reason:
            conn.commit()
            raise HTTPException(429, reason, headers={"Retry-After": "60"})
        request_id = uuid4().hex
        conn.execute("INSERT INTO ai_requests(id,subject,endpoint,started,status) VALUES (?,?,?,?,'running')",
                     (request_id, subject, endpoint, now))
        conn.commit()
    return request_id


@dataclass
class Usage:
    model_responses: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    total_tokens: int = 0
    failed: bool = False


_current: ContextVar[Usage | None] = ContextVar("ai_usage", default=None)


def record_usage(response) -> None:
    usage = _current.get()
    if usage is None:
        return
    metadata = getattr(response, "usage_metadata", None)
    usage.model_responses += 1
    for field, provider_field in (("input_tokens", "prompt_token_count"),
                                   ("output_tokens", "candidates_token_count"),
                                   ("thinking_tokens", "thoughts_token_count"),
                                   ("total_tokens", "total_token_count")):
        value = getattr(metadata, provider_field, None)
        if isinstance(value, int) and value >= 0:
            setattr(usage, field, getattr(usage, field) + value)


def mark_failed() -> None:
    if (usage := _current.get()) is not None:
        usage.failed = True


@contextmanager
def metered_request(subject: str, endpoint: str):
    request_id = reserve(subject, endpoint)
    usage = Usage()
    token = _current.set(usage)
    try:
        yield
    except BaseException:
        usage.failed = True
        raise
    finally:
        _current.reset(token)
        with connection() as conn:
            conn.execute("""UPDATE ai_requests SET finished=?, status=?, model_responses=?,
                input_tokens=?, output_tokens=?, thinking_tokens=?, total_tokens=? WHERE id=?""",
                (time.time(), "failed" if usage.failed else "finished", usage.model_responses,
                 usage.input_tokens, usage.output_tokens, usage.thinking_tokens, usage.total_tokens, request_id))
            conn.commit()


def usage_summary(subject: str) -> dict:
    day, month = _periods(time.time())
    with connection() as conn:
        row = conn.execute("""SELECT count(*) AS monthly_requests,
            coalesce(sum(started>=?),0) AS daily_requests,
            coalesce(sum(subject=?),0) AS your_monthly_requests,
            coalesce(sum(subject=? AND started>=?),0) AS your_daily_requests,
            coalesce(sum(CASE WHEN subject=? THEN total_tokens ELSE 0 END),0) AS your_reported_total_tokens
            FROM ai_requests WHERE started>=?""", (day, subject, subject, day, subject, month)).fetchone()
    return {**dict(row), "limits": limits(), "timezone": "UTC",
            "budget_unit": "requests", "billing_note": "Request limits are not a dollar cap. Token totals exclude unreported/unfinished responses and do not include Search charges."}
