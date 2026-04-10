import json
import logging
from datetime import date, timedelta
from typing import Optional, AsyncGenerator
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import pandas as pd

from app.modules.health import get_ping_response
from app.prediction_pipeline.predict import (
    predict_price, predict_price_averaged,
    predict_price_with_progress, predict_price_averaged_with_progress,
    PipelineResult,
)
from app.prediction_pipeline.step3_smooth_iv import BSplineParams
from app.data.db import (
    query_chain, query_chains_range, has_data,
    find_best_expiry, find_best_expiry_in_range,
)
from app.data.fetcher import (
    fetch_options_chain,
    fetch_spot_price,
    get_client,
    find_nearest_expiry_friday,
)
from app.news import fetch_market_context

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


def _get_realized_price(ticker: str, target_date: date) -> Optional[float]:
    if target_date > date.today():
        return None
    try:
        client = get_client()
        return fetch_spot_price(ticker, target_date, client, rate_limit_sleep=0.5)
    except Exception:
        return None


def _get_chain_and_spot_single(
    ticker: str, observation: date, expiry: date, source_log: list[str],
) -> tuple[pd.DataFrame, float]:
    """Single-day: DuckDB first, API fallback."""
    if has_data(ticker, observation):
        db_expiry = find_best_expiry(ticker, observation, expiry)
        if db_expiry:
            try:
                chain = query_chain(ticker, observation, db_expiry)
                if len(chain) >= 5:
                    spot = float(chain.iloc[0]["strike"] + chain.iloc[0]["last_price"])
                    source_log.append("duckdb")
                    return chain, spot
            except ValueError:
                pass

    source_log.append("api")
    client = get_client()
    spot = fetch_spot_price(ticker, observation, client, rate_limit_sleep=0.5)
    chain = fetch_options_chain(
        ticker, observation, expiry, spot=spot,
        client=client, rate_limit_sleep=0.5,
    )
    return chain, spot


def _get_chains_range(
    ticker: str, date_from: date, date_to: date, expiry: date,
) -> tuple[dict[str, pd.DataFrame], float, date, str]:
    """Multi-day: query DuckDB for chains across the date range.

    Returns (chains_by_date, spot, db_expiry, source).
    Spot is estimated from the latest date's deepest ITM call.
    """
    db_expiry = find_best_expiry_in_range(ticker, date_from, date_to, expiry)
    if db_expiry is None:
        raise ValueError(
            f"No options data in DB for {ticker} from {date_from} to {date_to} near expiry {expiry}"
        )

    all_rows = query_chains_range(ticker, date_from, date_to, db_expiry)

    chains_by_date: dict[str, pd.DataFrame] = {}
    for trade_date, group in all_rows.groupby("trade_date"):
        # DuckDB may return date as datetime or date object — normalise to YYYY-MM-DD string
        date_str = str(trade_date)[:10]
        chains_by_date[date_str] = group[["strike", "last_price", "bid", "ask"]].reset_index(drop=True)

    # Spot from the latest date's deepest ITM call
    latest_date = max(chains_by_date.keys())
    latest_chain = chains_by_date[latest_date]
    spot = float(latest_chain.iloc[0]["strike"] + latest_chain.iloc[0]["last_price"])

    return chains_by_date, spot, db_expiry, "duckdb"


@app.get("/ping")
async def ping():
    logger.info("ping received")
    return get_ping_response()


@app.post("/chat")
async def chat_endpoint(body: dict):
    """Conversational AI endpoint. Supports 'google' (default) and 'anthropic' providers."""
    from app.chat import run_chat
    messages = body.get("messages", [])
    provider = body.get("provider", "google")
    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")
    try:
        return run_chat(messages, provider=provider)
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
    """Run the prediction pipeline.

    Single-day: provide obs_date (or obs_date_from == obs_date_to).
    Date range: provide obs_date_from + obs_date_to for IV averaging.
    """
    ticker_upper = ticker.upper()
    bspline = BSplineParams(k=bspline_k, smooth=bspline_smooth, dx=bspline_dx)

    try:
        # Determine if single-day or range
        date_from = date.fromisoformat(obs_date_from) if obs_date_from else None
        date_to = date.fromisoformat(obs_date_to) if obs_date_to else None
        single_date = date.fromisoformat(obs_date) if obs_date else None

        is_range = date_from is not None and date_to is not None and date_from != date_to

        if is_range:
            # Date range mode — IV averaging
            if target_date:
                target = date.fromisoformat(target_date)
                days_forward = (target - date_to).days
                if days_forward <= 0:
                    raise ValueError("target_date must be after obs_date_to")

            expiry = find_nearest_expiry_friday(date_to, days_forward)
            chains_by_date, spot, db_expiry, source = _get_chains_range(
                ticker_upper, date_from, date_to, expiry,
            )

            logger.info(
                "predict (range): %s %s to %s, %d days, expiry=%s, spot=%.2f, source=%s",
                ticker_upper, date_from, date_to, len(chains_by_date), db_expiry, spot, source,
            )

            result = predict_price_averaged(
                chains_by_date=chains_by_date, spot=spot, days_forward=days_forward,
                expiry=db_expiry, risk_free_rate=risk_free_rate, solver=solver,
                bspline=bspline, kernel_smooth=kernel_smooth,
            )

            target_actual = date_to + timedelta(days=days_forward)
            meta = {
                "ticker": ticker_upper,
                "obs_date_from": date_from.isoformat(),
                "obs_date_to": date_to.isoformat(),
                "obs_date": date_to.isoformat(),
                "target_date": target_actual.isoformat(),
                "days_forward": days_forward,
                "days_averaged": len(chains_by_date),
                "spot": spot,
                "expiry_used": db_expiry.isoformat(),
                "data_source": source,
            }

        else:
            # Single-day mode
            observation = single_date or date_from or date.today()
            if target_date:
                target = date.fromisoformat(target_date)
                days_forward = (target - observation).days
                if days_forward <= 0:
                    raise ValueError("target_date must be after obs_date")

            expiry = find_nearest_expiry_friday(observation, days_forward)
            source_log: list[str] = []
            quotes_df, spot = _get_chain_and_spot_single(
                ticker_upper, observation, expiry, source_log,
            )

            logger.info(
                "predict (single): %s on %s, expiry=%s, spot=%.2f, source=%s",
                ticker_upper, observation, expiry, spot, source_log[0],
            )

            result = predict_price(
                quotes=quotes_df, spot=spot, days_forward=days_forward,
                risk_free_rate=risk_free_rate, solver=solver,
                bspline=bspline, kernel_smooth=kernel_smooth,
            )

            target_actual = observation + timedelta(days=days_forward)
            meta = {
                "ticker": ticker_upper,
                "obs_date": observation.isoformat(),
                "obs_date_from": observation.isoformat(),
                "obs_date_to": observation.isoformat(),
                "target_date": target_actual.isoformat(),
                "days_forward": days_forward,
                "days_averaged": 1,
                "spot": spot,
                "expiry_used": expiry.isoformat(),
                "data_source": source_log[0] if source_log else "unknown",
            }

        realized = _get_realized_price(ticker_upper, target_actual)
        if realized is not None:
            meta["realized_price"] = realized

        return _build_response(result, meta)

    except ValueError as e:
        logger.error("predict failed (bad input): %s", e)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("predict failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
    """Run the prediction pipeline with SSE progress updates."""

    async def generate() -> AsyncGenerator[str, None]:
        try:
            ticker_upper = ticker.upper()
            bspline = BSplineParams(k=bspline_k, smooth=bspline_smooth, dx=bspline_dx)

            yield _sse({"stage": "Resolving dates", "progress": 0})

            date_from = date.fromisoformat(obs_date_from) if obs_date_from else None
            date_to = date.fromisoformat(obs_date_to) if obs_date_to else None
            single_date = date.fromisoformat(obs_date) if obs_date else None
            is_range = date_from is not None and date_to is not None and date_from != date_to

            if is_range:
                df_days = days_forward
                if target_date:
                    target = date.fromisoformat(target_date)
                    df_days = (target - date_to).days
                    if df_days <= 0:
                        raise ValueError("target_date must be after obs_date_to")

                expiry = find_nearest_expiry_friday(date_to, df_days)

                yield _sse({"stage": f"Loading options data ({date_from} to {date_to})", "progress": 10})

                chains_by_date, spot, db_expiry, source = _get_chains_range(
                    ticker_upper, date_from, date_to, expiry,
                )

                logger.info(
                    "predict-stream (range): %s %s-%s %d days, spot=%.2f, expiry=%s",
                    ticker_upper, date_from, date_to, len(chains_by_date), spot, db_expiry,
                )

                result = None
                for step in predict_price_averaged_with_progress(
                    chains_by_date=chains_by_date, spot=spot, days_forward=df_days,
                    expiry=db_expiry, risk_free_rate=risk_free_rate, solver=solver,
                    bspline=bspline, kernel_smooth=kernel_smooth,
                ):
                    if isinstance(step, PipelineResult):
                        result = step
                    else:
                        yield _sse({"stage": step[0], "progress": step[1]})

                target_actual = date_to + timedelta(days=df_days)
                meta = {
                    "ticker": ticker_upper,
                    "obs_date_from": date_from.isoformat(),
                    "obs_date_to": date_to.isoformat(),
                    "obs_date": date_to.isoformat(),
                    "target_date": target_actual.isoformat(),
                    "days_forward": df_days,
                    "days_averaged": len(chains_by_date),
                    "spot": spot,
                    "expiry_used": db_expiry.isoformat(),
                    "data_source": source,
                }

            else:
                observation = single_date or date_from or date.today()
                df_days = days_forward
                if target_date:
                    target = date.fromisoformat(target_date)
                    df_days = (target - observation).days
                    if df_days <= 0:
                        raise ValueError("target_date must be after obs_date")

                expiry = find_nearest_expiry_friday(observation, df_days)

                yield _sse({"stage": "Loading options data", "progress": 10})

                source_log: list[str] = []
                quotes_df, spot = _get_chain_and_spot_single(
                    ticker_upper, observation, expiry, source_log,
                )

                logger.info(
                    "predict-stream (single): %s on %s, spot=%.2f, expiry=%s, source=%s",
                    ticker_upper, observation, spot, expiry, source_log[0],
                )

                result = None
                for step in predict_price_with_progress(
                    quotes=quotes_df, spot=spot, days_forward=df_days,
                    risk_free_rate=risk_free_rate, solver=solver,
                    bspline=bspline, kernel_smooth=kernel_smooth,
                ):
                    if isinstance(step, PipelineResult):
                        result = step
                    else:
                        yield _sse({"stage": step[0], "progress": step[1]})

                target_actual = observation + timedelta(days=df_days)
                meta = {
                    "ticker": ticker_upper,
                    "obs_date": observation.isoformat(),
                    "obs_date_from": observation.isoformat(),
                    "obs_date_to": observation.isoformat(),
                    "target_date": target_actual.isoformat(),
                    "days_forward": df_days,
                    "days_averaged": 1,
                    "spot": spot,
                    "expiry_used": expiry.isoformat(),
                    "data_source": source_log[0] if source_log else "unknown",
                }

            if target_actual <= date.today():
                yield _sse({"stage": "Fetching realized price", "progress": 95})
                realized = _get_realized_price(ticker_upper, target_actual)
                if realized is not None:
                    meta["realized_price"] = realized

            yield _sse({
                "done": True,
                "progress": 100,
                "result": _build_response(result, meta),
            })

        except Exception as e:
            logger.error("predict-stream failed: %s", e)
            yield _sse({"error": str(e)})

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/market-context")
async def market_context(
    ticker: str = "SPY",
    obs_from: str = "2025-11-01",
    obs_to: str = "2026-03-01",
):
    """Fetch AI-generated market context for the observation period."""
    try:
        events = fetch_market_context(ticker, obs_from, obs_to)
        return {
            "events": events,
            "disclaimer": "AI-generated summary based on the model's training data. Verify independently.",
        }
    except Exception as e:
        logger.error("market-context failed: %s", e)
        return {"events": [], "disclaimer": "Failed to fetch market context."}
