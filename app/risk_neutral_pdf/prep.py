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

    lower = [{"strike": k, "last_price": spot - k} for k in range(0, kmin)]
    upper = [{"strike": k, "last_price": 0.0} for k in range(kmax + 1, 2 * kmax)]

    out = pd.concat([pd.DataFrame(lower), df, pd.DataFrame(upper)], ignore_index=True)
    return out, float(kmin), float(kmax)