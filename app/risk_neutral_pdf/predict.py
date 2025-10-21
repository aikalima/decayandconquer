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
from .prep import validate_quotes, extrapolate_calls
from .black_scholes import MarketParams, call_price_bs
from .implied_volatility import iv_brent, iv_newton
from .smoothing import smooth_iv_bspline, BSplineParams, kde_pdf
from .probability_dist_function import breeden_litzenberger_pdf
from scipy.integrate import simpson


def calculate_cdf(
    pdf_point_arrays: tuple[np.ndarray, np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
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


def estimate_pdf_from_calls(
    quotes: pd.DataFrame,
    spot: float,
    days_forward: int,
    risk_free_rate: float,
    solver: str = "brent",
    bspline: BSplineParams = BSplineParams(),
    kernel_smooth: bool = False,
) -> pd.DataFrame:
    """Estimate the risk-neutral terminal price PDF from call quotes.

    Parameters
    ----------
    quotes : DataFrame
        Must contain at least columns: `strike`, `last_price`. Additional columns
        (e.g., `bid`, `ask`) are ignored by the core pipeline but can be used
        upstream to compute mid prices.
    spot : float
        Current underlying price `S`.
    days_forward : int
        Days until the forecast horizon / option expiry; converted to `T` years.
    risk_free_rate : float
        Annualized continuously-compounded risk-free rate `r`.
    solver : {"brent", "newton"}
        IV inversion method. Brent is robust default; Newton is faster when close
        to the solution.
    bspline : BSplineParams
        Controls the IV smile smoothing and grid density.
    kernel_smooth : bool
        If True, apply a lightweight KDE smoothing pass to the final PDF.

    Returns
    -------
    DataFrame with columns:
    - `price`: the strike/price grid (same axis as K)
    - `pdf`:   the estimated risk-neutral density on that grid
    """
    T = days_forward / 365.0
    mkt = MarketParams(r=risk_free_rate, T=T)

    q = validate_quotes(quotes)
    q_ext, kmin, kmax = extrapolate_calls(q, spot)

    # Solve IV per strike
    solve = iv_brent if solver == "brent" else iv_newton
    q_ext["iv"] = q_ext.apply(lambda row: solve(row.last_price, spot, row.strike, mkt), axis=1)
    q_ext = q_ext.dropna(subset=["iv"])  # remove failed solves

    # Smile smoothing and repricing
    K_dense, iv_smooth = smooth_iv_bspline(q_ext["strike"].to_numpy(), q_ext["iv"].to_numpy(), bspline)
    C_dense = call_price_bs(spot, K_dense, iv_smooth, mkt)

    # Breeden–Litzenberger to PDF
    pdf_dense = breeden_litzenberger_pdf(K_dense, C_dense, risk_free_rate, T, renormalize=False)

    # Crop back to original strike band
    mask = (K_dense >= kmin) & (K_dense <= kmax)
    K_out, pdf_out = K_dense[mask], pdf_dense[mask]

    pdf_point_arrays = (K_out, pdf_out)
    # Optional kernel smoothing
    if kernel_smooth:
        pdf_point_arrays = kde_pdf(K_out, pdf_out)

    cdf_point_arrays = calculate_cdf(pdf_point_arrays)
    
    priceP, densityP = pdf_point_arrays
    priceC, densityC = cdf_point_arrays

    #Convert results to DataFrame
    result_df = pd.DataFrame({"Price": priceP, "PDF": densityP, "CDF": densityC})
    
    return result_df