"""Smile and PDF smoothing utilities.

- **B-spline** smoothing for IV vs. strike
- Optional **KDE** smoothing for the final PDF
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy import interpolate
from scipy.stats import gaussian_kde


@dataclass(frozen=True)
class BSplineParams:
    """Controls the smoothness and sampling of the IV spline."""
    k: int = 3
    smooth: float = 10.0
    dx: float = 0.1

def fit_bspline_IV(options_data: pd.DataFrame, bspline: BSplineParams) -> pd.DataFrame:
    """Fit a bspline function on the IV observations, in effect denoising the IV.
        From this smoothed IV function, generate (x,y) coordinates
        representing observations of the denoised IV

    Args:
        options_data: a DataFrame containing options price data with
            cols ['strike', 'last_price', 'iv']
        bspline: a BSplineParams object with bspline parameters

    Returns:
        a tuple containing x-axis values (index 0) and y-axis values (index 1)
        'x' represents the price
        'y' represents the value of the IV
    """
    x = options_data["strike"]
    y = options_data["iv"]

    # fit the bspline using scipy.interpolate.splrep, with k=3
    """
    Bspline Parameters:
        t = the vector of knots
        c = the B-spline coefficients
        k = the degree of the spline
    """
    tck = interpolate.splrep(x, y, s=bspline.smooth, k=bspline.k)

    dx = bspline.dx
    domain = int((max(x) - min(x)) / dx)

    # compute (x,y) observations of the denoised IV from the fitted IV function
    x_new = np.linspace(min(x), max(x), domain)
    y_fit = interpolate.BSpline(*tck)(x_new)

    return (x_new, y_fit)

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

    # Unpack tuple
    prices, pdf_values = pdf_point_arrays

    # Normalize PDF to ensure it integrates to 1
    pdf_values /= np.trapz(pdf_values, prices)  # Use trapezoidal rule for normalization

    # Fit KDE using price points weighted by the normalized PDF
    kde = gaussian_kde(prices, weights=pdf_values)

    # Generate KDE-fitted PDF values
    fitted_pdf = kde.pdf(prices)

    return (prices, fitted_pdf)
