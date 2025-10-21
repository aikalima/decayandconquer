"""Black–Scholes primitives.

This module implements the Black–Scholes closed-form for European calls and its
Vega. In this project, Black–Scholes is not used as a *pricing model* per se,
so much as a **mapping** between observed call prices and their **implied
volatility** (IV). We invert the formula to recover an IV smile that is then
smoothed and used for consistent repricing across strikes.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.stats import norm


@dataclass(frozen=True)
class MarketParams:
    """Market parameters for Black–Scholes.

    Attributes
    ----------
    r : float
        Annualized continuously-compounded risk-free rate.
    T : float
        Time to expiry in **years**.
    """

    r: float
    T: float


def call_price_bs(S: float, K: float | np.ndarray, sigma: float | np.ndarray, mkt: MarketParams) -> np.ndarray:
    """Black–Scholes European call price.

    If `T == 0`, returns intrinsic `max(S-K, 0)`.
    """
    if mkt.T <= 0:
        return np.maximum(S - K, 0.0)

    sigma = np.asarray(sigma, dtype=float)
    K = np.asarray(K, dtype=float)

    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(S / K) + (mkt.r + 0.5 * sigma**2) * mkt.T) / (sigma * np.sqrt(mkt.T))
        d2 = d1 - sigma * np.sqrt(mkt.T)
    return S * norm.cdf(d1) - K * np.exp(-mkt.r * mkt.T) * norm.cdf(d2)


def call_vega_bs(S: float, K: float, sigma: float, mkt: MarketParams) -> float:
    """Sensitivity of Black–Scholes call price to volatility (∂C/∂σ)."""
    if sigma <= 0 or mkt.T <= 0:
        return 0.0
    d1 = (np.log(S / K) + (mkt.r + 0.5 * sigma**2) * mkt.T) / (sigma * np.sqrt(mkt.T))
    return float(S * norm.pdf(d1) * np.sqrt(mkt.T))