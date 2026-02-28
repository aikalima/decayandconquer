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
from typing import Callable, Literal
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from .black_scholes import call_value, call_vega

IV_LO, IV_HI = 1e-6, 5.0


@dataclass(frozen=True)
class IVBounds:
    lo: float = IV_LO
    hi: float = IV_HI

def bs_iv_newton_method(
    price: float,
    S: float,
    K: float,
    t: float,
    r: float,
    precision: float = 1e-4,
    initial_guess: float = None,
    max_iter: int = 1000,
    verbose: bool = False,
) -> float:
    """
    Computes the implied volatility (IV) using Newton-Raphson iteration.

    Args:
        price (float): Observed market price of the option.
        S (float): Current price of the underlying asset.
        K (float): Strike price of the option.
        t (float): Time to expiration in years.
        r (float): Risk-free interest rate (annualized).
        precision (float, optional): Convergence tolerance for Newton's method. Defaults to 1e-4.
        initial_guess (float, optional): Initial guess for IV. Defaults to 0.2 for ATM options, 0.5 otherwise.
        max_iter (int, optional): Maximum number of iterations before stopping. Defaults to 1000.
        verbose (bool, optional): If True, prints debugging information. Defaults to False.

    Returns:
        float: The implied volatility if found, otherwise np.nan.
    """

    # Set a dynamic initial guess if none is provided
    if initial_guess is None:
        initial_guess = (
            0.2 if abs(S - K) < 0.1 * S else 0.5
        )  # Lower guess for ATM, higher for OTM

    iv = initial_guess

    for i in range(max_iter):
        # Compute Black-Scholes model price and Vega
        P = call_value(S, K, iv, t, r)
        diff = price - P

        # Check for convergence
        if abs(diff) < precision:
            return iv

        # Compute Vega (gradient)
        grad = call_vega(S, K, iv, t, r)

        # Prevent division by near-zero Vega to avoid large jumps
        if abs(grad) < 1e-6:
            if verbose:
                print(f"Iteration {i}: Vega too small (grad={grad:.6f}), stopping.")
            return np.nan

        # Newton-Raphson update
        iv += diff / grad

        # Prevent extreme IV values (e.g., IV > 500%)
        if iv < 1e-6 or iv > 5.0:
            if verbose:
                print(f"Iteration {i}: IV out of bounds (iv={iv:.6f}), stopping.")
            return np.nan

    if verbose:
        print(f"Did not converge after {max_iter} iterations")

    return np.nan  # Return NaN if the method fails to converge

def bs_iv_brent_method(price, S, K, t, r):
    """
    Computes the implied volatility (IV) of a European call option using Brent’s method.

    This function finds the implied volatility by solving for sigma (volatility) in the
    Black-Scholes pricing formula. It uses Brent’s root-finding algorithm to find the
    volatility that equates the Black-Scholes model price to the observed market price.

    Args:
        price (float): The observed market price of the option.
        S (float): The current price of the underlying asset.
        K (float): The strike price of the option.
        t (float): Time to expiration in years.
        r (float, optional): The risk-free interest rate (annualized). Defaults to 0.

    Returns:
        float: The implied volatility (IV) if a solution is found.
        np.nan: If the function fails to converge to a solution.

    Raises:
        ValueError: If Brent’s method fails to find a root in the given range.

    Notes:
        - The function searches for IV within the range [1e-6, 5.0] (0.0001% to 500% volatility).
        - If `t <= 0`, the function returns NaN since volatility is undefined for expired options.
        - If the function fails to converge, it returns NaN instead of raising an exception.
    """

    if t <= 0:
        return np.nan  # No volatility if time is zero or negative

    try:
        return brentq(lambda iv: call_value(S, K, iv, t, r) - price, 1e-6, 5.0)
    except ValueError:
        return np.nan  # Return NaN if no solution is found

def calculate_IV(
    options_data: pd.DataFrame,
    spot: float,
    days_forward: int,
    risk_free_rate: float,
    solver_method: Literal["newton", "brent"],
) -> pd.DataFrame:
    """
    Calculate the implied volatility (IV) of the options in options_data.

    Args:
        options_data (pd.DataFrame): A DataFrame containing option price data with
            columns ['strike', 'last_price'].
        spot (float): The current price of the security.
        days_forward (int): The number of days in the future to estimate the
            price probability density at.
        risk_free_rate (float, optional): Annual risk-free rate in nominal terms. Defaults to 0.
        solver_method (Literal["newton", "brent"], optional):
            The method used to solve for IV.
            - "newton" (default) uses Newton-Raphson iteration.
            - "brent" uses Brent’s method (more stable).

    Returns:
        DataFrame: The options_data DataFrame with an additional column for implied volatility (IV).
    """
    years_forward = days_forward / 365

    # Choose the IV solver method
    if solver_method == "newton":
        iv_solver = bs_iv_newton_method
    elif solver_method == "brent":
        iv_solver = bs_iv_brent_method
    else:
        raise ValueError("Invalid solver_method. Choose either 'newton' or 'brent'.")

    options_data["iv"] = options_data.apply(
        lambda row: iv_solver(
            row.last_price, spot, row.strike, years_forward, r=risk_free_rate
        ),
        axis=1,
    )

    # Remove rows where IV could not be calculated
    options_data = options_data.dropna()

    return options_data
