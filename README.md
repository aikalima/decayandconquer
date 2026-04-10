# decay_core

Risk-neutral probability distribution estimation from options market data. Extracts the market-implied PDF of future prices from European call option quotes using Black-Scholes inversion, spline smoothing, and the Breeden-Litzenberger formula.

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

## Backtesting

Run the backtest CLI against historical data via the Massive.com API:

```bash
cd backend
source venv/bin/activate
python backtest.py --ticker SPY --days-forward 30 --api-key YOUR_KEY
python backtest.py --ticker AAPL --dates 2025-01-06 2025-01-13 --days-forward 60
```

Set `MASSIVE_API_KEY` env var to avoid passing `--api-key` each time.

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
      prediction_pipeline/   # 5-step PDF estimation pipeline
      data/
        fetcher.py           # Massive.com API client + CSV caching
        cache/               # Cached API responses
        spy.csv              # Sample SPY options data
        nvidia_*.csv         # Sample NVIDIA options data
    tests/                   # 22 tests + plot output
    backtest.py              # CLI backtesting harness
    requirements.txt
  frontend/
    src/
      layouts/               # SaaS shell (header, sidebar)
      pages/                 # Backtest, Predictions (coming soon)
      components/            # Charts (Chart.js), forms, stats
      api/                   # Backend API client
    package.json
```
