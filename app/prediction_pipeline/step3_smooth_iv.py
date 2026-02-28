"""B-spline smoothing of the implied volatility smile.

Fits a B-spline to the raw IV observations to denoise the vol smile,
then samples it over a dense strike grid for use in repricing.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy import interpolate


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

    tck = interpolate.splrep(x, y, s=bspline.smooth, k=bspline.k)

    dx = bspline.dx
    domain = int((max(x) - min(x)) / dx)

    x_new = np.linspace(min(x), max(x), domain)
    y_fit = interpolate.BSpline(*tck)(x_new)

    return (x_new, y_fit)
