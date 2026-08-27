#!/bin/bash
DIR="$(dirname "$0")"

cleanup() {
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null
    fi
}

trap cleanup EXIT INT TERM

echo "Starting backend..."
"$DIR/start-backend.sh" &
BACKEND_PID=$!

echo "Starting frontend..."
"$DIR/start-frontend.sh" &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:6173"
echo "Frontend: http://localhost:6161"
echo "Press Ctrl+C to stop both."

wait
