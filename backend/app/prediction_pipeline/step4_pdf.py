"""Probability density extraction via Breeden-Litzenberger.

The risk-neutral density over terminal prices is recovered from the second
derivative of the call price curve with respect to strike:

    PDF(K) = e^(rT) * d²C/dK²

We compute this via finite differences on the dense, smooth call-price curve
produced by the B-spline IV step, then normalise to ensure the PDF integrates
to 1.
"""

from __future__ import annotations
import numpy as np
from scipy.integrate import cumulative_trapezoid
from .black_scholes import call_value


def extract_pdf(
    denoised_iv: tuple[np.ndarray, np.ndarray],
    spot: float,
    days_forward: int,
    risk_free_rate: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Breeden-Litzenberger PDF extraction.

    Args:
        denoised_iv: (strikes, smoothed_iv) from B-spline fit
        spot: current price of the underlying
        days_forward: days to expiration
        risk_free_rate: annualised risk-free rate

    Returns:
        (strikes, pdf) where pdf integrates to 1.0 over the strike domain.
    """
    strikes, iv_smooth = denoised_iv
    years = days_forward / 365

    # Reprice calls on the dense grid using smoothed IV
    call_prices = call_value(spot, strikes, iv_smooth, years, risk_free_rate)

    # Breeden-Litzenberger: PDF = e^(rT) * d²C/dK²
    d2C_dK2 = np.gradient(np.gradient(call_prices, strikes), strikes)
    pdf = np.exp(risk_free_rate * years) * d2C_dK2

    # Enforce non-negativity (numerical noise can produce small negatives)
    pdf = np.maximum(pdf, 0.0)

    # Normalise so the PDF integrates to 1
    area = np.trapezoid(pdf, strikes)
    if area > 0:
        pdf /= area

    return strikes, pdf


def compute_cdf(
    strikes: np.ndarray, pdf: np.ndarray
) -> np.ndarray:
    """Cumulative distribution from a normalised PDF.

    Uses cumulative trapezoidal integration. The result starts near 0
    and approaches 1 at the upper end of the strike domain.
    """
    cdf = cumulative_trapezoid(pdf, strikes, initial=0.0)
    # Clamp to [0, 1] to absorb any floating-point drift
    return np.clip(cdf, 0.0, 1.0)


def crop_to_range(
    strikes: np.ndarray, pdf: np.ndarray, cdf: np.ndarray,
    lo: float, hi: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Crop all arrays to the original observed strike range [lo, hi]."""
    mask = (strikes >= lo) & (strikes <= hi)
    return strikes[mask], pdf[mask], cdf[mask]
