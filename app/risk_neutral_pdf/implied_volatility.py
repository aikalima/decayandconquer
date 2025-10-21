"""Implied volatility solvers.

We solve for `σ` such that Black–Scholes call price equals the observed market
price. Two methods are provided:
- **Brent** root-finding (robust, bracketed)
- **Newton** iteration (fast near the solution, but needs a decent initial guess)

Both return `np.nan` if they fail to converge or violate basic no-arbitrage
bounds.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import numpy as np
from scipy.optimize import brentq
from .black_scholes import call_price_bs, call_vega_bs, MarketParams

IV_LO, IV_HI = 1e-6, 5.0


@dataclass(frozen=True)
class IVBounds:
    lo: float = IV_LO
    hi: float = IV_HI


def _no_arbitrage_bounds_ok(price: float, S: float, K: float, mkt: MarketParams) -> bool:
    intrinsic = max(S - K * np.exp(-mkt.r * mkt.T), 0.0)
    return intrinsic <= price <= S


def iv_newton(
    price: float,
    S: float,
    K: float,
    mkt: MarketParams,
    tol: float = 1e-4,
    guess: float | None = None,
    max_iter: int = 100,
) -> float | np.nan:
    """Newton–Raphson implied vol.

    Fast when close to the solution; returns NaN on poor curvature (small vega)
    or when updates leave [IV_LO, IV_HI].
    """
    if mkt.T <= 0 or not _no_arbitrage_bounds_ok(price, S, K, mkt):
        return np.nan

    sigma = guess if guess is not None else (0.2 if abs(S - K) < 0.1 * S else 0.5)
    for _ in range(max_iter):
        c = call_price_bs(S, K, sigma, mkt)
        diff = price - c
        if abs(diff) < tol:
            return float(sigma)
        vega = call_vega_bs(S, K, sigma, mkt)
        if vega <= 1e-8:
            return np.nan
        sigma += diff / vega
        if not (IV_LO <= sigma <= IV_HI):
            return np.nan
    return np.nan


def iv_brent(
    price: float,
    S: float,
    K: float,
    mkt: MarketParams,
    bounds: IVBounds = IVBounds(),
) -> float | np.nan:
    """Brent root-finding implied vol (robust default)."""
    if mkt.T <= 0 or not _no_arbitrage_bounds_ok(price, S, K, mkt):
        return np.nan
    try:
        f = lambda s: call_price_bs(S, K, s, mkt) - price
        return float(brentq(f, bounds.lo, bounds.hi))
    except ValueError:
        return np.nan