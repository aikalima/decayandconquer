"""Top-level pipeline to estimate a risk-neutral price PDF from call quotes.

Steps:
1. Validate quotes
2. Solve implied volatility per strike (optionally averaged across a date range)
3. Smooth the IV smile with a B-spline
4. Extract PDF via Breeden-Litzenberger (normalised to integrate to 1)
5. Optionally smooth with KDE
6. Compute CDF

Returns a DataFrame with columns: Price, PDF, CDF.
"""

from __future__ import annotations
from datetime import date
import numpy as np
import pandas as pd
from .step1_prep import validate_quotes
from .step2_implied_vol import calculate_IV, calculate_IV_averaged
from .step3_smooth_iv import fit_bspline_IV, BSplineParams
from .step4_pdf import extract_pdf, compute_cdf
from .step5_smooth_pdf import fit_kde


def _iv_to_pdf(
    iv_df: pd.DataFrame,
    spot: float,
    days_forward: int,
    risk_free_rate: float,
    bspline: BSplineParams,
    kernel_smooth: bool,
) -> pd.DataFrame:
    """Shared pipeline from IV DataFrame -> PDF/CDF output.

    iv_df must have columns [strike, iv].
    """
    if len(iv_df) < 5:
        raise ValueError(
            f"Only {len(iv_df)} strikes with valid IV (need at least 5). "
            "Check that spot price and days_forward match the option chain data."
        )

    # B-spline smoothing
    denoised_iv = fit_bspline_IV(iv_df, bspline)

    # Breeden-Litzenberger PDF
    strikes, pdf = extract_pdf(denoised_iv, spot, days_forward, risk_free_rate)

    # Optional KDE smoothing
    if kernel_smooth:
        strikes, pdf = fit_kde(strikes, pdf)

    # CDF
    cdf = compute_cdf(strikes, pdf)

    return pd.DataFrame({"Price": strikes, "PDF": pdf, "CDF": cdf})


def predict_price(
    quotes: pd.DataFrame,
    spot: float,
    days_forward: int,
    risk_free_rate: float,
    solver: str = "brent",
    bspline: BSplineParams = BSplineParams(),
    kernel_smooth: bool = False,
) -> pd.DataFrame:
    """Run the pipeline from a single day's options chain."""
    df = quotes.copy()
    for col in ("strike", "last_price"):
        df[col] = df[col].astype(np.float64)

    df = validate_quotes(df)
    df = calculate_IV(df, spot, days_forward, risk_free_rate, solver)

    return _iv_to_pdf(df, spot, days_forward, risk_free_rate, bspline, kernel_smooth)


def predict_price_averaged(
    chains_by_date: dict[str, pd.DataFrame],
    spot: float,
    days_forward: int,
    expiry: date,
    risk_free_rate: float,
    solver: str = "brent",
    bspline: BSplineParams = BSplineParams(),
    kernel_smooth: bool = False,
) -> pd.DataFrame:
    """Run the pipeline using IV averaged across multiple days.

    Args:
        chains_by_date: {trade_date_str: DataFrame[strike, last_price, ...]}
        spot: reference spot price (from the latest date in the range)
        days_forward: days from the latest observation date to expiry
        expiry: the option expiry date (used to compute per-date days_forward)
        risk_free_rate: annualised risk-free rate
    """
    # Compute days_forward for each date in the range
    days_forward_by_date = {}
    for date_str in chains_by_date:
        d = date.fromisoformat(date_str)
        days_fwd = (expiry - d).days
        days_forward_by_date[date_str] = days_fwd

    # Validate each chain
    validated = {}
    for date_str, chain in chains_by_date.items():
        df = chain.copy()
        for col in ("strike", "last_price"):
            df[col] = df[col].astype(np.float64)
        df = validate_quotes(df)
        if len(df) > 0:
            validated[date_str] = df

    # Average IV across dates
    iv_df = calculate_IV_averaged(
        validated, spot, days_forward_by_date, risk_free_rate, solver,
    )

    return _iv_to_pdf(iv_df, spot, days_forward, risk_free_rate, bspline, kernel_smooth)


def predict_price_with_progress(
    quotes: pd.DataFrame,
    spot: float,
    days_forward: int,
    risk_free_rate: float,
    solver: str = "brent",
    bspline: BSplineParams = BSplineParams(),
    kernel_smooth: bool = False,
):
    """Single-day pipeline with progress yields."""
    yield ("Validating quotes", 50)

    df = quotes.copy()
    for col in ("strike", "last_price"):
        df[col] = df[col].astype(np.float64)
    df = validate_quotes(df)

    yield ("Solving implied volatility", 55)
    df = calculate_IV(df, spot, days_forward, risk_free_rate, solver)

    if len(df) < 5:
        raise ValueError(
            f"Only {len(df)} options survived IV solving (need at least 5). "
            "Check that spot price and days_forward match the option chain data."
        )

    yield ("Smoothing IV curve", 70)
    denoised_iv = fit_bspline_IV(df, bspline)

    yield ("Extracting price distribution", 80)
    strikes, pdf = extract_pdf(denoised_iv, spot, days_forward, risk_free_rate)

    if kernel_smooth:
        yield ("Smoothing distribution (KDE)", 85)
        strikes, pdf = fit_kde(strikes, pdf)

    yield ("Computing CDF", 90)
    cdf = compute_cdf(strikes, pdf)

    yield pd.DataFrame({"Price": strikes, "PDF": pdf, "CDF": cdf})


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
    """Averaged pipeline with progress yields."""
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
        raise ValueError(
            f"Only {len(iv_df)} strikes with valid IV (need at least 5)."
        )

    yield ("Smoothing IV curve", 70)
    denoised_iv = fit_bspline_IV(iv_df, bspline)

    yield ("Extracting price distribution", 80)
    strikes, pdf = extract_pdf(denoised_iv, spot, days_forward, risk_free_rate)

    if kernel_smooth:
        yield ("Smoothing distribution (KDE)", 85)
        strikes, pdf = fit_kde(strikes, pdf)

    yield ("Computing CDF", 90)
    cdf = compute_cdf(strikes, pdf)

    yield pd.DataFrame({"Price": strikes, "PDF": pdf, "CDF": cdf})
