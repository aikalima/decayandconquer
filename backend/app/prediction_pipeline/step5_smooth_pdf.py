"""Optional KDE smoothing of the final PDF.

Applies Gaussian kernel density estimation to produce a smoother density
while preserving normalisation (integral = 1).
"""

from __future__ import annotations
import numpy as np
from scipy.stats import gaussian_kde


def fit_kde(
    strikes: np.ndarray, pdf: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Smooth the PDF using weighted Gaussian KDE.

    The input PDF values are used as weights for the kernel density estimate.
    The result is re-normalised to integrate to 1 over the strike domain.

    Returns (strikes, smoothed_pdf).
    """
    kde = gaussian_kde(strikes, weights=pdf)
    smoothed = kde.pdf(strikes)

    # Re-normalise after KDE to guarantee unit integral
    area = np.trapezoid(smoothed, strikes)
    if area > 0:
        smoothed /= area

    return strikes, smoothed
