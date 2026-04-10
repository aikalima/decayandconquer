"""Market context: fetch news/events relevant to a ticker during a date range.

Uses Google Gemini to identify significant market events that likely
influenced options pricing during the observation period.
"""

from __future__ import annotations
import json
import logging
import os
from datetime import date

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """You are a financial markets analyst. List the most significant market events that likely influenced options pricing for the stock ticker {ticker} during the EXACT date range {obs_from} to {obs_to} (inclusive).

CRITICAL DATE RULES:
- Every event date MUST fall within {obs_from} to {obs_to}. No exceptions.
- Dates must be in YYYY-MM-DD format.
- Do NOT include events before {obs_from} or after {obs_to}.
- Double-check the year. The range spans {obs_from} to {obs_to}.

Consider:
- Company-specific news: earnings, guidance, analyst upgrades/downgrades, M&A, management changes
- Macro events: Fed rate decisions, CPI/inflation data, jobs reports, GDP
- Geopolitical events: trade wars, sanctions, conflicts, elections
- Sector-wide moves: regulatory changes, competitor news, industry trends

For each event return:
- date: the exact date it occurred (YYYY-MM-DD), must be between {obs_from} and {obs_to}
- headline: one-line summary (max 80 chars)
- category: one of "earnings", "macro", "geopolitical", "sector", "company", "regulatory"
- impact: one-line explanation of how this likely affected {ticker}'s options pricing

Return 3-8 events, ordered by relevance. Only include events you are confident actually occurred within this date range. If unsure, return an empty list.

Respond with ONLY valid JSON, no markdown fences: {{"events": [...]}}"""


def fetch_market_context(
    ticker: str,
    obs_from: str,
    obs_to: str,
) -> list[dict]:
    """Call Gemini to get market events for the observation period.

    Returns a list of event dicts with keys: date, headline, category, impact.
    Returns empty list on any failure.
    """
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        logger.warning("GOOGLE_API_KEY not set, skipping market context")
        return []

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        prompt = PROMPT_TEMPLATE.format(
            ticker=ticker,
            obs_from=obs_from,
            obs_to=obs_to,
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        text = response.text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3].strip()

        parsed = json.loads(text)
        events = parsed.get("events", [])

        # Validate structure and enforce date range
        range_start = date.fromisoformat(obs_from)
        range_end = date.fromisoformat(obs_to)

        valid = []
        for e in events:
            if not all(k in e for k in ("date", "headline", "category", "impact")):
                continue
            # Validate and clamp date to observation range
            try:
                evt_date = date.fromisoformat(str(e["date"]))
            except ValueError:
                continue
            if evt_date < range_start or evt_date > range_end:
                logger.warning(f"Dropping event outside range: {e['date']} not in {obs_from}..{obs_to}")
                continue
            valid.append({
                "date": evt_date.isoformat(),
                "headline": str(e["headline"])[:100],
                "category": str(e["category"]),
                "impact": str(e["impact"])[:200],
            })
        return valid

    except Exception as e:
        logger.error(f"Market context fetch failed: {e}")
        return []
