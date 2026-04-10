"""Top-level pipeline to estimate a risk-neutral price PDF from call quotes.

Steps:
1. Validate quotes
2. Solve implied volatility per strike (optionally averaged across a date range)
3. Smooth the IV smile with a B-spline
4. Extract PDF via Breeden-Litzenberger (normalised to integrate to 1)
5. Optionally smooth with KDE
6. Compute CDF

Returns a PipelineResult with the PDF/CDF DataFrame and IV smile data.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import numpy as np
import pandas as pd
from .step1_prep import validate_quotes
from .step2_implied_vol import calculate_IV, calculate_IV_averaged
from .step3_smooth_iv import fit_bspline_IV, BSplineParams
from .step4_pdf import extract_pdf, compute_cdf
from .step5_smooth_pdf import fit_kde


@dataclass
class PipelineResult:
    """Full output of the prediction pipeline."""
    df: pd.DataFrame                    # columns: Price, PDF, CDF
    iv_raw_strikes: list[float]         # per-strike IV observations (before smoothing)
    iv_raw_values: list[float]
    iv_smooth_strikes: list[float]      # dense B-spline smoothed IV
    iv_smooth_values: list[float]
    n_strikes_used: int                 # how many strikes had valid IV


def _iv_to_result(
    iv_df: pd.DataFrame,
    spot: float,
    days_forward: int,
    risk_free_rate: float,
    bspline: BSplineParams,
    kernel_smooth: bool,
) -> PipelineResult:
    """From IV DataFrame -> full PipelineResult with IV smile + PDF/CDF."""
    if len(iv_df) < 5:
        raise ValueError(
            f"Only {len(iv_df)} strikes with valid IV (need at least 5). "
            "Check that spot price and days_forward match the option chain data."
        )

    # Capture raw IV
    iv_raw_strikes = iv_df["strike"].tolist()
    iv_raw_values = iv_df["iv"].tolist()
    n_strikes = len(iv_df)

    # B-spline smoothing
    smooth_strikes, smooth_iv = fit_bspline_IV(iv_df, bspline)

    # Breeden-Litzenberger PDF
    strikes, pdf = extract_pdf((smooth_strikes, smooth_iv), spot, days_forward, risk_free_rate)

    # Optional KDE smoothing
    if kernel_smooth:
        strikes, pdf = fit_kde(strikes, pdf)

    # CDF
    cdf = compute_cdf(strikes, pdf)

    return PipelineResult(
        df=pd.DataFrame({"Price": strikes, "PDF": pdf, "CDF": cdf}),
        iv_raw_strikes=iv_raw_strikes,
        iv_raw_values=iv_raw_values,
        iv_smooth_strikes=smooth_strikes.tolist(),
        iv_smooth_values=smooth_iv.tolist(),
        n_strikes_used=n_strikes,
    )


# ---------------------------------------------------------------------------
# Public API — return PipelineResult
# ---------------------------------------------------------------------------

def predict_price(
    quotes: pd.DataFrame,
    spot: float,
    days_forward: int,
    risk_free_rate: float,
    solver: str = "brent",
    bspline: BSplineParams = BSplineParams(),
    kernel_smooth: bool = False,
) -> PipelineResult:
    """Run the pipeline from a single day's options chain."""
    df = quotes.copy()
    for col in ("strike", "last_price"):
        df[col] = df[col].astype(np.float64)

    df = validate_quotes(df)
    df = calculate_IV(df, spot, days_forward, risk_free_rate, solver)

    return _iv_to_result(df, spot, days_forward, risk_free_rate, bspline, kernel_smooth)


def predict_price_averaged(
    chains_by_date: dict[str, pd.DataFrame],
    spot: float,
    days_forward: int,
    expiry: date,
    risk_free_rate: float,
    solver: str = "brent",
    bspline: BSplineParams = BSplineParams(),
    kernel_smooth: bool = False,
) -> PipelineResult:
    """Run the pipeline using IV averaged across multiple days."""
    days_forward_by_date = {}
    validated = {}
    for date_str, chain in chains_by_date.items():
        d = date.fromisoformat(date_str)
        days_forward_by_date[date_str] = (expiry - d).days
        df = chain.copy()
        for col in ("strike", "last_price"):
            df[col] = df[col].astype(np.float64)
        df = validate_quotes(df)
        if len(df) > 0:
            validated[date_str] = df

    iv_df = calculate_IV_averaged(
        validated, spot, days_forward_by_date, risk_free_rate, solver,
    )

    return _iv_to_result(iv_df, spot, days_forward, risk_free_rate, bspline, kernel_smooth)


# ---------------------------------------------------------------------------
# Progress variants — yield (stage, pct) tuples, final yield is PipelineResult
# ---------------------------------------------------------------------------

def predict_price_with_progress(
    quotes: pd.DataFrame,
    spot: float,
    days_forward: int,
    risk_free_rate: float,
    solver: str = "brent",
    bspline: BSplineParams = BSplineParams(),
    kernel_smooth: bool = False,
):
    yield ("Validating quotes", 50)
    df = quotes.copy()
    for col in ("strike", "last_price"):
        df[col] = df[col].astype(np.float64)
    df = validate_quotes(df)

    yield ("Solving implied volatility", 55)
    df = calculate_IV(df, spot, days_forward, risk_free_rate, solver)

    if len(df) < 5:
        raise ValueError(f"Only {len(df)} options survived IV solving (need at least 5).")

    iv_raw_strikes = df["strike"].tolist()
    iv_raw_values = df["iv"].tolist()

    yield ("Smoothing IV curve", 70)
    smooth_strikes, smooth_iv = fit_bspline_IV(df, bspline)

    yield ("Extracting price distribution", 80)
    strikes, pdf = extract_pdf((smooth_strikes, smooth_iv), spot, days_forward, risk_free_rate)

    if kernel_smooth:
        yield ("Smoothing distribution (KDE)", 85)
        strikes, pdf = fit_kde(strikes, pdf)

    yield ("Computing CDF", 90)
    cdf = compute_cdf(strikes, pdf)

    yield PipelineResult(
        df=pd.DataFrame({"Price": strikes, "PDF": pdf, "CDF": cdf}),
        iv_raw_strikes=iv_raw_strikes,
        iv_raw_values=iv_raw_values,
        iv_smooth_strikes=smooth_strikes.tolist(),
        iv_smooth_values=smooth_iv.tolist(),
        n_strikes_used=len(iv_raw_strikes),
    )


def predict_price_averaged_with_progress(
    chains_by_date: dict[str, pd.DataFrame],
    spot: float,
    days_forward: int,
    expiry: date,
    risk_free_rate: float,
    solver: str = "brent",
    bspline: BSplineParams = BSplineParams(),
    kernel_smooth: bool = False,
):
    yield ("Validating quotes", 30)
    days_forward_by_date = {}
    validated = {}
    for date_str, chain in chains_by_date.items():
        d = date.fromisoformat(date_str)
        days_forward_by_date[date_str] = (expiry - d).days
        df = chain.copy()
        for col in ("strike", "last_price"):
            df[col] = df[col].astype(np.float64)
        df = validate_quotes(df)
        if len(df) > 0:
            validated[date_str] = df

    yield (f"Averaging IV across {len(validated)} days", 40)
    iv_df = calculate_IV_averaged(
        validated, spot, days_forward_by_date, risk_free_rate, solver,
    )

    if len(iv_df) < 5:
        raise ValueError(f"Only {len(iv_df)} strikes with valid IV (need at least 5).")

    iv_raw_strikes = iv_df["strike"].tolist()
    iv_raw_values = iv_df["iv"].tolist()

    yield ("Smoothing IV curve", 70)
    smooth_strikes, smooth_iv = fit_bspline_IV(iv_df, bspline)

    yield ("Extracting price distribution", 80)
    strikes, pdf = extract_pdf((smooth_strikes, smooth_iv), spot, days_forward, risk_free_rate)

    if kernel_smooth:
        yield ("Smoothing distribution (KDE)", 85)
        strikes, pdf = fit_kde(strikes, pdf)

    yield ("Computing CDF", 90)
    cdf = compute_cdf(strikes, pdf)

    yield PipelineResult(
        df=pd.DataFrame({"Price": strikes, "PDF": pdf, "CDF": cdf}),
        iv_raw_strikes=iv_raw_strikes,
        iv_raw_values=iv_raw_values,
        iv_smooth_strikes=smooth_strikes.tolist(),
        iv_smooth_values=smooth_iv.tolist(),
        n_strikes_used=len(iv_raw_strikes),
    )
