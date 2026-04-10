"""B-spline smoothing of the implied volatility smile.

Fits a B-spline to raw IV observations to denoise the vol smile, then
resamples onto a dense strike grid for use in repricing.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy import interpolate


@dataclass(frozen=True)
class BSplineParams:
    """Controls the B-spline fit.

    k:      spline degree (3 = cubic)
    smooth: regularisation weight passed to splrep (higher = smoother)
    dx:     spacing between dense grid points in strike units
    """
    k: int = 3
    smooth: float = 10.0
    dx: float = 0.1


def fit_bspline_IV(
    options_data: pd.DataFrame, params: BSplineParams = BSplineParams()
) -> tuple[np.ndarray, np.ndarray]:
    """Fit a B-spline to the IV smile and resample on a dense grid.

    Returns (strikes, smoothed_iv) as parallel arrays.
    """
    x = options_data["strike"].values
    y = options_data["iv"].values

    tck = interpolate.splrep(x, y, s=params.smooth, k=params.k)

    n_points = int((x.max() - x.min()) / params.dx)
    x_dense = np.linspace(x.min(), x.max(), n_points)
    y_smooth = interpolate.BSpline(*tck)(x_dense)

    return x_dense, y_smooth
