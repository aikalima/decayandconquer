"""Optional KDE smoothing of the final PDF.

Applies kernel density estimation to the Breeden-Litzenberger PDF
to produce a smoother, normalized density.
"""

from __future__ import annotations
import numpy as np
from scipy.stats import gaussian_kde


def fit_kde(pdf_point_arrays: tuple) -> tuple:
    """
    Fits a Kernel Density Estimation (KDE) to the given implied probability density function (PDF).

    Args:
        pdf_point_arrays (tuple): A tuple containing:
            - A numpy array of price values
            - A numpy array of PDF values

    Returns:
        tuple: (prices, fitted_pdf), where:
            - prices: The original price array
            - fitted_pdf: The KDE-fitted probability density values
    """
    prices, pdf_values = pdf_point_arrays

    pdf_values /= np.trapezoid(pdf_values, prices)

    kde = gaussian_kde(prices, weights=pdf_values)
    fitted_pdf = kde.pdf(prices)

    return (prices, fitted_pdf)
