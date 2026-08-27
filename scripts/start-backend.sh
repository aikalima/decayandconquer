#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR/backend" || exit 1

VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3.14 -m venv .venv
    echo "Installing dependencies..."
    $VENV_DIR/bin/pip install -r requirements.txt
fi

# Load .env if present
ENV_FILE="$ROOT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

if [ -z "$MASSIVE_API_KEY" ]; then
    echo "WARNING: MASSIVE_API_KEY is not set. Add it to $ENV_FILE for snapshot/heat map/theta features."
fi

exec $VENV_DIR/bin/uvicorn app.main:app --host 0.0.0.0 --port 6173 --reload --reload-dir app
