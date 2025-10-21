"""Probability density extraction via Breeden–Litzenberger.

The result is a **risk-neutral** density over terminal prices (expressed on the
strike axis). We compute finite differences over a dense, smooth call-price
curve and enforce non-negativity with optional renormalization.
"""

from __future__ import annotations
import numpy as np
from typing import Tuple
from scipy.integrate import simpson
from .black_scholes import call_value

def create_pdf_point_arrays(
    denoised_iv: tuple, spot: float, days_forward: int, risk_free_rate: float
) -> Tuple[np.ndarray, np.ndarray]:
    """Create two arrays containing x- and y-axis values representing a calculated
    price PDF

    Args:
        denoised_iv: (x,y) observations of the denoised IV
        spot: the current price of the security
        days_forward: the number of days in the future to estimate the
            price probability density at
        risk_free_rate: the current annual risk free interest rate, nominal terms

    Returns:
        a tuple containing x-axis values (index 0) and y-axis values (index 1)
    """

    # extract the x and y vectors from the denoised IV observations
    x_IV = denoised_iv[0]
    y_IV = denoised_iv[1]

    # convert IV-space to price-space
    # re-values call options using the BS formula, taking in as inputs S, domain, IV, and time to expiry
    years_forward = days_forward / 365
    interpolated = call_value(spot, x_IV, y_IV, years_forward, risk_free_rate)
    first_derivative_discrete = np.gradient(interpolated, x_IV)
    second_derivative_discrete = np.gradient(first_derivative_discrete, x_IV)

    # apply coefficient to reflect the time value of money
    pdf = np.exp(risk_free_rate * years_forward) * second_derivative_discrete

    # ensure non-negative pdf values (may occur for far OOM options)
    pdf = np.maximum(pdf, 0)  # Set all negative values to 0

    return (x_IV, pdf)

def calculate_cdf(
    pdf_point_arrays: Tuple[np.ndarray, np.ndarray],
) -> Tuple[np.ndarray, np.ndarray]:
    """Returns the cumulative probability at each price. Takes as input the array
    of pdf and array of prices, and calculates the cumulative probability as the
    numerical integral over the pdf function.

    For simplicity, it assumes that the CDF at the starting price
        = 1 - 0.5*(total area of the pdf)
    and therefore it adds 0.5*(total area of the pdf) to every cdf for the
    remainder of the domain

    Args:
        pdf_point_arrays: a tuple containing arrays representing a PDF

    Returns:
        A tuple containing the price domain and the point values of the CDF
    """
    x_array, pdf_array = pdf_point_arrays
    cdf = []
    n = len(x_array)

    total_area = simpson(y=pdf_array[0:n], x=x_array)
    remaining_area = 1 - total_area

    for i in range(n):
        if i == 0:
            integral = 0.0 + remaining_area / 2
        else:
            integral = (
                simpson(y=pdf_array[i - 1 : i + 1], x=x_array[i - 1 : i + 1]) + cdf[-1]
            )
        cdf.append(integral)

    return (x_array, cdf)


def crop_pdf(
    pdf: Tuple[np.ndarray, np.ndarray], min_strike: float, max_strike: float
) -> Tuple[np.ndarray, np.ndarray]:
    """Crop the PDF to the range of the original options data"""
    l, r = 0, len(pdf[0]) - 1
    while pdf[0][l] < min_strike:
        l += 1
    while pdf[0][r] > max_strike:
        r -= 1
    return pdf[0][l : r + 1], pdf[1][l : r + 1]
