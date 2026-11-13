# Decay And Conquer!

Predict where a stock is headed by reverse-engineering probability distributions from 90 million+ options data points. Extracts the market-implied risk-neutral PDF of future prices using Black-Scholes inversion, B-spline smoothing, and the Breeden-Litzenberger formula.

[Try it out](https://www.decayandconquer.com)

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

# Start app plus local HTTP MCP endpoints
scripts/start-all.sh --with-mcp
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

### Read-Only Query Benchmark

From the repository root, compare full-history queries with the optimized
recent-history and existence queries against your existing database:

```bash
backend/.venv/bin/python backend/programs/benchmark_queries.py --repeats 7 \
  --json /tmp/decay-queries-$(date +%Y%m%d-%H%M%S).json
backend/.venv/bin/python -m pytest backend/tests/test_db_queries.py -q
```

Use `--db /data/decay/db/options.duckdb` on the GCP instance. Optional
`--tickers SPY NVDA MSFT` and `--days 5 30 180` select the cases. This opens
DuckDB read-only, makes no external API calls, and does not delete data, build
indexes, or change the schema. Run when imports/scans are idle for comparable
measurements; an active database writer may prevent a read-only connection.

The benchmark warms both paths, alternates their execution order, reports
median timings and raw samples, and checks exact result equality. These are
warm-query measurements, not cold-disk or whole-application latency estimates.
Both daily-price paths use the same deterministic tie-break (lowest strike,
then earliest expiry, then contract ticker). The old strike-only ordering
could produce different prices on repeated parallel scans. Prices remain
options-derived estimates, not actual underlying stock closes.

Recent-price queries use the latest date in the database, not today's date,
and fall back to full history when the recent window has too few observations.
Sparse/inactive tickers may therefore be slightly slower. No result cache is
used, so newly imported data is immediately visible to these queries.

### Calculation Inputs and Data Health

Predictions, chat, and Prediction MCP share point-in-time input preparation.
Actual unadjusted Massive daily stock closes are requested for the options
observation dates and cached under `backend/app/data/cache/stock_daily/`.
Online cache entries refresh daily to pick up provider corrections. These
are completed daily bars, not live intraday prices. `MASSIVE_API_KEY` is needed;
the launcher scripts load it from the project `.env`.

When actual prices are unavailable, estimates are explicitly flagged with
their dates in result metadata. IV averaging uses each day's own stock price.
Option maturity is separate from forecast horizon; different-expiry horizon
projections disclose their constant-volatility assumption. Historical API
chains never use live snapshots, substituted expiries, or previous-day trades;
legacy chain/spot cache entries are ignored without deleting them.

Backtest scoring requires an actual stock close on the exact target date.
Missing/non-trading-day targets are not scored against later prices or
options-derived estimates. Density clipping diagnostics and model limitations
are included in responses. Dividend adjustments, American exercise modelling,
and empirical probability calibration are not yet implemented.

`GET /data-health` and the dashboard's expandable Data health strip report
options date coverage, calendar-day age, and scan timestamps. Weekday gaps are
explicitly unclassified: they may be holidays or failed imports. Coverage is
dataset-wide, not a guarantee that every ticker/contract is complete. Refresh
job state is reported as unknown, never inferred from a scan timestamp.
The endpoint does not download or alter data. Options history still needs the
normal flat-file refresh; fetching current stock prices does not refresh it.

### Theta Candidate Quality

Theta Plays uses the same read-time eligibility checks in the HTTP API and MCP.
Default rankings exclude unknown/stale inputs (over four calendar days), expired
or mismatched expiries, unverified underlying/HV sources, insufficient HV history,
HV at or below 1%, invalid IV/prices, IV asymmetry of at least 2x, unknown/low open
interest (below 10), zero/missing volume, and invalid or at least 20%-wide quotes.
These are conservative research heuristics, not calibrated measures of trade quality.
Daily marks with dates and liquidity can qualify, but are labeled as non-executable.
Scores retain quality penalties; zero scores never fall back to raw IV/HV ratios.

Use **Include flagged candidates** to inspect excluded rows. The ticker opens
source dates, per-leg inputs, HV coverage, ranking reasons and model limitations.
The API accepts `include_flagged=true`; MCP `get_theta_plays` accepts the same
boolean and returns category-specific eligibility counts. IV/HV means volatility
richness, not a dollar premium or directional prediction.

New scans use actual split-adjusted stock closes for HV and date-aligned beta,
with N+1 closes for N daily returns. The underlying reference is a dated raw stock
close or a newer timestamped snapshot. Failed IV is not copied from the other leg.
Old scans remain inspectable but cannot pass provenance checks retroactively.
No options-history purge is required: rerun the normal theta scan job to populate
the new fields. Schema columns are added on the next writable connection; read-only
servers can inspect older schemas without a migration. Dividend/earnings checks
and American-option modelling remain unverified, disclosed limitations.

Batch scans run the longest HV lookback first so shorter expiries reuse the same
fresh stock-history cache. Stock HTTP 429 responses receive up to three 65-second
backoffs in batch scans; interactive predictions do not inherit those long waits.
Snapshot requests use 250 contracts per page to reduce pagination overhead.
When available on the existing subscription, a grouped daily stock request warms
raw closing prices for the entire scan universe; unsupported bulk access falls
back to individual dated requests. The top-ticker universe is anchored to the
latest options date in DuckDB, with a warning when that volume history is stale.

## CLI Tools

All CLI tools live in `backend/programs/` and run from the `backend/` directory with the virtualenv activated. API keys are loaded from `.env` in the project root.

```bash
cd backend
source .venv/bin/activate
```

### Flat Files (Options Data)

Download and import daily options data from Massive.com S3 into DuckDB (~90M+ rows).

Flat-file downloads use Massive's S3 credentials, not the REST API key. Set these in the repo-root `.env`:

```bash
MASSIVE_API_KEY=your-massive-rest-api-key
MASSIVE_S3_ACCESS_KEY=your-massive-flat-files-s3-access-key
MASSIVE_S3_SECRET_KEY=your-massive-flat-files-s3-secret-key
```

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

# Run all configured theta scans
python programs/run_theta_scan.py --config config/app_defaults.json

# On GCP, build scans in a private DB and briefly restart only to publish
python programs/refresh_data.py --theta-only

# Purge theta scan data
python programs/purge_theta.py                  # delete all theta data
python programs/purge_theta.py --days 30        # delete only 30-day DTE scans
python programs/purge_theta.py --dry-run        # preview what would be deleted
```

App defaults live in `backend/config/app_defaults.json`. It controls prediction defaults, sample chat questions, the timeline range, and the theta scan policy. The theta scanner computes upcoming monthly third-Friday expiries and `days_forward` at runtime. Results are stored in `theta_scans` and `theta_results` DuckDB tables. The API serves defaults at `GET /app-defaults` and the latest scan results at `GET /theta-plays`.

### Theta Plays MCP Server

The Theta Plays MCP server exposes saved screener results to MCP clients as read-only tools. It reads the same DuckDB tables as the app and opens the database in read-only mode, so it can run while the web app is running.

```bash
# Run the MCP server over stdio
scripts/start-theta-mcp.sh

# Run as a local HTTP MCP endpoint
cd backend
.venv/bin/python -m app.theta_mcp --transport streamable-http --port 6181

# Or from backend directly
cd backend
.venv/bin/python -m app.theta_mcp

# Inspect during development
cd backend
.venv/bin/mcp dev app/theta_mcp.py
```

Available MCP tools:

- `list_theta_expiries` — list configured and scanned expiries, including scan freshness.
- `get_theta_plays` — return ranked rows for `highest_premium`, `expensive_calls`, or `expensive_puts`, with optional diagnostics for bid/ask quality, IV skew, and put-call parity.
- `get_theta_play_detail` — return one ticker's row, diagnostics, and a concise interpretation.

Example client config:

```json
{
  "mcpServers": {
    "decay-theta-plays": {
      "command": "/Users/markus/src/decay_core/scripts/start-theta-mcp.sh"
    }
  }
}
```

Copyable skill file:

- `mcp-skills/decay-theta-plays/SKILL.md`

### Backtesting

Run the backtest CLI against historical data via the Massive.com API:

```bash
python programs/backtest.py --ticker SPY --days-forward 30
python programs/backtest.py --ticker AAPL --dates 2025-01-06 2025-01-13 --days-forward 60
```

### Prediction MCP Server

The Prediction MCP server exposes the Backtest & Forecast feature to MCP clients without modifying the historical DuckDB database. It reads local options data and fetches date-matched, unadjusted daily stock closes from Massive, with a local cache refreshed daily. Set `MASSIVE_API_KEY` in the project `.env`; the startup scripts load it. Missing underlying prices are explicitly flagged as estimates, and backtests are scored only when an actual target-date stock close is available.

```bash
# Run the MCP server over stdio
scripts/start-prediction-mcp.sh

# Run as a local HTTP MCP endpoint
cd backend
.venv/bin/python -m app.prediction_mcp --transport streamable-http --port 6182

# Or from backend directly
cd backend
.venv/bin/python -m app.prediction_mcp
```

Available MCP tools:

- `get_prediction_defaults` — return date-aware prediction defaults and local DuckDB stats.
- `run_prediction` — run a single-day or observation-window prediction and return compact distribution statistics.
- `run_backtest` — run a compact local backtest across explicit historical observation dates.

Example client config:

```json
{
  "mcpServers": {
    "decay-predictions": {
      "command": "/Users/markus/src/decay_core/scripts/start-prediction-mcp.sh"
    }
  }
}
```

Copyable skill file:

- `mcp-skills/decay-predictions/SKILL.md`

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
    config/
      app_defaults.json      # Date-aware UI defaults + theta scan policy
    app/
      main.py                # FastAPI server
      screener.py            # Theta plays computation (IV/HV, beta, efficiency)
      theta_mcp.py           # Read-only MCP server for theta_scans/theta_results
      news.py                # Market context via Anthropic web search
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
  terraform/
    main.tf                    # Terraform provider config
    variables.tf               # Input variables
    network.tf                 # VPC, firewall, static IP
    compute.tf                 # GCE VM + data disk
    secrets.tf                 # Secret Manager for API keys
    outputs.tf                 # IP, SSH command
    startup.sh                 # VM bootstrap script
    scripts/run-daily-jobs.sh  # Cron wrapper for flat files + theta scans
```

## GCP Deployment

Deploy the app to a single GCE VM (~$31/mo) using Terraform. The VM runs nginx (frontend + API proxy), uvicorn (FastAPI backend), and daily cron jobs for data updates.

### Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.5
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) authenticated
- A GCP project with billing enabled
- SSH key pair (default: `~/.ssh/id_ed25519`)

### Deploy

```bash
cd terraform

# 1. Configure variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your project ID, API keys, etc.
# Optional: set anthropic_model = "claude-sonnet-5"

# 2. Initialize and apply
terraform init
terraform plan
terraform apply

# 3. Transfer DuckDB to the VM (5.7GB, takes a few minutes)
gcloud compute scp backend/app/data/options.duckdb \
  decay-core:/data/decay/db/options.duckdb \
  --zone=us-east4-c

# 4. Verify
curl http://$(terraform output -raw external_ip)/ping
```

### Post-Deploy

```bash
# SSH into the VM
ssh decay@$(terraform output -raw external_ip)

# Check service status
systemctl status decay-api
curl localhost:6173/ping

# View logs
tail -f /var/log/decay/api.log
tail -f /var/log/decay/cron.log

# Set up HTTPS (if domain_name is configured)
sudo certbot --nginx -d yourdomain.com
```

### GCP Ops Commands

Log in to the VM:

```bash
ssh decay@136.107.127.41
cd /opt/decay_core/backend
```

Preview the configured theta scans without spending API calls:

```bash
.venv/bin/python programs/run_theta_scan.py --config config/app_defaults.json --dry-run
```

Run only the configured theta scans while the API continues serving the current database:

```bash
.venv/bin/python programs/refresh_data.py --theta-only
```

Pull and import the newest published options flat files into a private database, then publish:

```bash
.venv/bin/python programs/update_flat_files.py --dry-run
.venv/bin/python programs/refresh_data.py --options-only
```

Run the full daily maintenance workflow manually. The API stays online during downloads, imports and scans; it briefly restarts only after the new database passes validation:

```bash
/opt/decay_core/scripts/run-daily-jobs.sh
```

The staged workflow runs on the systemd-based GCP VM. Local standalone scripts
(`update_flat_files.py` and `run_theta_scan.py`) still write directly to their DB
and require other readers to be stopped before saving. `--manage-service` remains
available for legacy direct scans but stops the API for the entire scan.

### Redeploy Code Updates

```bash
scripts/deploy-gcp.sh
```

The deploy script assumes `options.duckdb` already exists on the VM at `/data/decay/db/options.duckdb`. It pulls the current branch on the VM, installs backend dependencies, rebuilds the frontend, restarts `decay-api`, and runs health checks. Override defaults with environment variables, for example:

```bash
DEPLOY_HOST=136.107.127.41 DEPLOY_BRANCH=terraform scripts/deploy-gcp.sh
```

### Daily Scheduled Jobs

The cron runs at **9:30 UTC (5:30 AM EDT / 4:30 AM EST)** on weekdays:

1. Acquires the same lock as deployment, checks disk space, and copies the live
   DuckDB to a temporary directory beside it. The API keeps reading the live DB.
2. Downloads and imports published flat files into the private copy. Strict mode
   treats S3/listing/download/import failures as errors, not successful refreshes.
   Unpublished dates (including market holidays) are not download failures.
3. Runs theta scans from `backend/config/app_defaults.json` against the private DB.
4. Validates options row count/date coverage and a fresh, complete saved scan for
   every configured expiry. Individual unsupported tickers may still be skipped.
5. Preserves a rollback link, briefly stops the API, atomically replaces the live
   DB, starts the API and checks `/data-health` for the expected rows and scan times.
   If the new API is unhealthy, restores the old DB and starts it again.

**Availability:** this removes the long batch-processing outage, not every second
of downtime. Only the final stop/start interrupts requests, normally a few seconds;
draining requests or rollback can take longer. A failed build leaves the live DB
and API untouched. The updater publishes whichever files Massive has actually
listed; check Data health for the resulting date, not just the job's exit status.

**Resources:** staging temporarily needs another full DB copy (currently about
9 GB), plus room for downloads, growth and temporary import files. A preflight
requires the DB size plus at least 2 GiB free; larger catch-up imports can need
more. Completed/failed builds clean up staging files. If rollback itself fails,
the log reports a `.decay-refresh-*` recovery directory that is deliberately kept.
Do not remove it before recovering the database and API. Staged workers default
to a 1 GB DuckDB memory limit and two threads; override with
`DECAY_REFRESH_MEMORY_LIMIT` and `DECAY_REFRESH_THREADS` if needed.

Only `decay-api` is restarted. Separately running MCP processes or other persistent
DB readers must also reconnect/restart to see the newly published snapshot. Do not
run direct DB writers alongside the staged workflow. The `DECAY_DB_PATH` override
is set only for batch subprocesses; do not point the API at a staging file.

Logs: `/var/log/decay/cron.log`

### Cost Estimate

| Resource | Monthly Cost |
|----------|-------------|
| e2-medium VM (sustained use) | $24.46 |
| 20GB boot disk | $1.70 |
| 30GB SSD data disk | $5.10 |
| Static IP | $0 |
| Secret Manager | $0.06 |
| **Total** | **~$31/mo** |

### Destroy

```bash
cd terraform
terraform destroy
```

**Note:** The data disk is preserved by default. Delete it manually if you want to remove all data.
