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
# 3. Theta scans — compute days-forward for 3 target Fridays
#    Friday of the following week, +14d, +45d
# ---------------------------------------------------------------
NEXT_FRI=$($VENV -c "
from datetime import date, timedelta
today = date.today()
days_to_friday = (4 - today.weekday()) % 7
if days_to_friday == 0:
    days_to_friday = 7
# Following week's Friday
following_friday = today + timedelta(days=days_to_friday + 7)
print((following_friday - today).days)
")

echo ""
echo "--- Theta scans (days-forward: $NEXT_FRI, $((NEXT_FRI + 14)), $((NEXT_FRI + 45))) ---"

for DF in $NEXT_FRI $((NEXT_FRI + 14)) $((NEXT_FRI + 45)); do
  echo ""
  echo "Scanning --top 100 --days-forward $DF"
  $VENV programs/run_theta_scan.py --top 100 --days-forward "$DF" || {
    echo "WARNING: Theta scan for days_forward=$DF failed, continuing..."
  }
done

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
