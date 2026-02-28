"""pipeline_trace.py

Runs the prediction pipeline step-by-step with detailed logging at each stage,
then plots the resulting PDF and CDF curves.

Usage:
    python pipeline_trace.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # non-interactive backend — no display required
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from app.prediction_pipeline.step1_prep import extrapolate_call_prices, calculate_mid_price
from app.prediction_pipeline.step2_implied_vol import calculate_IV
from app.prediction_pipeline.step3_smooth_iv import fit_bspline_IV, BSplineParams
from app.prediction_pipeline.step4_pdf import create_pdf_point_arrays, calculate_cdf, crop_pdf
from app.prediction_pipeline.step5_smooth_pdf import fit_kde

DATA_DIR = Path("app/data")

RUNS = [
    {
        "label": "SPY",
        "csv": DATA_DIR / "spy.csv",
        "spot": 595.0,
        "days_forward": 30,
        "risk_free_rate": 0.04,
        "solver": "brent",
        "kernel_smooth": False,
    },
    {
        "label": "NVIDIA",
        "csv": DATA_DIR / "nvidia_date20250128_strikedate20250516_price12144.csv",
        "spot": 121.44,
        "days_forward": 108,
        "risk_free_rate": 0.04,
        "solver": "brent",
        "kernel_smooth": False,
    },
]


def section(title: str):
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")


def log_df_stats(label: str, df: pd.DataFrame, cols: list[str] | None = None):
    cols = cols or [c for c in ["strike", "last_price", "mid_price", "iv"] if c in df.columns]
    print(f"\n  {label}  ({len(df)} rows)")
    for col in cols:
        s = df[col]
        print(f"    {col:>12}:  min={s.min():.4f}  max={s.max():.4f}  mean={s.mean():.4f}  nulls={s.isna().sum()}")


def log_array_stats(label: str, x: np.ndarray, y: np.ndarray):
    print(f"\n  {label}  ({len(x)} points)")
    print(f"    {'x (price/strike)':>20}:  [{x[0]:.2f} … {x[-1]:.2f}]")
    print(f"    {'y':>20}:  min={y.min():.6f}  max={y.max():.6f}  sum≈{np.trapezoid(y, x):.4f}")


def run_traced(cfg: dict) -> pd.DataFrame:
    label = cfg["label"]
    spot = cfg["spot"]
    days_forward = cfg["days_forward"]
    risk_free_rate = cfg["risk_free_rate"]
    solver = cfg["solver"]
    kernel_smooth = cfg["kernel_smooth"]
    bspline = BSplineParams()

    section(f"TICKER: {label}  |  spot={spot}  days={days_forward}  r={risk_free_rate}")

    # ------------------------------------------------------------------
    print("\n[Step 0] Load quotes from CSV")
    raw = pd.read_csv(cfg["csv"])
    raw["strike"] = raw["strike"].astype(np.float64)
    raw["last_price"] = raw["last_price"].astype(np.float64)
    raw["bid"] = raw["bid"].astype(np.float64)
    raw["ask"] = raw["ask"].astype(np.float64)
    log_df_stats("Raw quotes", raw, ["strike", "last_price", "bid", "ask"])

    # ------------------------------------------------------------------
    print("\n[Step 1] Extrapolate strike domain + compute mid-price")
    data, min_strike, max_strike = extrapolate_call_prices(raw.copy(), spot)
    print(f"    Original strike range : {min_strike} – {max_strike}")
    print(f"    Extrapolated range    : {data['strike'].min():.0f} – {data['strike'].max():.0f}")
    print(f"    Rows after extrapolation: {len(data)}")
    data = calculate_mid_price(data)
    print(f"    Rows after mid-price filter: {len(data)}")
    log_df_stats("After extrapolation", data, ["strike", "last_price", "mid_price"])

    # ------------------------------------------------------------------
    print(f"\n[Step 2] Solve implied volatility  (solver={solver})")
    rows_before = len(data)
    data = calculate_IV(data, spot, days_forward, risk_free_rate, solver)
    rows_after = len(data)
    failed = rows_before - rows_after
    print(f"    Rows in       : {rows_before}")
    print(f"    IV solve fail : {failed}  ({100*failed/rows_before:.1f}%)")
    print(f"    Rows out      : {rows_after}")
    log_df_stats("After IV solve", data, ["strike", "iv"])

    # ------------------------------------------------------------------
    print(f"\n[Step 3] B-spline smoothing of IV smile  (k={bspline.k}  s={bspline.smooth}  dx={bspline.dx})")
    denoised_iv = fit_bspline_IV(data, bspline)
    log_array_stats("Smoothed IV", denoised_iv[0], denoised_iv[1])

    # ------------------------------------------------------------------
    print("\n[Step 4] Breeden–Litzenberger → PDF")
    pdf = create_pdf_point_arrays(denoised_iv, spot, days_forward, risk_free_rate)
    log_array_stats("Full PDF (pre-crop)", pdf[0], pdf[1])

    cropped = crop_pdf(pdf, min_strike, max_strike)
    log_array_stats("Cropped PDF", cropped[0], cropped[1])

    # ------------------------------------------------------------------
    if kernel_smooth:
        print("\n[Step 5] KDE smoothing of PDF")
        cropped = fit_kde(cropped)
        log_array_stats("KDE-smoothed PDF", cropped[0], cropped[1])
    else:
        print("\n[Step 5] KDE smoothing — skipped")

    # ------------------------------------------------------------------
    print("\n[Step 6] Integrate PDF → CDF")
    cdf = calculate_cdf(cropped)
    log_array_stats("CDF", cdf[0], np.array(cdf[1]))
    print(f"    CDF start : {cdf[1][0]:.4f}")
    print(f"    CDF end   : {cdf[1][-1]:.4f}")

    prices, pdf_vals = cropped
    _, cdf_vals = cdf
    df = pd.DataFrame({"Price": prices, "PDF": pdf_vals, "CDF": cdf_vals})
    print(f"\n  Final output: {len(df)} rows  columns={list(df.columns)}")
    return df


def plot_results(results: list[tuple[str, pd.DataFrame]]):
    n = len(results)
    fig = plt.figure(figsize=(14, 5 * n))
    gs = gridspec.GridSpec(n, 2, figure=fig, hspace=0.45, wspace=0.3)

    for row, (label, df) in enumerate(results):
        ax_pdf = fig.add_subplot(gs[row, 0])
        ax_cdf = fig.add_subplot(gs[row, 1])

        ax_pdf.plot(df["Price"], df["PDF"], color="steelblue", linewidth=1.8)
        ax_pdf.fill_between(df["Price"], df["PDF"], alpha=0.15, color="steelblue")
        ax_pdf.set_title(f"{label} — Risk-Neutral PDF", fontsize=13)
        ax_pdf.set_xlabel("Price")
        ax_pdf.set_ylabel("Density")
        ax_pdf.grid(True, linestyle="--", alpha=0.4)

        ax_cdf.plot(df["Price"], df["CDF"], color="darkorange", linewidth=1.8)
        ax_cdf.set_title(f"{label} — CDF", fontsize=13)
        ax_cdf.set_xlabel("Price")
        ax_cdf.set_ylabel("Cumulative Probability")
        ax_cdf.grid(True, linestyle="--", alpha=0.4)

    out_path = Path("pipeline_trace.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\n  Plot saved → {out_path.resolve()}")


if __name__ == "__main__":
    results = []
    for cfg in RUNS:
        df = run_traced(cfg)
        results.append((cfg["label"], df))

    section("PLOTTING")
    plot_results(results)
