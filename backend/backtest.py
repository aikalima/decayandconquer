"""Backtesting harness for the options price prediction pipeline.

Fetches historical options chains, runs the prediction pipeline,
compares predicted distributions against realized prices, and
produces calibration diagnostics.

Usage:
    python backtest.py --ticker SPY --days-forward 30
    python backtest.py --ticker AAPL --ticker NVDA --days-forward 60
"""

from __future__ import annotations
import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from app.prediction_pipeline.predict import predict_price
from app.prediction_pipeline.step3_smooth_iv import BSplineParams
from app.data.fetcher import fetch_options_chain, fetch_spot_price, get_client, find_nearest_expiry_friday

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

PLOT_DIR = Path("tests/plots/backtest")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    obs_date: date
    expiry_date: date
    ticker: str
    spot: float
    realized_price: float
    predicted_df: pd.DataFrame  # Price, PDF, CDF
    cdf_percentile: float
    predicted_median: float
    predicted_mean: float
    abs_error_median: float
    abs_error_mean: float
    ci_90_low: float
    ci_90_high: float
    realized_in_ci_90: bool


@dataclass
class BacktestSummary:
    ticker: str
    days_forward: int
    results: list[BacktestResult]
    mae_median: float
    mae_mean: float
    ci_90_coverage: float
    cdf_percentiles: list[float]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_prediction(result_df: pd.DataFrame, realized_price: float) -> dict:
    """Score a single prediction against a realized price.

    Returns dict with: cdf_percentile, predicted_median, predicted_mean,
    ci_90_low, ci_90_high.
    """
    prices = result_df["Price"].values
    pdf = result_df["PDF"].values
    cdf = result_df["CDF"].values

    # CDF percentile via interpolation (clip to [0, 1] if outside domain)
    if realized_price <= prices[0]:
        cdf_pct = 0.0
    elif realized_price >= prices[-1]:
        cdf_pct = 1.0
    else:
        cdf_pct = float(np.interp(realized_price, prices, cdf))

    # Median: price where CDF crosses 0.5
    median_price = float(np.interp(0.5, cdf, prices))

    # Mean: E[X] = integral(x * pdf dx)
    mean_price = float(np.trapezoid(prices * pdf, prices))

    # 90% confidence interval: CDF = 0.05 and CDF = 0.95
    ci_low = float(np.interp(0.05, cdf, prices))
    ci_high = float(np.interp(0.95, cdf, prices))

    return {
        "cdf_percentile": cdf_pct,
        "predicted_median": median_price,
        "predicted_mean": mean_price,
        "ci_90_low": ci_low,
        "ci_90_high": ci_high,
    }



# ---------------------------------------------------------------------------
# Backtest runner
# ---------------------------------------------------------------------------

def run_backtest(
    ticker: str,
    observation_dates: list[date],
    days_forward: int,
    risk_free_rate: float = 0.04,
    solver: str = "brent",
    kernel_smooth: bool = False,
    bspline: BSplineParams = BSplineParams(),
    rate_limit_sleep: float = 12.0,
    api_key: str | None = None,
) -> BacktestSummary:
    """Run the backtest across multiple observation dates."""
    client = get_client(api_key)
    results: list[BacktestResult] = []

    for obs_date in observation_dates:
        expiry_date = find_nearest_expiry_friday(obs_date, days_forward)
        logger.info("--- %s | obs=%s  expiry=%s ---", ticker, obs_date, expiry_date)

        try:
            # Fetch data
            spot = fetch_spot_price(ticker, obs_date, client, rate_limit_sleep=rate_limit_sleep)
            chain = fetch_options_chain(
                ticker, obs_date, expiry_date, spot=spot,
                client=client, rate_limit_sleep=rate_limit_sleep,
            )
            realized = fetch_spot_price(ticker, expiry_date, client, rate_limit_sleep=rate_limit_sleep)

            # Run pipeline
            pred_df = predict_price(
                quotes=chain,
                spot=spot,
                days_forward=days_forward,
                risk_free_rate=risk_free_rate,
                solver=solver,
                bspline=bspline,
                kernel_smooth=kernel_smooth,
            ).df

            # Score
            scores = score_prediction(pred_df, realized)
            result = BacktestResult(
                obs_date=obs_date,
                expiry_date=expiry_date,
                ticker=ticker,
                spot=spot,
                realized_price=realized,
                predicted_df=pred_df,
                cdf_percentile=scores["cdf_percentile"],
                predicted_median=scores["predicted_median"],
                predicted_mean=scores["predicted_mean"],
                abs_error_median=abs(scores["predicted_median"] - realized),
                abs_error_mean=abs(scores["predicted_mean"] - realized),
                ci_90_low=scores["ci_90_low"],
                ci_90_high=scores["ci_90_high"],
                realized_in_ci_90=scores["ci_90_low"] <= realized <= scores["ci_90_high"],
            )
            results.append(result)
            logger.info(
                "  spot=%.2f  realized=%.2f  median=%.2f  CDF%%=%.2f  in_CI=%s",
                spot, realized, scores["predicted_median"],
                scores["cdf_percentile"], result.realized_in_ci_90,
            )

        except Exception as e:
            logger.error("  FAILED: %s", e)
            continue

    if not results:
        raise RuntimeError(f"All observation dates failed for {ticker}")

    cdf_pcts = [r.cdf_percentile for r in results]
    return BacktestSummary(
        ticker=ticker,
        days_forward=days_forward,
        results=results,
        mae_median=float(np.mean([r.abs_error_median for r in results])),
        mae_mean=float(np.mean([r.abs_error_mean for r in results])),
        ci_90_coverage=sum(r.realized_in_ci_90 for r in results) / len(results),
        cdf_percentiles=cdf_pcts,
    )


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_single_prediction(result: BacktestResult, output_dir: Path):
    """Plot predicted PDF with realized price marked."""
    df = result.predicted_df
    fig, (ax_pdf, ax_cdf) = plt.subplots(1, 2, figsize=(14, 5.5))

    days = (result.expiry_date - result.obs_date).days
    fig.suptitle(
        f"{result.ticker} — obs {result.obs_date}  |  T = {days}d  |  expiry {result.expiry_date}",
        fontsize=13, fontweight="bold",
    )

    # PDF
    ax_pdf.plot(df["Price"], df["PDF"], color="steelblue", linewidth=1.5)
    ax_pdf.fill_between(df["Price"], df["PDF"], alpha=0.15, color="steelblue")
    ax_pdf.axvline(result.spot, color="crimson", linestyle="--", linewidth=1,
                   label=f"Spot = ${result.spot:.2f}")
    ax_pdf.axvline(result.realized_price, color="black", linewidth=2,
                   label=f"Realized = ${result.realized_price:.2f}")
    ax_pdf.axvline(result.predicted_median, color="green", linestyle=":", linewidth=1,
                   label=f"Median = ${result.predicted_median:.1f}")
    ax_pdf.axvspan(result.ci_90_low, result.ci_90_high, alpha=0.08, color="orange",
                   label=f"90% CI [{result.ci_90_low:.0f}, {result.ci_90_high:.0f}]")
    ax_pdf.set_title("Probability Density")
    ax_pdf.set_xlabel(f"Price at Expiry ($)")
    ax_pdf.set_ylabel("Probability Density (per $)")
    ax_pdf.legend(fontsize=8)
    ax_pdf.grid(True, linestyle="--", alpha=0.3)

    # CDF
    ax_cdf.plot(df["Price"], df["CDF"], color="darkorange", linewidth=1.5)
    ax_cdf.axvline(result.spot, color="crimson", linestyle="--", linewidth=1,
                   label=f"Spot = ${result.spot:.2f}")
    ax_cdf.axvline(result.realized_price, color="black", linewidth=2,
                   label=f"Realized = ${result.realized_price:.2f}")
    ax_cdf.axhline(result.cdf_percentile, color="gray", linestyle=":", linewidth=0.8,
                   label=f"CDF(realized) = {result.cdf_percentile:.2f}")
    ax_cdf.set_title("Cumulative Distribution")
    ax_cdf.set_xlabel("Price at Expiry ($)")
    ax_cdf.set_ylabel("P(Price < x)")
    ax_cdf.set_ylim(-0.02, 1.02)
    ax_cdf.legend(fontsize=8)
    ax_cdf.grid(True, linestyle="--", alpha=0.3)

    fig.tight_layout()
    fname = f"{result.ticker}_{result.obs_date}.png"
    fig.savefig(output_dir / fname, dpi=150)
    plt.show()


def plot_calibration(summary: BacktestSummary, output_dir: Path):
    """Plot calibration histogram of CDF percentiles."""
    fig, (ax_hist, ax_qq) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(
        f"{summary.ticker} — Calibration ({len(summary.results)} dates, {summary.days_forward}d horizon)",
        fontsize=13, fontweight="bold",
    )

    pcts = summary.cdf_percentiles
    n_bins = max(5, len(pcts) // 2)

    # Histogram
    ax_hist.hist(pcts, bins=n_bins, range=(0, 1), color="steelblue", edgecolor="white", alpha=0.8)
    ax_hist.axhline(len(pcts) / n_bins, color="crimson", linestyle="--", linewidth=1,
                    label="Expected (uniform)")
    ax_hist.set_xlabel("CDF Percentile of Realized Price")
    ax_hist.set_ylabel("Count")
    ax_hist.set_title("Calibration Histogram")
    ax_hist.legend()
    ax_hist.grid(True, linestyle="--", alpha=0.3)

    # Q-Q plot
    sorted_pcts = np.sort(pcts)
    expected = np.linspace(0, 1, len(sorted_pcts) + 2)[1:-1]
    ax_qq.scatter(expected, sorted_pcts, color="steelblue", s=40, zorder=3)
    ax_qq.plot([0, 1], [0, 1], color="crimson", linestyle="--", linewidth=1, label="Perfect calibration")
    ax_qq.set_xlabel("Expected Uniform Quantile")
    ax_qq.set_ylabel("Observed CDF Percentile")
    ax_qq.set_title("Q-Q Plot")
    ax_qq.set_xlim(-0.05, 1.05)
    ax_qq.set_ylim(-0.05, 1.05)
    ax_qq.set_aspect("equal")
    ax_qq.legend()
    ax_qq.grid(True, linestyle="--", alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_dir / f"{summary.ticker}_calibration.png", dpi=150)
    plt.show()


def print_summary_table(summary: BacktestSummary):
    """Print a formatted results table."""
    print(f"\n{'=' * 90}")
    print(f"  BACKTEST: {summary.ticker}  |  {summary.days_forward}-day horizon  |  {len(summary.results)} dates")
    print(f"{'=' * 90}")
    print(f"  {'Date':>12}  {'Spot':>8}  {'Median':>8}  {'Mean':>8}  {'Realized':>9}  {'CDF%':>6}  {'90% CI':>16}  {'Hit':>4}")
    print(f"  {'-'*12}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*9}  {'-'*6}  {'-'*16}  {'-'*4}")
    for r in summary.results:
        ci = f"[{r.ci_90_low:.0f}, {r.ci_90_high:.0f}]"
        hit = "Y" if r.realized_in_ci_90 else "N"
        print(
            f"  {r.obs_date!s:>12}  {r.spot:8.2f}  {r.predicted_median:8.2f}  "
            f"{r.predicted_mean:8.2f}  {r.realized_price:9.2f}  {r.cdf_percentile:6.2f}  "
            f"{ci:>16}  {hit:>4}"
        )
    print(f"  {'-'*12}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*9}  {'-'*6}  {'-'*16}  {'-'*4}")
    print(f"  MAE (median): ${summary.mae_median:.2f}")
    print(f"  MAE (mean):   ${summary.mae_mean:.2f}")
    print(f"  90% CI coverage: {summary.ci_90_coverage:.0%} ({sum(r.realized_in_ci_90 for r in summary.results)}/{len(summary.results)})")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DEFAULT_SPY_DATES = [
    date(2025, 1, 6),
    date(2025, 1, 13),
    date(2025, 1, 21),
    date(2025, 1, 27),
    date(2025, 2, 3),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backtest the options price prediction pipeline")
    p.add_argument("--ticker", action="append", default=[], help="Ticker(s) to backtest (repeatable)")
    p.add_argument("--days-forward", type=int, default=30, help="Prediction horizon in days")
    p.add_argument("--risk-free-rate", type=float, default=0.04, help="Annualised risk-free rate")
    p.add_argument("--solver", default="brent", choices=["brent", "newton"])
    p.add_argument("--kde", action="store_true", help="Enable KDE smoothing")
    p.add_argument("--rate-limit", type=float, default=DEFAULT_SPY_DATES and 12.0,
                   help="Seconds between API calls (default 12 for free tier)")
    p.add_argument("--api-key", default=None, help="Massive API key (or set MASSIVE_API_KEY)")
    p.add_argument("--dates", nargs="+", default=None,
                   help="Observation dates as YYYY-MM-DD (default: 5 SPY dates in Jan 2025)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    tickers = args.ticker or ["SPY"]

    if args.dates:
        observation_dates = [date.fromisoformat(d) for d in args.dates]
    else:
        observation_dates = DEFAULT_SPY_DATES

    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    for ticker in tickers:
        summary = run_backtest(
            ticker=ticker,
            observation_dates=observation_dates,
            days_forward=args.days_forward,
            risk_free_rate=args.risk_free_rate,
            solver=args.solver,
            kernel_smooth=args.kde,
            rate_limit_sleep=args.rate_limit,
            api_key=args.api_key,
        )

        print_summary_table(summary)

        for result in summary.results:
            plot_single_prediction(result, PLOT_DIR)

        if len(summary.results) >= 3:
            plot_calibration(summary, PLOT_DIR)
