#!/usr/bin/env bash
# Deploy code updates to the existing GCP VM.
#
# Assumes the persistent DuckDB already exists on the VM at:
#   /data/decay/db/options.duckdb
#
# Usage:
#   scripts/deploy-gcp.sh
#
# Optional env overrides:
#   DEPLOY_HOST=136.107.127.41
#   DEPLOY_USER=decay
#   DEPLOY_BRANCH=terraform
#   DEPLOY_APP_DIR=/opt/decay_core
#   DEPLOY_DB_PATH=/data/decay/db/options.duckdb
#   DEPLOY_FORCE_REMOTE=1   # reset VM checkout to origin/branch

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v ssh >/dev/null 2>&1; then
  echo "ERROR: ssh is required." >&2
  exit 1
fi

DEPLOY_USER="${DEPLOY_USER:-decay}"
DEPLOY_APP_DIR="${DEPLOY_APP_DIR:-/opt/decay_core}"
DEPLOY_DB_PATH="${DEPLOY_DB_PATH:-/data/decay/db/options.duckdb}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
DEPLOY_FORCE_REMOTE="${DEPLOY_FORCE_REMOTE:-0}"

DEPLOY_HOST="${DEPLOY_HOST:-}"
if [[ -z "$DEPLOY_HOST" ]] && command -v terraform >/dev/null 2>&1 && [[ -d terraform ]]; then
  DEPLOY_HOST="$(terraform -chdir=terraform output -raw external_ip 2>/dev/null || true)"
fi
DEPLOY_HOST="${DEPLOY_HOST:-136.107.127.41}"

LOCAL_COMMIT="$(git rev-parse HEAD)"
PUBLIC_URL="${PUBLIC_URL:-http://$DEPLOY_HOST}"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "WARNING: local worktree has uncommitted changes. This deploy uses code already pushed to git."
fi

if git rev-parse --abbrev-ref --symbolic-full-name "@{u}" >/dev/null 2>&1; then
  UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name "@{u}")"
  if [[ -n "$(git log --oneline "$UPSTREAM"..HEAD)" ]]; then
    echo "WARNING: local branch has commits not pushed to $UPSTREAM."
  fi
fi

echo "Deploying branch '$DEPLOY_BRANCH' to $DEPLOY_USER@$DEPLOY_HOST"
echo "App dir: $DEPLOY_APP_DIR"
echo "DuckDB:  $DEPLOY_DB_PATH"

ssh "$DEPLOY_USER@$DEPLOY_HOST" "bash -s" -- \
  "$DEPLOY_APP_DIR" \
  "$DEPLOY_DB_PATH" \
  "$DEPLOY_BRANCH" \
  "$LOCAL_COMMIT" \
  "$DEPLOY_FORCE_REMOTE" <<'REMOTE_SCRIPT'
set -Eeuo pipefail

APP_DIR="$1"
DB_PATH="$2"
BRANCH="$3"
LOCAL_COMMIT="$4"
FORCE_REMOTE="$5"

if [[ ! -d "$APP_DIR/.git" ]]; then
  echo "ERROR: $APP_DIR is not a git checkout." >&2
  exit 1
fi

if [[ ! -s "$DB_PATH" ]]; then
  echo "ERROR: DuckDB not found or empty at $DB_PATH." >&2
  echo "This deploy script assumes the DB is already present on the VM." >&2
  exit 1
fi

cd "$APP_DIR"

echo ""
echo "--- Git update ---"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
if [[ "$FORCE_REMOTE" == "1" ]]; then
  git reset --hard "origin/$BRANCH"
else
  git pull --ff-only origin "$BRANCH"
fi

REMOTE_COMMIT="$(git rev-parse HEAD)"
if [[ "$REMOTE_COMMIT" != "$LOCAL_COMMIT" ]]; then
  echo "WARNING: VM is deploying commit $REMOTE_COMMIT, local HEAD is $LOCAL_COMMIT."
  echo "         Push your local branch first if that is not expected."
fi

echo ""
echo "--- DuckDB link ---"
mkdir -p "$APP_DIR/backend/app/data"
if [[ -L "$APP_DIR/backend/app/data/options.duckdb" || ! -e "$APP_DIR/backend/app/data/options.duckdb" ]]; then
  ln -sfn "$DB_PATH" "$APP_DIR/backend/app/data/options.duckdb"
else
  echo "WARNING: $APP_DIR/backend/app/data/options.duckdb exists and is not a symlink; leaving it untouched."
fi
ls -lh "$DB_PATH"

echo ""
echo "--- Backend dependencies ---"
cd "$APP_DIR/backend"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -r requirements.txt

echo ""
echo "--- Frontend build ---"
cd "$APP_DIR/frontend"
npm ci --silent
env VITE_API_BASE="" npm run build

echo ""
echo "--- Restart API ---"
sudo systemctl restart decay-api

echo "Waiting for API health..."
for attempt in {1..30}; do
  if curl -fsS http://127.0.0.1:6173/ping; then
    echo ""
    break
  fi
  if [[ "$attempt" == "30" ]]; then
    echo "ERROR: API did not become healthy within 30 seconds." >&2
    sudo systemctl --no-pager --full status decay-api | sed -n '1,40p'
    exit 1
  fi
  sleep 1
done
sudo systemctl --no-pager --full status decay-api | sed -n '1,12p'
REMOTE_SCRIPT

echo ""
echo "--- Public health check ---"
for attempt in {1..30}; do
  if curl -fsS "$PUBLIC_URL/ping"; then
    echo ""
    break
  fi
  if [[ "$attempt" == "30" ]]; then
    echo "ERROR: public health check did not pass within 30 seconds." >&2
    exit 1
  fi
  sleep 1
done
echo ""
echo "Deploy complete: $PUBLIC_URL"
