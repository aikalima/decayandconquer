"""Probability density extraction via Breeden–Litzenberger.

The result is a **risk-neutral** density over terminal prices (expressed on the
strike axis). We compute finite differences over a dense, smooth call-price
curve and enforce non-negativity with optional renormalization.
"""

from __future__ import annotations
import numpy as np


def breeden_litzenberger_pdf(K: np.ndarray, C_of_K: np.ndarray, r: float, T: float, renormalize: bool = True) -> np.ndarray:
    """Compute f(K) = exp(rT) * d^2 C / dK^2 via finite differences.

    Parameters
    ----------
    K : array
        Strike grid (monotone increasing).
    C_of_K : array
        Call prices on K.
    r : float
        Risk-free rate (annualized, cont. comp.).
    T : float
        Time to expiry in years.
    renormalize : bool
        If True, rescale to integrate to 1 over K.
    """
    d1 = np.gradient(C_of_K, K)
    d2 = np.gradient(d1, K)
    pdf = np.exp(r * T) * d2
    pdf = np.clip(pdf, 0.0, None)
    if renormalize:
        area = np.trapz(pdf, K)
        if area > 0:
            pdf = pdf / area
    return pdf