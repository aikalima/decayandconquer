#!/bin/bash
cd "$(dirname "$0")/../backend" || exit 1

VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3.14 -m venv .venv
    echo "Installing dependencies..."
    $VENV_DIR/bin/pip install -r requirements.txt
fi

export MASSIVE_API_KEY="${MASSIVE_API_KEY:-rvyOh4B22MMK1q5HnnJL8Dh1bAKbCQ4A}"
exec $VENV_DIR/bin/uvicorn app.main:app --host 0.0.0.0 --port 6173 --reload --reload-dir app
