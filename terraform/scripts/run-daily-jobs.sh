#!/bin/bash
# Daily cron job: update flat files + run theta scans
# Runs at 9:30 UTC (5:30 AM ET) weekdays via /etc/cron.d/decay-daily
set -euo pipefail

LOCKFILE="/tmp/decay-cron.lock"
exec 200>"$LOCKFILE"
flock -n 200 || { echo "$(date) Another job is running, skipping."; exit 0; }

APP_DIR="/opt/decay_core"
VENV="$APP_DIR/backend/.venv/bin/python"

echo ""
echo "============================================"
echo "Daily jobs started at $(date)"
echo "============================================"

cd "$APP_DIR/backend"
set -a; source "$APP_DIR/.env"; set +a

# ---------------------------------------------------------------
# 1. Stop API to release DuckDB lock for writes
# ---------------------------------------------------------------
echo "Stopping API..."
sudo systemctl stop decay-api

# ---------------------------------------------------------------
# 2. Update flat files (download + import new trading days)
# ---------------------------------------------------------------
echo ""
echo "--- Updating flat files ---"
$VENV programs/update_flat_files.py || echo "WARNING: Flat file update failed"

# ---------------------------------------------------------------
# 3. Theta scans — run configured target expiries
# ---------------------------------------------------------------
echo ""
echo "--- Theta scans from config/theta_scans.yaml ---"
$VENV programs/run_theta_scan.py --config config/theta_scans.yaml || {
  echo "WARNING: One or more configured theta scans failed, continuing..."
}

# ---------------------------------------------------------------
# 4. Restart API
# ---------------------------------------------------------------
echo ""
echo "Restarting API..."
sudo systemctl start decay-api

echo ""
echo "============================================"
echo "Daily jobs completed at $(date)"
echo "============================================"
