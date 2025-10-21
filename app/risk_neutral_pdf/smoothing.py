"""Smile and PDF smoothing utilities.

- **B-spline** smoothing for IV vs. strike
- Optional **KDE** smoothing for the final PDF
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy import interpolate
from scipy.stats import gaussian_kde


@dataclass(frozen=True)
class BSplineParams:
    """Controls the smoothness and sampling of the IV spline."""
    k: int = 3
    smooth: float = 10.0
    dx: float = 0.1


def smooth_iv_bspline(strikes: np.ndarray, iv: np.ndarray, p: BSplineParams) -> tuple[np.ndarray, np.ndarray]:
    """Fit a cubic B-spline to (strike, iv) and sample on a dense grid."""
    tck = interpolate.splrep(strikes, iv, s=p.smooth, k=p.k)
    x_min, x_max = float(np.min(strikes)), float(np.max(strikes))
    n = max(10, int((x_max - x_min) / p.dx))
    x_new = np.linspace(x_min, x_max, n)
    y_fit = interpolate.BSpline(*tck)(x_new)
    return x_new, y_fit


def kde_pdf(x: np.ndarray, y_pdf: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Optional kernel smoothing of an already estimated PDF.

    The input y is treated as a weighting function over x; we renormalize and
    return the KDE-evaluated density on the same support.
    """
    area = np.trapz(y_pdf, x)
    if area > 0:
        y_pdf = y_pdf / area
    kde = gaussian_kde(x, weights=y_pdf)
    return x, kde.pdf(x)