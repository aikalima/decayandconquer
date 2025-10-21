# -------------------------------
# app/risk_neutral_pdf/__init__.py
# -------------------------------

"""risk_neutral_pdf

Tools to estimate a risk-neutral price PDF from option quotes via:
- Black–Scholes implied volatility inversion
- Smile smoothing (B-splines)
- Breeden–Litzenberger density extraction

Public API:
- estimate_pdf_from_calls (predict)
- MarketParams, call_price_bs (black_scholes)
"""

from .predict import estimate_pdf_from_calls
from .black_scholes import MarketParams, call_price_bs

__all__ = [
    "estimate_pdf_from_calls",
    "MarketParams",
    "call_price_bs",
]

# -------------------------------
# app/risk_neutral_pdf/black_scholes.py
# -------------------------------

"""Black–Scholes primitives.

This module implements the Black–Scholes closed-form for European calls and its
Vega. In this project, Black–Scholes is not used as a *pricing model* per se,
so much as a **mapping** between observed call prices and their **implied
volatility** (IV). We invert the formula to recover an IV smile that is then
smoothed and used for consistent repricing across strikes.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.stats import norm


@dataclass(frozen=True)
class MarketParams:
    """Market parameters for Black–Scholes.

    Attributes
    ----------
    r : float
        Annualized continuously-compounded risk-free rate.
    T : float
        Time to expiry in **years**.
    """

    r: float
    T: float


def call_price_bs(S: float, K: float | np.ndarray, sigma: float | np.ndarray, mkt: MarketParams) -> np.ndarray:
    """Black–Scholes European call price.

    If `T == 0`, returns intrinsic `max(S-K, 0)`.
    """
    if mkt.T <= 0:
        return np.maximum(S - K, 0.0)

    sigma = np.asarray(sigma, dtype=float)
    K = np.asarray(K, dtype=float)

    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(S / K) + (mkt.r + 0.5 * sigma**2) * mkt.T) / (sigma * np.sqrt(mkt.T))
        d2 = d1 - sigma * np.sqrt(mkt.T)
    return S * norm.cdf(d1) - K * np.exp(-mkt.r * mkt.T) * norm.cdf(d2)


def call_vega_bs(S: float, K: float, sigma: float, mkt: MarketParams) -> float:
    """Sensitivity of Black–Scholes call price to volatility (∂C/∂σ)."""
    if sigma <= 0 or mkt.T <= 0:
        return 0.0
    d1 = (np.log(S / K) + (mkt.r + 0.5 * sigma**2) * mkt.T) / (sigma * np.sqrt(mkt.T))
    return float(S * norm.pdf(d1) * np.sqrt(mkt.T))

# -------------------------------
# app/risk_neutral_pdf/implied_volatility.py
# -------------------------------

"""Implied volatility solvers.

We solve for `σ` such that Black–Scholes call price equals the observed market
price. Two methods are provided:
- **Brent** root-finding (robust, bracketed)
- **Newton** iteration (fast near the solution, but needs a decent initial guess)

Both return `np.nan` if they fail to converge or violate basic no-arbitrage
bounds.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import numpy as np
from scipy.optimize import brentq
from .black_scholes import call_price_bs, call_vega_bs, MarketParams

IV_LO, IV_HI = 1e-6, 5.0


@dataclass(frozen=True)
class IVBounds:
    lo: float = IV_LO
    hi: float = IV_HI


def _no_arbitrage_bounds_ok(price: float, S: float, K: float, mkt: MarketParams) -> bool:
    intrinsic = max(S - K * np.exp(-mkt.r * mkt.T), 0.0)
    return intrinsic <= price <= S


def iv_newton(
    price: float,
    S: float,
    K: float,
    mkt: MarketParams,
    tol: float = 1e-4,
    guess: float | None = None,
    max_iter: int = 100,
) -> float | np.nan:
    """Newton–Raphson implied vol.

    Fast when close to the solution; returns NaN on poor curvature (small vega)
    or when updates leave [IV_LO, IV_HI].
    """
    if mkt.T <= 0 or not _no_arbitrage_bounds_ok(price, S, K, mkt):
        return np.nan

    sigma = guess if guess is not None else (0.2 if abs(S - K) < 0.1 * S else 0.5)
    for _ in range(max_iter):
        c = call_price_bs(S, K, sigma, mkt)
        diff = price - c
        if abs(diff) < tol:
            return float(sigma)
        vega = call_vega_bs(S, K, sigma, mkt)
        if vega <= 1e-8:
            return np.nan
        sigma += diff / vega
        if not (IV_LO <= sigma <= IV_HI):
            return np.nan
    return np.nan


def iv_brent(
    price: float,
    S: float,
    K: float,
    mkt: MarketParams,
    bounds: IVBounds = IVBounds(),
) -> float | np.nan:
    """Brent root-finding implied vol (robust default)."""
    if mkt.T <= 0 or not _no_arbitrage_bounds_ok(price, S, K, mkt):
        return np.nan
    try:
        f = lambda s: call_price_bs(S, K, s, mkt) - price
        return float(brentq(f, bounds.lo, bounds.hi))
    except ValueError:
        return np.nan

# -------------------------------
# app/risk_neutral_pdf/smoothing.py
# -------------------------------

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

# -------------------------------
# app/risk_neutral_pdf/probability_dist_function.py
# -------------------------------

"""Probability density extraction via Breeden–Litzenberger.

The result is a **risk-neutral** density over terminal prices (expressed on the
strike axis). We compute finite differences over a dense, smooth call-price
curve and enforce non-negativity with optional renormalization.
"""

from __future__ import annotations
import numpy as np


def breeden_litzenberger_pdf(K: np.ndarray, C_of_K: np.ndarray, r: float, T: float, renormalize: bool = True) -> np.ndarray:
    """Compute f(K) = exp(rT) * d^2 C / dK^2 via finite differences.

    Parameters
    ----------
    K : array
        Strike grid (monotone increasing).
    C_of_K : array
        Call prices on K.
    r : float
        Risk-free rate (annualized, cont. comp.).
    T : float
        Time to expiry in years.
    renormalize : bool
        If True, rescale to integrate to 1 over K.
    """
    d1 = np.gradient(C_of_K, K)
    d2 = np.gradient(d1, K)
    pdf = np.exp(r * T) * d2
    pdf = np.clip(pdf, 0.0, None)
    if renormalize:
        area = np.trapz(pdf, K)
        if area > 0:
            pdf = pdf / area
    return pdf

# -------------------------------
# app/risk_neutral_pdf/prep.py
# -------------------------------

"""Data loading, validation, and extrapolation helpers.

The extrapolation step pads the domain of strikes to reduce boundary effects in
finite differencing. Below the minimum strike we set `C(K)=max(S-K,0)`;
above the maximum we set `C(K)=0`. This keeps `C(K)` decreasing and convex,
which is essential for a well-behaved second derivative.
"""

from __future__ import annotations
import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {"strike", "last_price"}


def validate_quotes(df: pd.DataFrame) -> pd.DataFrame:
    """Basic schema checks and cleaning for quotes DataFrame."""
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    out = df.copy()
    out = out[(out["strike"] > 0) & (out["last_price"] >= 0)]
    out = out.sort_values("strike").reset_index(drop=True)
    return out


def extrapolate_calls(df: pd.DataFrame, spot: float) -> tuple[pd.DataFrame, float, float]:
    """Pad strike range below min and above max with conservative prices.

    Returns the extended DataFrame and the original (min_strike, max_strike).
    """
    df = df.sort_values("strike").reset_index(drop=True)
    kmin, kmax = int(df.strike.min()), int(df.strike.max())

    lower = [{"strike": k, "last_price": max(spot - k, 0.0)} for k in range(0, kmin)]
    upper = [{"strike": k, "last_price": 0.0} for k in range(kmax + 1, 2 * kmax)]

    out = pd.concat([pd.DataFrame(lower), df, pd.DataFrame(upper)], ignore_index=True)
    return out, float(kmin), float(kmax)

# -------------------------------
# app/risk_neutral_pdf/predict.py
# -------------------------------

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
    pdf_dense = breeden_litzenberger_pdf(K_dense, C_dense, risk_free_rate, T, renormalize=True)

    # Crop back to original strike band
    mask = (K_dense >= kmin) & (K_dense <= kmax)
    K_out, pdf_out = K_dense[mask], pdf_dense[mask]

    # Optional kernel smoothing
    if kernel_smooth:
        K_out, pdf_out = kde_pdf(K_out, pdf_out)

    return pd.DataFrame({"price": K_out, "pdf": pdf_out})
