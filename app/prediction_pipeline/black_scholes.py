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

def call_vega(S, K, sigma, t, r):
    # TODO: refactor this function (style)
    with np.errstate(divide="ignore"):
        d1 = np.divide(1, sigma * np.sqrt(t)) * (np.log(S / K) + (r + sigma**2 / 2) * t)
    return np.multiply(S, norm.pdf(d1)) * np.sqrt(t)

def call_value(S, K, sigma, t, r):
    # TODO: refactor this function (style)
    # use np.multiply and divide to handle divide-by-zero
    with np.errstate(divide="ignore"):
        d1 = np.divide(1, sigma * np.sqrt(t)) * (np.log(S / K) + (r + sigma**2 / 2) * t)
        d2 = d1 - sigma * np.sqrt(t)
    return np.multiply(norm.cdf(d1), S) - np.multiply(norm.cdf(d2), K * np.exp(-r * t))
