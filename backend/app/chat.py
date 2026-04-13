"""Chat endpoint with configurable LLM provider (Google Gemini or Anthropic Claude).

Both providers share the same tool definitions and handlers. The provider
is selected via the `provider` parameter (default: "google").
"""

from __future__ import annotations
import json
import logging
import os
from datetime import date
from typing import Any, Literal

import numpy as np

from app.prediction_pipeline.predict import predict_price, predict_price_averaged, PipelineResult
from app.prediction_pipeline.step3_smooth_iv import BSplineParams
from app.data.db import (
    get_db, query_chain, query_chains_range, has_data,
    find_best_expiry, find_best_expiry_in_range, get_stats,
)
from app.data.fetcher import find_nearest_expiry_friday

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a quantitative finance analyst assistant for the Decay And Conquer options analysis platform.

You have access to a DuckDB database with three tables:

1. **options** — 90M+ rows of historical US options OHLC data (2025-2026)
   Columns: underlying, expiry, contract_type (C/P), strike, ticker, trade_date, open, high, low, close, volume, transactions

   CRITICAL OPTIONS DATA RULES:
   - The "close" column is the **option contract's per-share price**, NOT the stock price
   - Each contract controls 100 shares, so contract cost = close × 100
   - Example: close=$5.00 means one contract costs $500
   - The "underlying" column is the stock ticker (e.g., MSTR). Use WHERE underlying='MSTR', NOT WHERE ticker='MSTR'
   - The "ticker" column is the OCC symbol (e.g., 'O:MSTR250815C00250000')

   HOW TO CALCULATE OPTIONS P&L:
   1. Find the option's close price on the ENTRY date: entry_price = close on trade_date near purchase date
   2. Find the SAME option's close price on the EXIT/expiry date: exit_price = close on trade_date near expiry
   3. Both prices must be from the SAME option contract (same underlying, strike, expiry, contract_type)
   4. Number of contracts = investment / (entry_price × 100)
   5. Exit value = num_contracts × exit_price × 100
   6. P&L = exit_value - investment

   NEVER mix stock prices with option prices. Both entry and exit must come from the options table.

2. **theta_scans** — pre-computed screener runs for theta plays
   Columns: scan_id, days_forward, hv_days, expiry, tickers_scanned, tickers_failed, scan_time_seconds, created_at

3. **theta_results** — per-ticker screener results (IV vs HV premium)
   Columns: scan_id, ticker, spot, expiry, call_strike, call_bid, call_ask, call_mid, call_iv, put_strike, put_bid, put_ask, put_mid, put_iv, hv_20, call_premium, put_premium, avg_premium, call_efficiency, put_efficiency, beta, pct_change_5d

You can:
1. Run the prediction pipeline to extract risk-neutral price distributions
2. Query all three tables with SQL
3. Compare multiple tickers side by side
4. Retrieve the latest theta plays screener results

When asked about theta plays or options to sell, use the get_theta_plays tool or query theta_results directly.
When asked about a stock's outlook or prediction, use run_prediction with recent observation dates.
- For obs_date_from, use a date 2-4 months before today to capture enough data
- For obs_date_to, use the most recent trading date (today or yesterday)
- The database has data up to approximately today's date
When asked data questions, use query_database with SQL.

Today's date is {today}. The database covers 2025-01-02 through approximately today.

Keep responses concise and well-formatted:
- Use markdown bullet points (- or *) for lists, each on its own line. NEVER use the bullet character (•)
- Use **bold** for important numbers
- Use headers (## or ###) to separate sections
- Always put a blank line before a list of bullet points
- Don't use em dashes
- Don't use markdown tables (they render poorly in the narrow chat panel)""".format(today=date.today().isoformat())


# ---------------------------------------------------------------------------
# Tool definitions (provider-agnostic format, converted per provider)
# ---------------------------------------------------------------------------

TOOL_DEFS = [
    {
        "name": "run_prediction",
        "description": (
            "Run the options-implied price prediction pipeline for a stock. "
            "Extracts the risk-neutral probability distribution from historical options data. "
            "Returns predicted stats and, if the target date is past, the actual realized price."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock symbol, e.g. SPY, AAPL, NVDA"},
                "obs_date_from": {"type": "string", "description": "Start of observation window (YYYY-MM-DD)"},
                "obs_date_to": {"type": "string", "description": "End of observation window (YYYY-MM-DD). Same as obs_date_from for single-day."},
                "target_date": {"type": "string", "description": "Date to predict the price for (YYYY-MM-DD)"},
                "risk_free_rate": {"type": "number", "description": "Annualised risk-free rate, default 0.04"},
            },
            "required": ["ticker", "obs_date_from", "obs_date_to", "target_date"],
        },
    },
    {
        "name": "query_database",
        "description": (
            "Run a read-only SQL query against the DuckDB database. "
            "Tables: 'options' (underlying, expiry, contract_type, strike, ticker, trade_date, open, high, low, close, volume, transactions), "
            "'theta_scans' (scan_id, days_forward, hv_days, expiry, tickers_scanned, created_at), "
            "'theta_results' (scan_id, ticker, spot, call_iv, put_iv, hv_20, call_premium, put_premium, avg_premium, beta, pct_change_5d)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SQL query (SELECT only)"},
            },
            "required": ["sql"],
        },
    },
    {
        "name": "get_database_stats",
        "description": "Get summary statistics about the options database: row count, date range, available tickers.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_theta_plays",
        "description": (
            "Get the latest theta plays screener results: options with IV exceeding HV (overpriced premium, good to sell). "
            "Returns top tickers ranked by premium ratio for a given DTE."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "days_forward": {"type": "integer", "description": "Target DTE: 14, 30, 45, or 60 (default 30)"},
                "limit": {"type": "integer", "description": "Max results to return (default 10)"},
            },
        },
    },
    {
        "name": "compare_tickers",
        "description": "Compare predicted price distributions of multiple stocks on the same date.",
        "parameters": {
            "type": "object",
            "properties": {
                "tickers": {"type": "array", "items": {"type": "string"}, "description": "Stock symbols to compare"},
                "obs_date": {"type": "string", "description": "Observation date (YYYY-MM-DD)"},
                "target_date": {"type": "string", "description": "Target date (YYYY-MM-DD)"},
            },
            "required": ["tickers", "obs_date", "target_date"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handlers (shared by all providers)
# ---------------------------------------------------------------------------

def _run_prediction_tool(params: dict) -> dict:
    ticker = params["ticker"].upper()
    obs_from = params["obs_date_from"]
    obs_to = params["obs_date_to"]
    target = params["target_date"]
    rfr = params.get("risk_free_rate", 0.04)

    obs_from_d = date.fromisoformat(obs_from)
    obs_to_d = date.fromisoformat(obs_to)
    target_d = date.fromisoformat(target)
    days_forward = (target_d - obs_to_d).days

    if days_forward <= 0:
        return {"error": "target_date must be after obs_date_to"}

    expiry = find_nearest_expiry_friday(obs_to_d, days_forward)
    is_range = obs_from_d != obs_to_d

    try:
        # Get spot price from daily closes (more reliable than options intrinsic)
        from app.data.db import query_daily_closes
        daily = query_daily_closes(ticker, 5)
        spot_from_daily = daily[-1][1] if daily else None

        if is_range:
            db_expiry = find_best_expiry_in_range(ticker, obs_from_d, obs_to_d, expiry)
            if not db_expiry:
                return {"error": f"No options data in DB for {ticker} from {obs_from} to {obs_to}"}
            all_rows = query_chains_range(ticker, obs_from_d, obs_to_d, db_expiry)
            chains = {}
            for td, grp in all_rows.groupby("trade_date"):
                chains[str(td)[:10]] = grp[["strike", "last_price", "bid", "ask"]].reset_index(drop=True)
            latest = max(chains.keys())
            spot = spot_from_daily or float(chains[latest].iloc[0]["strike"] + chains[latest].iloc[0]["last_price"])
            result = predict_price_averaged(chains, spot, days_forward, db_expiry, rfr)
        else:
            db_expiry = find_best_expiry(ticker, obs_from_d, expiry)
            if not db_expiry:
                return {"error": f"No options data in DB for {ticker} on {obs_from}"}
            chain = query_chain(ticker, obs_from_d, db_expiry)
            spot = spot_from_daily or float(chain.iloc[0]["strike"] + chain.iloc[0]["last_price"])
            result = predict_price(chain, spot, days_forward, rfr)

        df = result.df
        prices, pdf, cdf = df["Price"].values, df["PDF"].values, df["CDF"].values
        mean_p = float(np.trapezoid(prices * pdf, prices))
        median_p = float(np.interp(0.5, cdf, prices))
        std_p = float(np.sqrt(np.trapezoid((prices - mean_p)**2 * pdf, prices)))

        output = {
            "ticker": ticker, "obs_date_from": obs_from, "obs_date_to": obs_to,
            "target_date": target, "spot": round(spot, 2), "expiry_used": str(db_expiry),
            "days_forward": days_forward,
            "days_averaged": len(chains) if is_range else 1,
            "mean": round(mean_p, 2), "median": round(median_p, 2), "std_dev": round(std_p, 2),
            "p5": round(float(np.interp(0.05, cdf, prices)), 2),
            "p25": round(float(np.interp(0.25, cdf, prices)), 2),
            "p75": round(float(np.interp(0.75, cdf, prices)), 2),
            "p95": round(float(np.interp(0.95, cdf, prices)), 2),
            "n_strikes": result.n_strikes_used, "has_chart_data": True,
        }

        if target_d <= date.today():
            try:
                from app.data.fetcher import fetch_spot_price, get_client
                realized = fetch_spot_price(ticker, target_d, get_client(), rate_limit_sleep=0.5)
                output["realized_price"] = round(realized, 2)
                output["cdf_percentile"] = round(float(np.interp(realized, prices, cdf)), 4)
                output["prediction_error"] = round(realized - median_p, 2)
            except Exception:
                pass

        return output
    except Exception as e:
        return {"error": str(e)}


def _query_database_tool(params: dict) -> dict:
    sql = params["sql"].strip()
    if not sql.upper().startswith("SELECT"):
        return {"error": "Only SELECT queries are allowed"}
    try:
        result = get_db().execute(sql).fetchdf()
        truncated = len(result) > 100
        if truncated:
            result = result.head(100)
        # Convert date/timestamp columns to strings for JSON serialization
        for col in result.columns:
            if result[col].dtype.kind in ("M", "m"):  # datetime or timedelta
                result[col] = result[col].astype(str)
        # Replace NaN/inf with None for JSON compliance
        import math
        rows = result.values.tolist()
        for row in rows:
            for j, v in enumerate(row):
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    row[j] = None
        return {
            "columns": list(result.columns),
            "rows": rows,
            "row_count": len(result),
            "truncated": truncated,
        }
    except Exception as e:
        return {"error": str(e)}


def _get_database_stats_tool(params: dict) -> dict:
    return get_stats()


def _compare_tickers_tool(params: dict) -> dict:
    results = []
    for ticker in params["tickers"]:
        results.append(_run_prediction_tool({
            "ticker": ticker,
            "obs_date_from": params["obs_date"],
            "obs_date_to": params["obs_date"],
            "target_date": params["target_date"],
        }))
    return {"comparisons": results}


def _get_theta_plays_tool(params: dict) -> dict:
    from app.data.db import get_latest_theta_scan, get_theta_results
    days_forward = params.get("days_forward", 30)
    limit = params.get("limit", 10)
    scan = get_latest_theta_scan(days_forward)
    if not scan:
        return {"error": f"No theta scan results for {days_forward}-day DTE. Run run_theta_scan.py first."}
    rows = get_theta_results(scan["scan_id"])
    sorted_rows = sorted(rows, key=lambda r: r.get("avg_premium", 0), reverse=True)[:limit]
    return {
        "scan_id": scan["scan_id"],
        "expiry": scan["expiry"],
        "scanned_at": scan.get("created_at", ""),
        "tickers_scanned": scan.get("tickers_scanned", 0),
        "results": sorted_rows,
    }


TOOL_HANDLERS = {
    "run_prediction": _run_prediction_tool,
    "query_database": _query_database_tool,
    "get_database_stats": _get_database_stats_tool,
    "get_theta_plays": _get_theta_plays_tool,
    "compare_tickers": _compare_tickers_tool,
}


def _execute_tool(name: str, params: dict) -> dict:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return {"error": f"Unknown tool: {name}"}
    logger.info("Tool call: %s(%s)", name, json.dumps(params)[:200])
    return handler(params)


# ---------------------------------------------------------------------------
# Google Gemini provider
# ---------------------------------------------------------------------------

def _run_chat_google(messages: list[dict]) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))

    # Convert tool defs to Gemini format
    gemini_tools = []
    for t in TOOL_DEFS:
        gemini_tools.append(types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=t["parameters"],
            )
        ]))

    # Build contents from message history
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))

    tool_results_for_frontend = []

    max_iterations = 15
    for _ in range(max_iterations):
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=gemini_tools,
            ),
        )

        # Check for function calls
        function_calls = []
        text_parts = []
        for part in response.candidates[0].content.parts:
            if part.function_call:
                function_calls.append(part)
            elif part.text:
                text_parts.append(part.text)

        if function_calls:
            # Add model response to contents
            contents.append(response.candidates[0].content)

            # Execute tools and add results
            function_responses = []
            for fc_part in function_calls:
                fc = fc_part.function_call
                result = _execute_tool(fc.name, dict(fc.args))
                tool_results_for_frontend.append({
                    "tool": fc.name,
                    "input": dict(fc.args),
                    "output": result,
                })
                function_responses.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response=result,
                    )
                )

            contents.append(types.Content(role="user", parts=function_responses))
        else:
            # Final text response
            text = "\n".join(text_parts) if text_parts else ""
            return {"response": text, "tool_results": tool_results_for_frontend}

    return {"response": "Max tool iterations reached.", "tool_results": tool_results_for_frontend}


# ---------------------------------------------------------------------------
# Anthropic Claude provider
# ---------------------------------------------------------------------------

def _run_chat_anthropic(messages: list[dict]) -> dict:
    import anthropic

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return {"response": "No ANTHROPIC_API_KEY set.", "tool_results": []}

    client = anthropic.Anthropic(api_key=key)

    # Convert tool defs to Anthropic format
    anthropic_tools = []
    for t in TOOL_DEFS:
        anthropic_tools.append({
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["parameters"],
        })

    claude_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
    tool_results_for_frontend = []

    def _call_anthropic(**kwargs):
        """Call Anthropic API with retry on 529 (overloaded)."""
        import time as _time
        for attempt in range(5):
            try:
                return client.messages.create(**kwargs)
            except anthropic.APIStatusError as e:
                if e.status_code == 529 and attempt < 4:
                    logger.warning("Anthropic 529 overloaded, retrying in %ds (attempt %d/5)", 3 * (attempt + 1), attempt + 1)
                    _time.sleep(3 * (attempt + 1))
                    continue
                raise

    max_iterations = 15
    for _ in range(max_iterations):
        response = _call_anthropic(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=anthropic_tools,
            messages=claude_messages,
        )

        if response.stop_reason == "tool_use":
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            claude_messages.append({"role": "assistant", "content": response.content})

            tool_result_contents = []
            for tb in tool_use_blocks:
                result = _execute_tool(tb.name, tb.input)
                tool_results_for_frontend.append({
                    "tool": tb.name, "input": tb.input, "output": result,
                })
                tool_result_contents.append({
                    "type": "tool_result",
                    "tool_use_id": tb.id,
                    "content": json.dumps(result),
                })

            claude_messages.append({"role": "user", "content": tool_result_contents})
        else:
            text = "".join(b.text for b in response.content if hasattr(b, "text"))
            return {"response": text, "tool_results": tool_results_for_frontend}

    return {"response": "Max tool iterations reached.", "tool_results": tool_results_for_frontend}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

PROVIDERS = {
    "google": _run_chat_google,
    "anthropic": _run_chat_anthropic,
}

DEFAULT_PROVIDER = "google"


def run_chat(
    messages: list[dict],
    provider: str | None = None,
) -> dict:
    """Run a chat turn with the specified LLM provider.

    Args:
        messages: conversation history [{role, content}, ...]
        provider: "google" or "anthropic" (default: "google")

    Returns:
        {"response": "...", "tool_results": [...]}
    """
    provider = provider or DEFAULT_PROVIDER
    handler = PROVIDERS.get(provider)
    if not handler:
        return {"response": f"Unknown provider: {provider}. Use 'google' or 'anthropic'.", "tool_results": []}

    try:
        return handler(messages)
    except Exception as e:
        logger.error("Chat failed (%s): %s", provider, e)
        return {"response": f"Error ({provider}): {e}", "tool_results": []}
