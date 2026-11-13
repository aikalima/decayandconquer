import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.modules.health import get_ping_response
from app.prediction_pipeline.predict import (
    predict_price_with_progress, predict_price_averaged_with_progress,
    PipelineResult,
)
from app.prediction_pipeline.step3_smooth_iv import BSplineParams
from app.data.db import set_read_only

# Server only reads from DuckDB — never hold a write lock
set_read_only(True)
from app.news import fetch_market_context
from app.screener import scan_all, DEFAULT_TICKERS
from app.defaults import build_app_defaults
from app.data.db import get_latest_theta_scan, get_latest_theta_scan_by_expiry, get_theta_results, get_available_theta_expiries

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _build_response(result: PipelineResult, meta: dict) -> dict:
    """Serialize PipelineResult + meta into the API response."""
    return {
        "data": result.df.to_dict(),
        "meta": meta,
        "iv_smile": {
            "raw_strikes": result.iv_raw_strikes,
            "raw_iv": result.iv_raw_values,
            "smooth_strikes": result.iv_smooth_strikes,
            "smooth_iv": result.iv_smooth_values,
            "n_strikes": result.n_strikes_used,
        },
        "greeks": result.greeks,
    }


def _prediction_steps(
    ticker, obs_date, obs_date_from, obs_date_to, target_date, days_forward,
    risk_free_rate, solver, bspline_k, bspline_smooth, bspline_dx, kernel_smooth,
):
    from app.prediction_inputs import prepare_prediction
    from app.data.underlying import realized_close

    if bool(obs_date_from) != bool(obs_date_to):
        raise ValueError("Both observation range dates are required")
    start = date.fromisoformat(obs_date_from or obs_date or (date.today() - timedelta(days=1)).isoformat())
    end = date.fromisoformat(obs_date_to) if obs_date_to else start
    target = date.fromisoformat(target_date) if target_date else end + timedelta(days=days_forward)
    yield {"stage": "Loading date-matched options and stock prices", "progress": 10}
    inputs = prepare_prediction(ticker, start, end, target)
    common = dict(spot=inputs.spot, days_forward=inputs.days_forward,
                  risk_free_rate=risk_free_rate, solver=solver,
                  bspline=BSplineParams(k=bspline_k, smooth=bspline_smooth, dx=bspline_dx),
                  kernel_smooth=kernel_smooth)
    if len(inputs.chains) > 1:
        steps = predict_price_averaged_with_progress(
            chains_by_date=inputs.chains, expiry=inputs.expiry,
            spots_by_date=inputs.spots, **common)
    else:
        steps = predict_price_with_progress(
            quotes=next(iter(inputs.chains.values())),
            option_days_to_expiry=(inputs.expiry - inputs.observation).days, **common)
    result = None
    for step in steps:
        if isinstance(step, PipelineResult):
            result = step
        else:
            yield {"stage": step[0], "progress": step[1]}
    meta = inputs.meta
    meta["fit_diagnostics"] = result.diagnostics
    if result.diagnostics.get("clipped_negative_fraction", 0) > 0.01:
        meta["warnings"].append("The fitted density required material negative-mass clipping. Treat this distribution with caution.")
    realized = realized_close(ticker.upper(), target)
    if realized:
        meta["realized_price"] = realized["price"]
        meta["realized_date"] = realized["date"]
        meta["realized_source"] = realized["basis"]
    elif meta["mode"] == "backtest":
        meta["warnings"].append("No actual stock close is available on the target date; this run is not scored.")
    yield {"done": True, "progress": 100, "result": _build_response(result, meta)}


@app.get("/ping")
async def ping():
    logger.info("ping received")
    return get_ping_response()


@app.get("/app-defaults")
async def app_defaults():
    """Return date-aware frontend and batch defaults."""
    return build_app_defaults()


@app.get("/data-health")
async def data_health():
    from app.data_health import get_data_health
    return get_data_health()


@app.post("/chat")
async def chat_endpoint(body: dict):
    """Conversational AI endpoint. Supports 'google' (default) and 'anthropic' providers."""
    from app.chat import run_chat
    messages = body.get("messages", [])
    provider = body.get("provider", "google")
    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")
    try:
        result = run_chat(messages, provider=provider)
        # Sanitize NaN/inf values that break JSON serialization
        import math
        def _sanitize(obj):
            if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
                return None
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitize(v) for v in obj]
            return obj
        return _sanitize(result)
    except Exception as e:
        logger.error("chat failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/predict")
async def predict_price_route(
    ticker: str = "SPY",
    obs_date: Optional[str] = None,
    obs_date_from: Optional[str] = None,
    obs_date_to: Optional[str] = None,
    target_date: Optional[str] = None,
    days_forward: int = 30,
    risk_free_rate: float = 0.04,
    solver: str = "brent",
    bspline_k: int = 3,
    bspline_smooth: float = 10.0,
    bspline_dx: float = 0.1,
    kernel_smooth: bool = True,
):
    params = locals()
    try:
        for event in _prediction_steps(**params):
            if event.get("done"):
                return event["result"]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("Prediction failed")
        raise HTTPException(status_code=503, detail="Prediction data is unavailable")


@app.get("/predict-stream")
async def predict_price_stream(
    ticker: str = "SPY",
    obs_date: Optional[str] = None,
    obs_date_from: Optional[str] = None,
    obs_date_to: Optional[str] = None,
    target_date: Optional[str] = None,
    days_forward: int = 30,
    risk_free_rate: float = 0.04,
    solver: str = "brent",
    bspline_k: int = 3,
    bspline_smooth: float = 10.0,
    bspline_dx: float = 0.1,
    kernel_smooth: bool = True,
):
    params = locals()

    async def generate():
        try:
            for event in _prediction_steps(**params):
                yield _sse(event)
        except ValueError as exc:
            yield _sse({"error": str(exc)})
        except Exception:
            logger.exception("Prediction stream failed")
            yield _sse({"error": "Prediction data is unavailable"})

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/market-context")
async def market_context(
    ticker: str = "SPY",
    obs_from: Optional[str] = None,
    obs_to: Optional[str] = None,
):
    """Fetch AI-generated market context for the observation period."""
    try:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return {
                "events": [],
                "disclaimer": "Market context is disabled because ANTHROPIC_API_KEY is not configured.",
            }
        defaults = build_app_defaults()["prediction"]
        obs_from = obs_from or defaults["obs_date_from"]
        obs_to = obs_to or defaults["obs_date_to"]
        events = fetch_market_context(ticker, obs_from, obs_to)
        return {
            "events": events,
            "disclaimer": "Sourced via Anthropic web search. AI-summarized, verify independently.",
        }
    except Exception as e:
        logger.error("market-context failed: %s", e)
        return {"events": [], "disclaimer": "Failed to fetch market context."}


def _try_theta_json_fallback():
    """Check for JSON fallback file written when DB was locked."""
    import json as _json
    fallback = Path(__file__).parent / "data" / "theta_latest.json"
    if not fallback.exists():
        return None
    try:
        data = _json.loads(fallback.read_text())
        rows = data["results"]
        by_avg = sorted(rows, key=lambda r: r.get("rank_score") or r.get("avg_premium", 0), reverse=True)
        by_call = sorted(rows, key=lambda r: r.get("call_rank_score") or r.get("call_premium", 0), reverse=True)
        by_put = sorted(rows, key=lambda r: r.get("put_rank_score") or r.get("put_premium", 0), reverse=True)
        return {
            "highest_premium": by_avg,
            "expensive_calls": by_call,
            "expensive_puts": by_put,
            "tickers_scanned": data.get("tickers_scanned", len(rows)),
            "tickers_failed": [],
            "expiry": data.get("expiry", ""),
            "scan_time_seconds": data.get("scan_time_seconds", 0),
            "scan_id": data.get("scan_id", ""),
            "scanned_at": data.get("scan_id", ""),
        }
    except Exception:
        return None


@app.get("/theta-expiries")
async def theta_expiries():
    """List available expiry dates from completed theta scans."""
    return {"expiries": get_available_theta_expiries()}


@app.get("/theta-plays")
async def theta_plays(scan_id: Optional[str] = None, days_forward: Optional[int] = None, expiry: Optional[str] = None):
    """Serve pre-computed theta plays results from DuckDB or JSON fallback."""
    if expiry:
        scan = get_latest_theta_scan_by_expiry(expiry)
    elif scan_id:
        scan = None
    else:
        scan = get_latest_theta_scan(days_forward)

    if scan is None and scan_id is None:
        fallback = _try_theta_json_fallback()
        if fallback:
            return fallback
        return {"error": "No scans available. Run run_theta_scan.py first."}

    sid = scan_id or scan["scan_id"]
    if scan is None:
        scan = {"scan_id": sid}

    rows = get_theta_results(sid)
    if not rows:
        return {"error": f"No results for scan {sid}"}

    by_avg = sorted(rows, key=lambda r: r.get("rank_score") or r.get("avg_premium", 0), reverse=True)
    by_call = sorted(rows, key=lambda r: r.get("call_rank_score") or r.get("call_premium", 0), reverse=True)
    by_put = sorted(rows, key=lambda r: r.get("put_rank_score") or r.get("put_premium", 0), reverse=True)

    return {
        "highest_premium": by_avg,
        "expensive_calls": by_call,
        "expensive_puts": by_put,
        "tickers_scanned": scan.get("tickers_scanned", len(rows)),
        "tickers_failed": [],
        "expiry": scan.get("expiry", ""),
        "scan_time_seconds": scan.get("scan_time_seconds", 0),
        "scan_id": sid,
        "scanned_at": scan.get("created_at", ""),
        "hv_days": scan.get("hv_days", 20),
    }


@app.get("/theta-plays-stream")
async def theta_plays_stream(
    tickers: str = "",
    days_forward: int = 30,
    hv_days: int = 20,
):
    """Scan tickers for theta play opportunities with SSE progress."""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()] if tickers else DEFAULT_TICKERS

    async def generate() -> AsyncGenerator[str, None]:
        import time
        start = time.time()
        try:
            for item in scan_all(ticker_list, days_forward, hv_days):
                if isinstance(item, dict):
                    # Final results
                    item["scan_time_seconds"] = round(time.time() - start, 1)
                    yield _sse({"done": True, "progress": 100, "results": item})
                else:
                    stage, progress, row = item
                    yield _sse({
                        "stage": stage,
                        "progress": progress,
                        "row": row.__dict__ if row else None,
                    })
        except Exception as e:
            logger.error("theta-plays-stream failed: %s", e)
            yield _sse({"error": str(e)})

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/heatmap-stream")
async def heatmap_stream(
    ticker: str = "SPY",
    num_expiries: int = 6,
    strike_range: float = 0.15,
):
    """Generate options heat map data with SSE progress."""
    from app.heatmap import generate_heatmap

    async def generate() -> AsyncGenerator[str, None]:
        import time
        start = time.time()
        try:
            for item in generate_heatmap(ticker.upper(), num_expiries, strike_range):
                if isinstance(item, dict):
                    if "error" not in item:
                        item["fetch_time_seconds"] = round(time.time() - start, 1)
                    yield _sse({"done": True, "progress": 100, "result": item})
                else:
                    stage, progress = item
                    yield _sse({"stage": stage, "progress": progress})
        except Exception as e:
            logger.error("heatmap-stream failed: %s", e)
            yield _sse({"error": str(e)})

    return StreamingResponse(generate(), media_type="text/event-stream")
