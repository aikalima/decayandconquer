"""Black-Scholes primitives.

Provides the closed-form European call price and its Vega (sensitivity to
volatility). Used here not as a pricing model but as a mapping between
observed call prices and implied volatility.
"""

from __future__ import annotations
import numpy as np
from scipy.stats import norm


def call_value(S, K, sigma, t, r):
    """European call price under Black-Scholes.

    Handles vectorised inputs (K and sigma may be arrays).
    """
    with np.errstate(divide="ignore"):
        d1 = (np.log(S / K) + (r + sigma**2 / 2) * t) / (sigma * np.sqrt(t))
        d2 = d1 - sigma * np.sqrt(t)
    return norm.cdf(d1) * S - norm.cdf(d2) * K * np.exp(-r * t)


def call_vega(S, K, sigma, t, r):
    """Vega: dC/d(sigma). Used by Newton-Raphson IV solver."""
    with np.errstate(divide="ignore"):
        d1 = (np.log(S / K) + (r + sigma**2 / 2) * t) / (sigma * np.sqrt(t))
    return S * norm.pdf(d1) * np.sqrt(t)


def call_delta(S, K, sigma, t, r):
    """Delta: dC/dS — probability call finishes ITM (risk-neutral)."""
    with np.errstate(divide="ignore"):
        d1 = (np.log(S / K) + (r + sigma**2 / 2) * t) / (sigma * np.sqrt(t))
    return norm.cdf(d1)


def call_gamma(S, K, sigma, t, r):
    """Gamma: d²C/dS² — rate of change of delta."""
    with np.errstate(divide="ignore"):
        d1 = (np.log(S / K) + (r + sigma**2 / 2) * t) / (sigma * np.sqrt(t))
    return norm.pdf(d1) / (S * sigma * np.sqrt(t))


def call_theta(S, K, sigma, t, r):
    """Theta: dC/dt — annualized time decay (negative = value lost)."""
    with np.errstate(divide="ignore"):
        d1 = (np.log(S / K) + (r + sigma**2 / 2) * t) / (sigma * np.sqrt(t))
        d2 = d1 - sigma * np.sqrt(t)
    return (
        -(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(t))
        - r * K * np.exp(-r * t) * norm.cdf(d2)
    )
