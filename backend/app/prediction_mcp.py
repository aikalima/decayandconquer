"""Read-only MCP server for prediction and backtest data.

Run with:
    python -m app.prediction_mcp
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Literal

import numpy as np
import pandas as pd
from mcp.server import MCPServer

from app.data.db import (
    find_best_expiry,
    find_best_expiry_in_range,
    get_db,
    get_stats,
    has_data,
    query_chain,
    query_chains_range,
    set_read_only,
)
from app.data.fetcher import find_nearest_expiry_friday
from app.defaults import build_app_defaults
from app.prediction_pipeline.predict import PipelineResult, predict_price, predict_price_averaged
from app.prediction_pipeline.step3_smooth_iv import BSplineParams

set_read_only(True)
logging.getLogger("app.data.db").setLevel(logging.WARNING)

mcp = MCPServer(
    "decay-predictions",
    title="Decay And Conquer Predictions",
    description="Read-only local access to prediction and backtest features backed by DuckDB options data.",
    instructions=(
        "Use these tools to run Decay And Conquer price-distribution predictions and compact "
        "historical backtests. Data is read from local DuckDB and may lag the market."
    ),
    log_level="ERROR",
)

Solver = Literal["brent", "newton"]


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must be a valid YYYY-MM-DD date")


def _chain_spot(chain: pd.DataFrame) -> float:
    """Approximate spot from the deepest ITM call in the option chain."""
    if chain.empty:
        raise ValueError("option chain is empty")
    return float(chain.iloc[0]["strike"] + chain.iloc[0]["last_price"])


def _realized_price_from_db(ticker: str, target: date) -> dict | None:
    """Approximate realized underlying price from local options data."""
    db = get_db()
    row = db.execute("""
        SELECT trade_date,
               MIN(strike) AS min_strike,
               FIRST(close ORDER BY strike) AS min_strike_price
        FROM options
        WHERE underlying = ?
          AND contract_type = 'C'
          AND close > 0
          AND trade_date >= ?
        GROUP BY trade_date
        ORDER BY trade_date
        LIMIT 1
    """, [ticker, target.isoformat()]).fetchone()
    if not row:
        return None
    return {
        "date": str(row[0]),
        "price": round(float(row[1] + row[2]), 2),
        "basis": "nearest local options trading date on or after target_date",
    }


def _score_distribution(result: PipelineResult, spot: float, price_targets: list[float] | None = None) -> dict:
    df = result.df
    prices = df["Price"].values
    pdf = df["PDF"].values
    cdf = df["CDF"].values

    mean_p = float(np.trapezoid(prices * pdf, prices))
    median_p = float(np.interp(0.5, cdf, prices))
    std_p = float(np.sqrt(np.trapezoid((prices - mean_p) ** 2 * pdf, prices)))

    targets = []
    for target in price_targets or []:
        probability_below = float(np.interp(float(target), prices, cdf))
        targets.append({
            "price": round(float(target), 2),
            "probability_below": round(probability_below, 4),
            "probability_above": round(1 - probability_below, 4),
        })

    return {
        "mean": round(mean_p, 2),
        "median": round(median_p, 2),
        "std_dev": round(std_p, 2),
        "p5": round(float(np.interp(0.05, cdf, prices)), 2),
        "p25": round(float(np.interp(0.25, cdf, prices)), 2),
        "p75": round(float(np.interp(0.75, cdf, prices)), 2),
        "p95": round(float(np.interp(0.95, cdf, prices)), 2),
        "probability_above_spot": round(1 - float(np.interp(spot, prices, cdf)), 4),
        "probability_below_spot": round(float(np.interp(spot, prices, cdf)), 4),
        "price_targets": targets,
        "n_strikes": result.n_strikes_used,
    }


def _run_prediction(
    *,
    ticker: str,
    obs_from: date,
    obs_to: date,
    target: date,
    risk_free_rate: float,
    solver: Solver,
    kernel_smooth: bool,
    price_targets: list[float] | None = None,
    include_distribution_points: int = 0,
) -> dict:
    ticker = ticker.upper()
    days_forward = (target - obs_to).days
    if days_forward <= 0:
        raise ValueError("target_date must be after obs_date_to")

    bspline = BSplineParams()
    desired_expiry = find_nearest_expiry_friday(obs_to, days_forward)
    is_range = obs_from != obs_to

    if is_range:
        db_expiry = find_best_expiry_in_range(ticker, obs_from, obs_to, desired_expiry)
        if not db_expiry:
            raise ValueError(f"No options data in DB for {ticker} from {obs_from} to {obs_to}")
        all_rows = query_chains_range(ticker, obs_from, obs_to, db_expiry)
        chains = {
            str(td)[:10]: grp[["strike", "last_price", "bid", "ask"]].reset_index(drop=True)
            for td, grp in all_rows.groupby("trade_date")
        }
        latest_chain = chains[max(chains.keys())]
        spot = _chain_spot(latest_chain)
        result = predict_price_averaged(
            chains_by_date=chains,
            spot=spot,
            days_forward=days_forward,
            expiry=db_expiry,
            risk_free_rate=risk_free_rate,
            solver=solver,
            bspline=bspline,
            kernel_smooth=kernel_smooth,
        )
        data_source = "duckdb_range"
        days_averaged = len(chains)
    else:
        if not has_data(ticker, obs_to):
            raise ValueError(f"No options data in DB for {ticker} on {obs_to}")
        db_expiry = find_best_expiry(ticker, obs_to, desired_expiry)
        if not db_expiry:
            raise ValueError(f"No expiry near {desired_expiry} for {ticker} on {obs_to}")
        chain = query_chain(ticker, obs_to, db_expiry)
        spot = _chain_spot(chain)
        result = predict_price(
            quotes=chain,
            spot=spot,
            days_forward=days_forward,
            risk_free_rate=risk_free_rate,
            solver=solver,
            bspline=bspline,
            kernel_smooth=kernel_smooth,
        )
        data_source = "duckdb"
        days_averaged = 1

    summary = _score_distribution(result, spot, price_targets)
    realized = _realized_price_from_db(ticker, target)
    if realized:
        prices = result.df["Price"].values
        cdf = result.df["CDF"].values
        realized_price = realized["price"]
        realized["cdf_percentile"] = round(float(np.interp(realized_price, prices, cdf)), 4)
        realized["prediction_error_vs_median"] = round(realized_price - summary["median"], 2)

    output = {
        "ticker": ticker,
        "obs_date_from": obs_from.isoformat(),
        "obs_date_to": obs_to.isoformat(),
        "target_date": target.isoformat(),
        "days_forward": days_forward,
        "days_averaged": days_averaged,
        "spot": round(spot, 2),
        "expiry_used": db_expiry.isoformat(),
        "data_source": data_source,
        "risk_free_rate": risk_free_rate,
        "solver": solver,
        "kernel_smooth": kernel_smooth,
        "summary": summary,
        "realized": realized,
    }

    points = max(0, min(int(include_distribution_points), 500))
    if points:
        sample = result.df.iloc[np.linspace(0, len(result.df) - 1, points, dtype=int)]
        output["distribution_points"] = [
            {
                "price": round(float(row.Price), 2),
                "pdf": round(float(row.PDF), 8),
                "cdf": round(float(row.CDF), 6),
            }
            for row in sample.itertuples(index=False)
        ]

    return output


@mcp.tool(description="Return date-aware prediction defaults and local DuckDB summary statistics.")
def get_prediction_defaults() -> dict:
    """Return defaults for prediction tools."""
    defaults = build_app_defaults()
    try:
        stats = get_stats()
    except Exception as exc:
        stats = {"error": str(exc)}
    return {
        "defaults": defaults.get("prediction", {}),
        "latest_data_date": defaults.get("latest_data_date"),
        "earliest_data_date": defaults.get("earliest_data_date"),
        "database": stats,
    }


@mcp.tool(
    description=(
        "Run a price-distribution prediction from local DuckDB options data. "
        "Use obs_date for a single day or obs_date_from/obs_date_to for an averaged observation window."
    )
)
def run_prediction(
    ticker: str = "SPY",
    obs_date: str | None = None,
    obs_date_from: str | None = None,
    obs_date_to: str | None = None,
    target_date: str | None = None,
    days_forward: int = 30,
    risk_free_rate: float = 0.04,
    solver: Solver = "brent",
    kernel_smooth: bool = False,
    price_targets: list[float] | None = None,
    include_distribution_points: int = 0,
) -> dict:
    """Run a local prediction and return compact distribution statistics."""
    defaults = build_app_defaults().get("prediction", {})
    ticker = ticker.strip().upper() or defaults.get("ticker", "SPY")
    obs_from_s = obs_date_from or obs_date or defaults.get("obs_date_from")
    obs_to_s = obs_date_to or obs_date or defaults.get("obs_date_to")
    if not obs_from_s or not obs_to_s:
        raise ValueError("obs_date or obs_date_from/obs_date_to is required")

    obs_from = _parse_date(obs_from_s, "obs_date_from")
    obs_to = _parse_date(obs_to_s, "obs_date_to")
    if obs_from > obs_to:
        raise ValueError("obs_date_from must be on or before obs_date_to")

    if target_date:
        target = _parse_date(target_date, "target_date")
    else:
        target = obs_to + timedelta(days=int(days_forward))

    return _run_prediction(
        ticker=ticker,
        obs_from=obs_from,
        obs_to=obs_to,
        target=target,
        risk_free_rate=float(risk_free_rate),
        solver=solver,
        kernel_smooth=bool(kernel_smooth),
        price_targets=price_targets,
        include_distribution_points=include_distribution_points,
    )


@mcp.tool(
    description=(
        "Backtest the prediction model over explicit historical observation dates using local DuckDB data. "
        "Returns per-date realized percentiles, median/mean errors, and 90% interval coverage."
    )
)
def run_backtest(
    ticker: str = "SPY",
    observation_dates: list[str] | None = None,
    days_forward: int = 30,
    risk_free_rate: float = 0.04,
    solver: Solver = "brent",
    kernel_smooth: bool = False,
    limit: int = 12,
) -> dict:
    """Run a compact local backtest for supplied observation dates."""
    ticker = ticker.strip().upper()
    if not ticker:
        return {"error": "ticker is required"}
    if not observation_dates:
        return {"error": "observation_dates is required, e.g. ['2026-06-01', '2026-06-08']"}

    rows = []
    errors = []
    for value in observation_dates[: max(1, min(int(limit), 50))]:
        try:
            obs = _parse_date(value, "observation_dates")
            target = obs + timedelta(days=int(days_forward))
            prediction = _run_prediction(
                ticker=ticker,
                obs_from=obs,
                obs_to=obs,
                target=target,
                risk_free_rate=float(risk_free_rate),
                solver=solver,
                kernel_smooth=bool(kernel_smooth),
            )
            realized = prediction.get("realized")
            if not realized:
                errors.append({"obs_date": obs.isoformat(), "error": "No realized price in local DB"})
                continue
            summary = prediction["summary"]
            rows.append({
                "obs_date": obs.isoformat(),
                "target_date": target.isoformat(),
                "realized_date": realized["date"],
                "spot": prediction["spot"],
                "realized_price": realized["price"],
                "predicted_median": summary["median"],
                "predicted_mean": summary["mean"],
                "cdf_percentile": realized["cdf_percentile"],
                "abs_error_median": round(abs(realized["price"] - summary["median"]), 2),
                "abs_error_mean": round(abs(realized["price"] - summary["mean"]), 2),
                "ci_90_low": summary["p5"],
                "ci_90_high": summary["p95"],
                "realized_in_ci_90": summary["p5"] <= realized["price"] <= summary["p95"],
                "expiry_used": prediction["expiry_used"],
                "n_strikes": summary["n_strikes"],
            })
        except Exception as exc:
            errors.append({"obs_date": str(value), "error": str(exc)})

    if not rows:
        return {"ticker": ticker, "days_forward": days_forward, "results": [], "errors": errors}

    return {
        "ticker": ticker,
        "days_forward": days_forward,
        "count": len(rows),
        "mae_median": round(float(np.mean([row["abs_error_median"] for row in rows])), 2),
        "mae_mean": round(float(np.mean([row["abs_error_mean"] for row in rows])), 2),
        "ci_90_coverage": round(sum(row["realized_in_ci_90"] for row in rows) / len(rows), 4),
        "cdf_percentiles": [row["cdf_percentile"] for row in rows],
        "results": rows,
        "errors": errors,
    }


@mcp.resource(
    "prediction://defaults",
    description="JSON prediction defaults and local DuckDB summary.",
    mime_type="application/json",
)
def prediction_defaults_resource() -> dict:
    """Expose prediction defaults as an MCP resource."""
    return get_prediction_defaults()


if __name__ == "__main__":
    mcp.run()
