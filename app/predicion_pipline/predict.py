"""Top-level pipeline to estimate a risk-neutral price PDF from call quotes.

This module orchestrates the steps:
1) validate & sort quotes
2) extrapolate strike domain
3) solve implied vol per strike (Brent default)
4) smooth the smile (B-spline)
5) reprice over dense strike grid
6) apply Breeden–Litzenberger to recover the PDF
7) crop to original strike band and (optionally) smooth the PDF with KDE

The result is returned as a tidy DataFrame with columns `price` and `pdf`.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from .prep import extrapolate_call_prices, calculate_mid_price
from .implied_volatility import calculate_IV
from .smoothing import fit_bspline_IV, fit_kde, BSplineParams
from .probability_dist_function import create_pdf_point_arrays, calculate_cdf, crop_pdf

def predict_price(
    quotes: pd.DataFrame,
    spot: float,
    days_forward: int,
    risk_free_rate: float,
    solver: str = "brent",
    bspline: BSplineParams = BSplineParams(),
    kernel_smooth: bool = False,
) -> pd.DataFrame:
    
    fit_kernel_pdf = kernel_smooth 
    solver_method = solver

    options_data = quotes

    options_data["strike"] = options_data["strike"].astype(np.float64)
    options_data["last_price"] = options_data["last_price"].astype(np.float64)
    options_data["bid"] = options_data["bid"].astype(np.float64)
    options_data["ask"] = options_data["ask"].astype(np.float64)

    # calculate_pdf START
    options_data, min_strike, max_strike = extrapolate_call_prices(
        options_data, spot
    )

    options_data = calculate_mid_price(options_data)

    options_data = calculate_IV(
        options_data, spot, days_forward, risk_free_rate, solver_method
    )

    denoised_iv = fit_bspline_IV(options_data, bspline)

    pdf = create_pdf_point_arrays(
        denoised_iv, spot, days_forward, risk_free_rate
    )

    cropped_pdf = crop_pdf(pdf, min_strike, max_strike)
    pdf_point_arrays = cropped_pdf
    # calculate_pdf END

    # Fit KDE to normalize PDF if desired
    if fit_kernel_pdf:
        pdf_point_arrays = fit_kde(
            pdf_point_arrays
        )  # Ensure this returns a tuple of arrays

    cdf_point_arrays = calculate_cdf(pdf_point_arrays)
    priceP, densityP = pdf_point_arrays
    priceC, densityC = cdf_point_arrays 

    #Convert results to DataFrame
    df = pd.DataFrame({"Price": priceP, "PDF": densityP, "CDF": densityC})
    return df
