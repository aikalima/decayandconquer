"""Dacey: Google ADK agent with Gemini Flash and read-only dashboard tools."""

from __future__ import annotations
import json
import asyncio
import logging
import math
import os
from datetime import date, timedelta
from uuid import uuid4

import numpy as np

from app.prediction_pipeline.predict import predict_price, predict_price_averaged
from app.data.db import get_db, get_stats, isolated_read_db
from google.adk.agents import LlmAgent
from google.adk.agents.run_config import RunConfig
from google.adk.events import Event
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import BaseTool
from google.genai import types, errors
from jsonschema import validate, ValidationError

logger = logging.getLogger(__name__)

DEFAULT_CHAT_MODEL = "gemini-3.8-flash"

def _prompt_defaults() -> dict[str, str]:
    try:
        from app.defaults import build_app_defaults

        defaults = build_app_defaults()
        return {
            "today": defaults["today"],
            "earliest_data_date": defaults["earliest_data_date"],
            "latest_data_date": defaults["latest_data_date"],
        }
    except Exception:
        today = date.today()
        return {
            "today": today.isoformat(),
            "earliest_data_date": "2025-01-02",
            "latest_data_date": today.isoformat(),
        }


SYSTEM_PROMPT = """You are a quantitative finance analyst assistant for the Decay And Conquer options analysis platform.

You have access to a DuckDB database with three tables:

1. **options** — historical US options OHLC data (coverage dates below)
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
   Columns: scan_id, ticker, spot, expiry, call_strike, call_bid, call_ask, call_mid, call_iv, put_strike, put_bid, put_ask, put_mid, put_iv, hv_20, call_premium, put_premium, avg_premium, call_efficiency, put_efficiency, beta, pct_change_5d, quality_score, rank_score, quality_warnings, price_source/open_interest fields

You can:
1. Run the prediction pipeline to extract risk-neutral price distributions
2. Query all three tables with SQL
3. Compare multiple tickers side by side
4. Retrieve the latest theta plays screener results

When asked about theta plays or options to sell, use get_theta_plays. It applies the same data-quality filters as the dashboard.
IV/HV richness is a volatility ratio, not a dollar premium or a trade recommendation.
Never replace a zero quality/rank score with raw IV/HV. Explain timestamps and warnings.
Risk-neutral probabilities describe finishing prices, not touching a price before expiry or guaranteed real-world odds.
When asked about a stock's outlook or prediction, use run_prediction with recent observation dates.
- For obs_date_from, use a date 2-4 months before today to capture enough data
- For obs_date_to, use the latest available trading date ({latest_data_date})
- The database has data through {latest_data_date}
When asked data questions, use query_database with SQL.

Today's date is {today}. The database covers {earliest_data_date} through {latest_data_date}.

Keep responses concise and well-formatted:
- Use markdown bullet points (- or *) for lists, each on its own line. NEVER use the bullet character (•)
- Use **bold** for important numbers
- Use headers (## or ###) to separate sections
- Always put a blank line before a list of bullet points
- Don't use em dashes
- Don't use markdown tables (they render poorly in the narrow chat panel)"""


# ---------------------------------------------------------------------------
# Tool definitions exposed through ADK
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
            "'theta_results' (scan_id, ticker, spot, call_iv, put_iv, hv_20, call_premium, put_premium, avg_premium, quality_score, rank_score, quality_warnings, beta, pct_change_5d)."
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
            "Get saved theta research candidates with the dashboard's quality checks. "
            "Ranks by quality-adjusted IV/HV richness, not dollar premium or executable trade prices."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expiry": {"type": "string", "description": "Optional monthly expiry date to retrieve (YYYY-MM-DD)"},
                "days_forward": {"type": "integer", "description": "Optional target DTE. If no exact scan exists, the nearest scanned expiry is used."},
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
# Tool handlers
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

    is_range = obs_from_d != obs_to_d

    try:
        from app.prediction_inputs import prepare_prediction
        from app.data.underlying import realized_close
        inputs = prepare_prediction(ticker, obs_from_d, obs_to_d, target_d)
        chains, spot, db_expiry = inputs.chains, inputs.spot, inputs.expiry
        days_forward = inputs.days_forward
        if len(chains) > 1:
            result = predict_price_averaged(chains, spot, days_forward, db_expiry, rfr, spots_by_date=inputs.spots)
        else:
            result = predict_price(next(iter(chains.values())), spot, days_forward, rfr,
                                   option_days_to_expiry=(db_expiry - inputs.observation).days)

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
        output.update(inputs.meta)
        output["fit_diagnostics"] = result.diagnostics
        if result.diagnostics.get("clipped_negative_fraction", 0) > 0.01:
            output["warnings"].append("Material negative density was clipped; the distribution may be unreliable.")

        if target_d <= date.today():
            try:
                observation = realized_close(ticker, target_d)
                if not observation:
                    output["warnings"].append("No actual stock close on the target date; this run is not scored.")
                    return output
                realized = observation["price"]
                output["realized_price"] = round(realized, 2)
                output["realized_date"] = observation["date"]
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
        conn = get_db()
        statements = conn.extract_statements(sql)
        if len(statements) != 1 or statements[0].type.name != "SELECT":
            return {"error": "Only a single SELECT query is allowed"}
        cursor = conn.execute(sql)
        rows = cursor.fetchmany(101)
        truncated = len(rows) > 100
        return {
            "columns": [column[0] for column in cursor.description],
            "rows": _json_safe(rows[:100]),
            "row_count": min(len(rows), 100),
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


def _nearest_theta_scan_for_days(days_forward: int) -> dict | None:
    from app.data.db import get_available_theta_expiries, get_latest_theta_scan_by_expiry

    target = date.today() + timedelta(days=days_forward)
    candidates = []
    for item in get_available_theta_expiries():
        try:
            expiry = date.fromisoformat(str(item["expiry"]))
        except ValueError:
            continue
        candidates.append((abs((expiry - target).days), item["expiry"]))

    if not candidates:
        return None

    _, expiry = min(candidates, key=lambda item: item[0])
    return get_latest_theta_scan_by_expiry(expiry)


def _first_configured_theta_scan() -> dict | None:
    from app.data.db import get_latest_theta_scan_by_expiry

    try:
        from app.defaults import build_app_defaults

        defaults = build_app_defaults()
        expiries = defaults.get("theta", {}).get("expiries", [])
    except Exception:
        expiries = []

    for item in expiries:
        expiry = item.get("expiry")
        if not expiry:
            continue
        scan = get_latest_theta_scan_by_expiry(expiry)
        if scan:
            return scan
    return None


def _get_theta_plays_tool(params: dict) -> dict:
    from app.data.db import get_latest_theta_scan, get_latest_theta_scan_by_expiry, get_theta_results

    expiry = params.get("expiry")
    days_forward = params.get("days_forward")
    limit = max(1, min(int(params.get("limit", 10)), 100))

    if expiry:
        try:
            expiry = date.fromisoformat(str(expiry)).isoformat()
        except ValueError:
            return {"error": "expiry must be a valid YYYY-MM-DD date"}
        scan = get_latest_theta_scan_by_expiry(expiry)
    elif days_forward is not None:
        days_forward = int(days_forward)
        scan = get_latest_theta_scan(days_forward) or _nearest_theta_scan_for_days(days_forward)
    else:
        scan = _first_configured_theta_scan() or get_latest_theta_scan(None)

    if not scan:
        return {"error": "No theta scan results found. Run run_theta_scan.py --config config/app_defaults.json first."}

    rows = get_theta_results(scan["scan_id"])
    from app.theta_quality import scan_response, timestamp
    assessed = scan_response(rows, scan)
    scanned = timestamp(scan.get("created_at"))
    return {
        "scan_id": scan["scan_id"],
        "expiry": scan["expiry"],
        "days_forward": scan.get("days_forward"),
        "hv_days": scan.get("hv_days"),
        "scanned_at": scanned.isoformat() if scanned else None,
        "tickers_scanned": scan.get("tickers_scanned", 0),
        "quality_counts": assessed["quality_counts"]["highest_premium"],
        "results": assessed["highest_premium"][:limit],
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
# Google ADK runtime
# ---------------------------------------------------------------------------

def _json_safe(value):
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


class DashboardTool(BaseTool):
    """Expose the existing schemas and handlers to ADK's function-call loop."""

    def __init__(self, definition: dict, results: list, budget: dict):
        super().__init__(name=definition["name"], description=definition["description"])
        self.definition = definition
        self.results = results
        self.budget = budget

    def _get_declaration(self):
        return types.FunctionDeclaration(**self.definition)

    async def run_async(self, *, args, tool_context):
        if self.budget["calls"] >= 20:
            return {"error": "Tool budget reached. Summarize the results already obtained."}
        self.budget["calls"] += 1
        try:
            validate(args, self.definition["parameters"])

            def invoke():
                with isolated_read_db():
                    return _json_safe(_execute_tool(self.name, args))

            result = await asyncio.to_thread(invoke)
        except ValidationError:
            result = {"error": "Invalid tool arguments. Check the required fields and types."}
        except Exception as exc:
            logger.warning("Chat tool %s failed (%s)", self.name, type(exc).__name__)
            result = {"error": "The requested calculation or database read failed."}
        self.results.append({"tool": self.name, "input": args, "output": result})
        return result


def _system_instruction() -> str:
    with isolated_read_db():
        return SYSTEM_PROMPT.format(**_prompt_defaults())


def _validate_messages(messages):
    if not isinstance(messages, list) or not messages or len(messages) > 60:
        raise ValueError("Provide 1-60 chat messages. Start a new conversation if the history is full.")
    for message in messages:
        if (not isinstance(message, dict) or message.get("role") not in ("user", "assistant")
                or not isinstance(message.get("content"), str) or not message["content"].strip()):
            raise ValueError("Each message must have a user/assistant role and nonempty text.")
    if messages[-1]["role"] != "user":
        raise ValueError("The last message must be from the user.")
    if sum(len(message["content"]) for message in messages) > 60000:
        raise ValueError("Conversation is too long. Start a new conversation.")


async def _run_adk(messages: list[dict], results: list, model) -> str:
    from app.ai_usage import record_usage
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name="decay_chat", user_id="request", session_id=uuid4().hex)
    # The browser supplies its history. A fresh, request-scoped ADK session
    # avoids server affinity and cross-user state on multi-worker deployments.
    for index, message in enumerate(messages[:-1]):
        is_user = message["role"] == "user"
        await session_service.append_event(session=session, event=Event(
            invocation_id=f"history_{index}", author="user" if is_user else "dacey",
            content=types.Content(role="user" if is_user else "model",
                                  parts=[types.Part.from_text(text=message["content"])]),
        ))
    budget = {"calls": 0}
    agent = LlmAgent(
        name="dacey", model=model,
        instruction=await asyncio.to_thread(_system_instruction),
        tools=[DashboardTool(definition, results, budget) for definition in TOOL_DEFS],
        generate_content_config=types.GenerateContentConfig(max_output_tokens=4096),
    )
    async with Runner(agent=agent, app_name="decay_chat", session_service=session_service) as runner:
        async for event in runner.run_async(
            user_id="request", session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=messages[-1]["content"])]),
            run_config=RunConfig(max_llm_calls=15),
        ):
            if not event.partial and event.usage_metadata is not None:
                record_usage(event)
            if event.is_final_response() and event.content:
                text = "\n".join(part.text for part in event.content.parts or []
                                 if part.text and not part.thought)
                if text:
                    return text
    return "I couldn't complete that request. Try a narrower question."


async def run_chat(messages: list[dict]) -> dict:
    """Run one Gemini ADK turn, preserving the browser's response/tool-results API."""
    from app.ai_usage import mark_failed
    _validate_messages(messages)
    results = []
    key = os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        mark_failed()
        return {"response": "Dacey needs GOOGLE_API_KEY to be configured.", "tool_results": []}
    from google import genai

    client = genai.Client(api_key=key, vertexai=False, http_options=types.HttpOptions(timeout=45000))
    try:
        model = Gemini(model=os.environ.get("CHAT_MODEL", DEFAULT_CHAT_MODEL), client=client)
        async with asyncio.timeout(180):
            text = await _run_adk(messages, results, model)
    except TimeoutError:
        mark_failed()
        text = "Dacey took too long. Please try a narrower question."
    except Exception as exc:
        mark_failed()
        code = getattr(exc, "code", None)
        logger.error("ADK chat failed (%s, code=%s)", type(exc).__name__, code)
        if isinstance(exc, errors.APIError) and (code in (401, 403) or "API key not valid" in str(exc.message)):
            text = "Google rejected Dacey's API key. Update GOOGLE_API_KEY and check its API restrictions."
        elif code == 402:
            text = "Gemini requires payment. Check your project's billing and prepaid credits in Google AI Studio."
        elif code == 429:
            text = "Gemini quota or rate limit reached. Check Google API billing or try again later."
        elif code == 404:
            text = "The configured Gemini model is unavailable. Check CHAT_MODEL."
        else:
            text = "Dacey couldn't complete that request. Please try again."
    finally:
        await client.aio.aclose()
        client.close()
    return {"response": text, "tool_results": results}
