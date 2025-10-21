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

def extrapolate_call_prices(
    options_data: pd.DataFrame, spot: float
) -> tuple[pd.DataFrame, int, int]:
    """Extrapolate the price of the call options to strike prices outside
    the range of options_data. Extrapolation is done to zero and twice the
    highest strike price in options_data. Done to give the resulting PDF
    more stability.

    Args:
        options_data: a DataFrame containing options price data with
            cols ['strike', 'last_price']
        spot: the current price of the security

    Returns:
        the extended options_data DataFrame
    """
    min_strike = int(options_data.strike.min())
    max_strike = int(options_data.strike.max())
    lower_extrapolation = pd.DataFrame(
        {"strike": p, "last_price": spot - p} for p in range(0, min_strike)
    )
    upper_extrapolation = pd.DataFrame(
        {
            "strike": p,
            "last_price": 0,
        }
        for p in range(max_strike + 1, max_strike * 2)
    )
    return (
        pd.concat([lower_extrapolation, options_data, upper_extrapolation]),
        min_strike,
        max_strike,
    )

def calculate_mid_price(options_data: pd.DataFrame) -> pd.DataFrame:
    """Calculate mid-price from bid and ask prices, and filter invalid values."""
    options_data["mid_price"] = (options_data["bid"] + options_data["ask"]) / 2
    return options_data[options_data["mid_price"] >= 0].copy()
