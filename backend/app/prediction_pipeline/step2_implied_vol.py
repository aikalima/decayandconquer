"""Implied volatility solvers.

We solve for sigma such that Black-Scholes call price equals the observed
market price. Two methods:
- **Brent** root-finding (robust, bracketed)
- **Newton** iteration (fast, needs decent initial guess)

Both return np.nan on convergence failure or no-arbitrage violations.
"""

from __future__ import annotations
import logging
from typing import Literal
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from .black_scholes import call_value, call_vega

logger = logging.getLogger(__name__)

IV_LO, IV_HI = 1e-6, 5.0


def bs_iv_newton(
    price: float,
    S: float,
    K: float,
    t: float,
    r: float,
    precision: float = 1e-4,
    max_iter: int = 200,
) -> float:
    """Implied volatility via Newton-Raphson iteration.

    Returns np.nan if convergence fails.
    """
    if t <= 0:
        return np.nan

    # Dynamic initial guess: lower for ATM, higher for OTM
    iv = 0.2 if abs(S - K) < 0.1 * S else 0.5

    for _ in range(max_iter):
        P = call_value(S, K, iv, t, r)
        diff = price - P

        if abs(diff) < precision:
            return iv

        vega = call_vega(S, K, iv, t, r)
        if abs(vega) < 1e-10:
            return np.nan

        iv += diff / vega
        # Clamp to valid range instead of hard-failing
        iv = np.clip(iv, IV_LO, IV_HI)

    return np.nan


def bs_iv_brent(price: float, S: float, K: float, t: float, r: float) -> float:
    """Implied volatility via Brent's bracketed root-finding.

    Searches in [IV_LO, IV_HI]. Returns np.nan if no root exists.
    """
    if t <= 0:
        return np.nan
    try:
        return brentq(lambda iv: call_value(S, K, iv, t, r) - price, IV_LO, IV_HI)
    except ValueError:
        return np.nan


SOLVERS = {
    "brent": bs_iv_brent,
    "newton": bs_iv_newton,
}


def calculate_IV(
    options_data: pd.DataFrame,
    spot: float,
    days_forward: int,
    risk_free_rate: float,
    solver: Literal["newton", "brent"] = "brent",
) -> pd.DataFrame:
    """Compute implied volatility for each option row.

    Rows where IV cannot be determined are dropped (with a log warning).
    """
    if solver not in SOLVERS:
        raise ValueError(f"Unknown solver '{solver}'. Choose from: {list(SOLVERS)}")

    iv_fn = SOLVERS[solver]
    years_forward = days_forward / 365

    df = options_data.copy()
    df["iv"] = df.apply(
        lambda row: iv_fn(row["last_price"], spot, row["strike"], years_forward, risk_free_rate),
        axis=1,
    )

    n_failed = df["iv"].isna().sum()
    if n_failed:
        logger.warning("calculate_IV: %d / %d rows failed IV solve (dropped)", n_failed, len(df))

    return df.dropna(subset=["iv"])


def calculate_IV_averaged(
    chains_by_date: dict[str, pd.DataFrame],
    spot: float,
    days_forward_by_date: dict[str, int],
    risk_free_rate: float,
    solver: Literal["newton", "brent"] = "brent",
) -> pd.DataFrame:
    """Compute IV for each date's chain, then average IV across dates per strike.

    Args:
        chains_by_date: {trade_date_str: DataFrame[strike, last_price, bid, ask]}
        spot: reference spot price (typically from the last date in the range)
        days_forward_by_date: {trade_date_str: days_to_expiry_from_that_date}
        risk_free_rate: annualised risk-free rate
        solver: IV solver method

    Returns:
        DataFrame with columns [strike, iv] — mean IV per strike across all dates.
        Same format as calculate_IV output, ready for fit_bspline_IV.
    """
    all_ivs = []

    for trade_date, chain in chains_by_date.items():
        days_fwd = days_forward_by_date[trade_date]
        if days_fwd <= 0:
            continue
        try:
            with_iv = calculate_IV(chain, spot, days_fwd, risk_free_rate, solver)
            if len(with_iv) > 0:
                all_ivs.append(with_iv[["strike", "iv"]])
        except Exception as e:
            logger.warning("IV solve failed for %s: %s", trade_date, e)

    if not all_ivs:
        raise ValueError("No IV data could be computed for any date in the range")

    combined = pd.concat(all_ivs, ignore_index=True)
    averaged = combined.groupby("strike", as_index=False)["iv"].mean()
    averaged = averaged.sort_values("strike").reset_index(drop=True)

    logger.info(
        "IV averaged: %d dates, %d total observations -> %d unique strikes",
        len(all_ivs), len(combined), len(averaged),
    )

    return averaged
