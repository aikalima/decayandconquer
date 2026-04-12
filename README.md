# decay_core

Predict where a stock is headed by reverse-engineering probability distributions from 90 million+ options data points. Extracts the market-implied risk-neutral PDF of future prices using Black-Scholes inversion, B-spline smoothing, and the Breeden-Litzenberger formula.

## How It Works

The pipeline runs in five steps:

1. **Validate** — Check option quotes, sort by strike
2. **Implied Volatility** — Invert Black-Scholes to solve for IV at each strike (Brent or Newton)
3. **IV Smoothing** — Fit a B-spline to the raw IV smile, resample onto a dense grid
4. **PDF Extraction** — Apply Breeden-Litzenberger: `PDF = e^(rT) * d²C/dK²` via finite differences, normalise to integrate to 1
5. **KDE Smoothing** *(optional)* — Gaussian kernel density estimation for a cleaner final density

Output: a DataFrame with `Price` (strike), `PDF` (density), and `CDF` (cumulative probability).

## Quick Start (Dev Mode)

### Prerequisites

- Python 3.12+
- Node.js 18+

### Start both services

```bash
# Backend (FastAPI on :6173)
scripts/start-backend.sh

# Frontend (Vite + React on :6161)
scripts/start-frontend.sh

# Or start both at once
scripts/start-all.sh
```

### Stop

```bash
# Stop backend
scripts/stop-backend.sh

# Frontend: Ctrl+C in the terminal running it
```

### Restart backend

```bash
scripts/restart-backend.sh
```

### Manual setup

```bash
# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 6173

# Frontend (in a separate terminal)
cd frontend
npm install
npm run dev
```

Open [http://localhost:6161](http://localhost:6161) in your browser.

## Testing

```bash
cd backend
source venv/bin/activate
venv/bin/python -m pytest tests/ -v
```

22 tests cover the prediction pipeline, API endpoints, and backtest scoring logic.

## CLI Tools

All CLI tools live in `backend/programs/` and run from the `backend/` directory with the virtualenv activated. API keys are loaded from `.env` in the project root.

```bash
cd backend
source .venv/bin/activate
```

### Flat Files (Options Data)

Download and import daily options data from Massive.com S3 into DuckDB (~90M+ rows).

```bash
# Download a specific month
python programs/download_flat_files.py --year 2025 --month 6

# Download a specific date
python programs/download_flat_files.py --date 2025-06-15

# Download and filter to specific tickers only
python programs/download_flat_files.py --year 2025 --month 1 --tickers SPY,AAPL,NVDA

# List available files without downloading
python programs/download_flat_files.py --year 2025 --month 1 --list

# Import downloaded flat files into DuckDB
python programs/import_flat_files.py                    # import all files in flat_files/
python programs/import_flat_files.py --file app/data/flat_files/2025-06-15.csv.gz  # single file
python programs/import_flat_files.py --stats            # show DB stats (row count, date range, tickers)

# Catch up — download and import everything since the last file
python programs/update_flat_files.py                    # download + import new files
python programs/update_flat_files.py --dry-run          # preview what would be downloaded
python programs/update_flat_files.py --download-only    # download without importing
```

**Note:** The backend server holds a DuckDB write lock. Stop it before importing (`scripts/stop-backend.sh`), then restart after.

### Theta Plays Screener

Scan tickers for overpriced options (IV > HV) and store results in DuckDB. The frontend serves pre-computed results instantly via `GET /theta-plays`.

```bash
# Scan default 30 high-liquidity tickers, 30-day DTE
python programs/run_theta_scan.py

# Scan top 500 tickers by options volume (~4 min)
python programs/run_theta_scan.py --top 500

# Scan top 100 tickers (~40 sec)
python programs/run_theta_scan.py --top 100

# Scan specific tickers
python programs/run_theta_scan.py --tickers AAPL,MSFT,NVDA,TSLA

# Custom DTE and HV lookback (how many trading days to compute historical volatility)
python programs/run_theta_scan.py --top 200 --days-forward 45 --hv-days 30

# Purge theta scan data
python programs/purge_theta.py                  # delete all theta data
python programs/purge_theta.py --days 30        # delete only 30-day DTE scans
python programs/purge_theta.py --dry-run        # preview what would be deleted
```

Results are stored in `theta_scans` and `theta_results` DuckDB tables. The API serves the latest scan at `GET /theta-plays`.

### Backtesting

Run the backtest CLI against historical data via the Massive.com API:

```bash
python programs/backtest.py --ticker SPY --days-forward 30
python programs/backtest.py --ticker AAPL --dates 2025-01-06 2025-01-13 --days-forward 60
```

### Pipeline Trace (Dev/Debug)

Run the prediction pipeline step-by-step with detailed logging at each stage. Prints stats (row counts, IV ranges, PDF integral) and saves a diagnostic plot. Useful for debugging pipeline parameters.

```bash
python programs/pipeline_trace.py
```

Outputs `pipeline_trace.png` with PDF and CDF curves for sample data (SPY, NVIDIA).

## API

### `GET /ping`

Health check. Returns `{"pong": "Hello, world!"}`.

### `GET /predict`

Returns the estimated risk-neutral PDF and CDF.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `ticker` | str | `SPY` | Ticker symbol |
| `spot` | float | `121.44` | Current spot price |
| `days_forward` | int | `100` | Days to expiration |
| `risk_free_rate` | float | `0.03` | Annualized risk-free rate |
| `solver` | str | `brent` | IV solver: `brent` or `newton` |
| `bspline_k` | int | `3` | Spline degree |
| `bspline_smooth` | float | `10.0` | Spline regularization |
| `bspline_dx` | float | `0.1` | Dense grid spacing |
| `kernel_smooth` | bool | `true` | Enable KDE smoothing |

## Project Structure

```
decay_core/
  scripts/
    start-backend.sh         # Start backend on :6173
    stop-backend.sh          # Stop backend
    restart-backend.sh       # Restart backend + tail logs
    start-frontend.sh        # Start frontend on :6161
    start-all.sh             # Start both
  backend/
    app/
      main.py                # FastAPI server
      screener.py            # Theta plays computation (IV/HV, beta, efficiency)
      news.py                # Market context via Gemini + Google Search
      prediction_pipeline/   # 5-step PDF estimation pipeline
      data/
        db.py                # DuckDB schema + queries (options, theta_scans, theta_results)
        fetcher.py           # Massive.com API client + CSV caching
        flat_files/          # Downloaded daily options data (.csv.gz)
        cache/               # Cached API responses
    tests/                   # 22 tests + plot output
    programs/
      download_flat_files.py # Download flat files from Massive S3
      import_flat_files.py   # Import flat files into DuckDB
      update_flat_files.py   # Catch up — download + import since last file
      run_theta_scan.py      # Batch theta plays screener
      purge_theta.py         # Purge theta scan data
      backtest.py            # CLI backtesting harness
    requirements.txt
  frontend/
    src/
      layouts/               # Header, sidebar navigation
      pages/                 # Analyze (home), Theta Plays, Predictions
      components/            # Charts, forms, timeline, stats, market context
      api/                   # Backend API client
    package.json
```
