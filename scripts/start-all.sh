#!/bin/bash
DIR="$(dirname "$0")"

echo "Starting backend..."
"$DIR/start-backend.sh"

echo "Starting frontend..."
"$DIR/start-frontend.sh"
