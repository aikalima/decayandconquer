"""Data loading, validation, and extrapolation helpers.

The extrapolation step pads the strike domain to reduce boundary effects in
finite differencing. Below the minimum observed strike we set C(K) = max(S-K, 0)
(intrinsic value); above the maximum we set C(K) = 0. This keeps the call price
curve decreasing and convex — essential for a well-behaved second derivative.
"""

from __future__ import annotations
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"strike", "last_price"}


def validate_quotes(df: pd.DataFrame) -> pd.DataFrame:
    """Basic schema checks and cleaning for a quotes DataFrame.

    Ensures required columns exist, drops rows with non-positive strikes or
    negative prices, and sorts by strike.
    """
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    out = df.copy()
    n_before = len(out)
    out = out[(out["strike"] > 0) & (out["last_price"] >= 0)]
    n_dropped = n_before - len(out)
    if n_dropped:
        logger.warning("validate_quotes: dropped %d rows with invalid strike/price", n_dropped)

    return out.sort_values("strike").reset_index(drop=True)


def extrapolate_call_prices(
    options_data: pd.DataFrame, spot: float
) -> tuple[pd.DataFrame, float, float]:
    """Pad the strike domain with synthetic quotes for boundary stability.

    Below min_strike: intrinsic value max(S - K, 0).
    Above max_strike: price = 0 (deep OTM).

    Returns (extended_df, min_strike, max_strike) where the strike bounds
    refer to the *original* data range.
    """
    options_data = validate_quotes(options_data)

    min_strike = float(options_data["strike"].min())
    max_strike = float(options_data["strike"].max())

    # Extrapolate below: from near-zero up to (but not including) min_strike
    lower_strikes = np.arange(1.0, min_strike, 1.0)
    lower = pd.DataFrame({
        "strike": lower_strikes,
        "last_price": np.maximum(spot - lower_strikes, 0.0),
    })

    # Extrapolate above: from just past max_strike to 2x max_strike
    upper_strikes = np.arange(max_strike + 1.0, max_strike * 2, 1.0)
    upper = pd.DataFrame({
        "strike": upper_strikes,
        "last_price": np.zeros(len(upper_strikes)),
    })

    extended = pd.concat([lower, options_data, upper], ignore_index=True)
    return extended, min_strike, max_strike
