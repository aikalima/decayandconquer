"""Market context: fetch news/events relevant to a ticker during a date range.

Uses Anthropic Claude with web search to find real, verifiable market events
that influenced options pricing during the observation period. The previous
Google Gemini implementation is kept as an alternate helper.
"""

from __future__ import annotations
import json
import logging
import os
from datetime import date

logger = logging.getLogger(__name__)

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"

PROMPT_TEMPLATE = """Search for the most significant market events that affected the stock {ticker} between {obs_from} and {obs_to}. Use web search to find real news articles from financial sources like Yahoo Finance, Reuters, Bloomberg, CNBC, MarketWatch, and similar.

CRITICAL DATE RULES:
- Every event date MUST fall within {obs_from} to {obs_to}. No exceptions.
- Dates must be in YYYY-MM-DD format.
- Only include events you found in actual search results. Do not guess or fabricate.

Search for:
- {ticker} earnings, guidance, analyst upgrades/downgrades between {obs_from} and {obs_to}
- Federal Reserve rate decisions, CPI data, jobs reports between {obs_from} and {obs_to}
- Geopolitical events affecting markets between {obs_from} and {obs_to}
- Sector news relevant to {ticker} between {obs_from} and {obs_to}

For each event return:
- date: the exact date it occurred (YYYY-MM-DD), must be between {obs_from} and {obs_to}
- headline: one-line summary (max 80 chars)
- category: one of "earnings", "macro", "geopolitical", "sector", "company", "regulatory"
- impact: one-line explanation of how this likely affected {ticker}'s options pricing
- source: the news source name (e.g. "Reuters", "Yahoo Finance")

Return 3-8 events, ordered by relevance. If you cannot find reliable search results, return an empty list.

Respond with ONLY valid JSON, no markdown fences: {{"events": [...]}}"""


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


def _validate_events(events: list, obs_from: str, obs_to: str) -> list[dict]:
    range_start = date.fromisoformat(obs_from)
    range_end = date.fromisoformat(obs_to)

    valid = []
    for e in events:
        if not all(k in e for k in ("date", "headline", "category", "impact")):
            continue
        try:
            evt_date = date.fromisoformat(str(e["date"]))
        except ValueError:
            continue
        if evt_date < range_start or evt_date > range_end:
            logger.warning("Dropping event outside range: %s not in %s..%s", e["date"], obs_from, obs_to)
            continue
        valid.append({
            "date": evt_date.isoformat(),
            "headline": str(e["headline"])[:100],
            "category": str(e["category"]),
            "impact": str(e["impact"])[:200],
            "source": str(e.get("source", ""))[:50],
        })
    return valid


def fetch_market_context(
    ticker: str,
    obs_from: str,
    obs_to: str,
) -> list[dict]:
    """Call Anthropic to get market events for the observation period.

    Returns a list of event dicts with keys: date, headline, category, impact.
    Returns empty list on any failure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set, skipping market context")
        return []

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
        prompt = PROMPT_TEMPLATE.format(
            ticker=ticker,
            obs_from=obs_from,
            obs_to=obs_to,
        )

        response = client.messages.create(
            model=model,
            max_tokens=2048,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 6,
            }],
            messages=[{"role": "user", "content": prompt}],
        )

        text = "".join(block.text for block in response.content if hasattr(block, "text"))
        parsed = json.loads(_strip_json_fences(text))
        return _validate_events(parsed.get("events", []), obs_from, obs_to)

    except Exception as e:
        logger.error("Market context fetch failed: %s", e)
        return []


def fetch_market_context_google(
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
        from google.genai import types

        client = genai.Client(api_key=api_key)
        prompt = PROMPT_TEMPLATE.format(
            ticker=ticker,
            obs_from=obs_from,
            obs_to=obs_to,
        )

        # Use Google Search grounding so Gemini pulls from real search results
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        config = types.GenerateContentConfig(tools=[grounding_tool])

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=config,
        )

        parsed = json.loads(_strip_json_fences(response.text))
        events = parsed.get("events", [])
        return _validate_events(events, obs_from, obs_to)

    except Exception as e:
        logger.error("Google market context fetch failed: %s", e)
        return []
