#!/bin/bash
# Daily cron job: update flat files + run theta scans
# Runs at 9:30 UTC weekdays via /etc/cron.d/decay-daily
set -euo pipefail

APP_DIR="/opt/decay_core"
VENV="$APP_DIR/backend/.venv/bin/python"

echo ""
echo "============================================"
echo "Daily jobs started at $(date)"
echo "============================================"

cd "$APP_DIR/backend"
set -a; source "$APP_DIR/.env"; set +a

# Downloads, imports and scans use a private DB; only publication restarts the API.
$VENV -u programs/refresh_data.py --service decay-api "$@"

echo ""
echo "============================================"
echo "Daily jobs completed at $(date)"
echo "============================================"
