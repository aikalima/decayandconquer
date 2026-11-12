#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DIR/.." && pwd)"
WITH_MCP=false
BACKEND_PID=""
FRONTEND_PID=""
THETA_MCP_PID=""
PREDICTION_MCP_PID=""

usage() {
    echo "Usage: scripts/start-all.sh [--with-mcp]"
    echo ""
    echo "Starts backend on :6173 and frontend on :6161."
    echo "  --with-mcp    also start Theta MCP on :6181/mcp and Prediction MCP on :6182/mcp"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --with-mcp|--mcp)
            WITH_MCP=true
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
    shift
done

cleanup() {
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null
    fi
    if [ -n "$THETA_MCP_PID" ]; then
        kill "$THETA_MCP_PID" 2>/dev/null
    fi
    if [ -n "$PREDICTION_MCP_PID" ]; then
        kill "$PREDICTION_MCP_PID" 2>/dev/null
    fi
}

trap cleanup EXIT INT TERM

echo "Starting backend..."
"$DIR/start-backend.sh" &
BACKEND_PID=$!

echo "Starting frontend..."
"$DIR/start-frontend.sh" &
FRONTEND_PID=$!

if [ "$WITH_MCP" = true ]; then
    echo "Starting Theta MCP..."
    (
        cd "$ROOT_DIR/backend" || exit 1
        exec .venv/bin/python -m app.theta_mcp --transport streamable-http --host 127.0.0.1 --port 6181
    ) &
    THETA_MCP_PID=$!

    echo "Starting Prediction MCP..."
    (
        cd "$ROOT_DIR/backend" || exit 1
        exec .venv/bin/python -m app.prediction_mcp --transport streamable-http --host 127.0.0.1 --port 6182
    ) &
    PREDICTION_MCP_PID=$!
fi

echo ""
echo "Backend:  http://localhost:6173"
echo "Frontend: http://localhost:6161"
if [ "$WITH_MCP" = true ]; then
    echo "Theta MCP:      http://127.0.0.1:6181/mcp"
    echo "Prediction MCP: http://127.0.0.1:6182/mcp"
fi
echo "Press Ctrl+C to stop all."

wait
