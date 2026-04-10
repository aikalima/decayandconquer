import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from app.prediction_pipeline.predict import predict_price

DATA_DIR = Path(__file__).parent.parent / "app" / "data"
PLOT_DIR = Path(__file__).parent / "plots"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assert_valid_result(result: pd.DataFrame, min_rows: int = 1):
    assert isinstance(result, pd.DataFrame)
    assert {"Price", "PDF", "CDF"} <= set(result.columns)
    assert len(result) >= min_rows

    # PDF must be non-negative
    assert result["PDF"].ge(0).all(), "PDF must be non-negative"

    # PDF should integrate close to 1 over the full domain
    integral = np.trapezoid(result["PDF"].values, result["Price"].values)
    assert 0.8 < integral < 1.2, f"PDF integral = {integral:.4f}, expected ~1.0"

    # CDF must be in [0, 1] and non-decreasing
    assert result["CDF"].ge(-1e-9).all(), "CDF has negative values"
    assert result["CDF"].le(1.0 + 1e-9).all(), "CDF exceeds 1.0"
    assert result["CDF"].is_monotonic_increasing, "CDF must be non-decreasing"


def plot_result(
    result: pd.DataFrame,
    ticker: str,
    spot: float,
    days_forward: int,
    risk_free_rate: float,
    solver: str,
    filename: str,
    kde: bool = False,
):
    """Save and show a 2-panel PDF + CDF plot for a pipeline result."""
    PLOT_DIR.mkdir(exist_ok=True)

    years = days_forward / 365
    method = f"{solver.title()}" + (" + KDE" if kde else "")

    fig, (ax_pdf, ax_cdf) = plt.subplots(1, 2, figsize=(14, 5.5))
    fig.suptitle(
        f"{ticker} — Risk-Neutral Price Distribution at T = {days_forward} days ({years:.2f}y)",
        fontsize=14, fontweight="bold", y=1.0,
    )

    # --- PDF panel ---
    ax_pdf.plot(result["Price"], result["PDF"], color="steelblue", linewidth=1.5)
    ax_pdf.fill_between(result["Price"], result["PDF"], alpha=0.15, color="steelblue")
    ax_pdf.axvline(spot, color="crimson", linestyle="--", linewidth=1, label=f"Spot (now) = ${spot:.2f}")
    peak_idx = result["PDF"].idxmax()
    peak_price = result.loc[peak_idx, "Price"]
    ax_pdf.axvline(peak_price, color="green", linestyle=":", linewidth=1,
                   label=f"Mode (most likely) = ${peak_price:.1f}")
    integral = np.trapezoid(result["PDF"].values, result["Price"].values)
    ax_pdf.set_title("Probability Density")
    ax_pdf.set_xlabel(f"Predicted Price in {days_forward} Days ($)")
    ax_pdf.set_ylabel("Probability Density (per $)")
    ax_pdf.legend(fontsize=8, loc="upper right")

    # Stats box
    # Compute mean = E[X] = integral(x * pdf dx)
    mean_price = np.trapezoid(result["Price"].values * result["PDF"].values, result["Price"].values)
    stats_text = (
        f"Horizon: {days_forward}d ({years:.2f}y)\n"
        f"Solver: {method}\n"
        f"r = {risk_free_rate:.1%}\n"
        f"$\\int$ PDF = {integral:.4f}\n"
        f"E[Price] = ${mean_price:.1f}"
    )
    ax_pdf.text(0.03, 0.95, stats_text, transform=ax_pdf.transAxes,
                ha="left", va="top", fontsize=8, family="monospace",
                bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="gray", alpha=0.85))
    ax_pdf.grid(True, linestyle="--", alpha=0.3)

    # --- CDF panel ---
    ax_cdf.plot(result["Price"], result["CDF"], color="darkorange", linewidth=1.5)
    ax_cdf.axvline(spot, color="crimson", linestyle="--", linewidth=1, label=f"Spot (now) = ${spot:.2f}")
    ax_cdf.axhline(0.5, color="gray", linestyle=":", linewidth=0.8, alpha=0.5)

    # Percentiles
    for pct, color, style in [(0.25, "purple", ":"), (0.50, "green", "--"), (0.75, "purple", ":")]:
        idx = (result["CDF"] - pct).abs().idxmin()
        price_at_pct = result.loc[idx, "Price"]
        label = f"{'Median' if pct == 0.5 else f'P{int(pct*100)}'} = ${price_at_pct:.1f}"
        ax_cdf.axvline(price_at_pct, color=color, linestyle=style, linewidth=1, label=label)

    ax_cdf.set_title("Cumulative Distribution")
    ax_cdf.set_xlabel(f"Predicted Price in {days_forward} Days ($)")
    ax_cdf.set_ylabel("P(Price < x)")
    ax_cdf.set_ylim(-0.02, 1.02)
    ax_cdf.legend(fontsize=8, loc="lower right")
    ax_cdf.grid(True, linestyle="--", alpha=0.3)

    fig.tight_layout()
    fig.savefig(PLOT_DIR / filename, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Dummy data (smoke test)
# ---------------------------------------------------------------------------

def test_predict_price_default_values():
    dummy_df = pd.DataFrame({
        'strike':     [100, 110, 120, 130, 140],
        'last_price': [25,  15,  5,   1,   0.5],
        'bid':        [24.9, 14.9, 4.9, 0.9, 0.4],
        'ask':        [25.1, 15.1, 5.1, 1.1, 0.6],
    })
    result = predict_price(quotes=dummy_df, spot=120, days_forward=30, risk_free_rate=0.02).df
    assert_valid_result(result)
    plot_result(result, "Dummy", spot=120, days_forward=30, risk_free_rate=0.02,
                solver="brent", filename="dummy.png")


# ---------------------------------------------------------------------------
# SPY real data
# ---------------------------------------------------------------------------

def test_predict_price_spy():
    """SPY options - strikes 360-700, spot ~595 (late-Jan 2025)."""
    quotes = pd.read_csv(DATA_DIR / "spy.csv")
    result = predict_price(
        quotes=quotes,
        spot=595.0,
        days_forward=30,
        risk_free_rate=0.04,
        solver="brent",
    ).df
    assert_valid_result(result, min_rows=10)
    peak_price = result.loc[result["PDF"].idxmax(), "Price"]
    assert 500 < peak_price < 700, f"PDF peak at unexpected price: {peak_price}"
    plot_result(result, "SPY", spot=595.0, days_forward=30, risk_free_rate=0.04,
                solver="brent", filename="spy_brent.png")


def test_predict_price_spy_with_kde():
    """SPY pipeline with KDE smoothing enabled."""
    quotes = pd.read_csv(DATA_DIR / "spy.csv")
    result = predict_price(
        quotes=quotes,
        spot=595.0,
        days_forward=30,
        risk_free_rate=0.04,
        solver="brent",
        kernel_smooth=True,
    ).df
    assert_valid_result(result, min_rows=10)
    plot_result(result, "SPY", spot=595.0, days_forward=30, risk_free_rate=0.04,
                solver="brent", filename="spy_brent_kde.png", kde=True)


# ---------------------------------------------------------------------------
# NVIDIA real data
# ---------------------------------------------------------------------------

NVDA_FILE = "nvidia_date20250128_strikedate20250516_price12144.csv"
NVDA_SPOT = 121.44
NVDA_DAYS = 108  # Jan 28 -> May 16, 2025

def test_predict_price_nvidia():
    """NVIDIA options - strikes 5-300, spot 121.44, expiry May 16 2025."""
    quotes = pd.read_csv(DATA_DIR / NVDA_FILE)
    result = predict_price(
        quotes=quotes,
        spot=NVDA_SPOT,
        days_forward=NVDA_DAYS,
        risk_free_rate=0.04,
        solver="brent",
    ).df
    assert_valid_result(result, min_rows=10)
    peak_price = result.loc[result["PDF"].idxmax(), "Price"]
    assert 80 < peak_price < 200, f"PDF peak at unexpected price: {peak_price}"
    plot_result(result, "NVIDIA", spot=NVDA_SPOT, days_forward=NVDA_DAYS, risk_free_rate=0.04,
                solver="brent", filename="nvidia_brent.png")


def test_predict_price_nvidia_newton():
    """NVIDIA pipeline using Newton-Raphson IV solver."""
    quotes = pd.read_csv(DATA_DIR / NVDA_FILE)
    result = predict_price(
        quotes=quotes,
        spot=NVDA_SPOT,
        days_forward=NVDA_DAYS,
        risk_free_rate=0.04,
        solver="newton",
    ).df
    assert_valid_result(result, min_rows=10)
    plot_result(result, "NVIDIA", spot=NVDA_SPOT, days_forward=NVDA_DAYS, risk_free_rate=0.04,
                solver="newton", filename="nvidia_newton.png")
